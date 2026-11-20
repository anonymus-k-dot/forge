// The request lifecycle: reducer (state transitions, ignored late updates) and session
// (one request at a time, Stop, recovery), driven through the real stream client.
import assert from "node:assert/strict";
import { test } from "node:test";
import { MESSAGES, streamEnhance } from "../../src/api/enhance.ts";
import { enhancementReducer, initialEnhancementState } from "../../src/state/enhancement.ts";
import { createEnhancementSession } from "../../src/state/session.ts";
import { manualResponse, scriptedFetch, settle, sse, sseResponse } from "./helpers.mjs";

function harness(...responders) {
  const { fetch, calls } = scriptedFetch(...responders);
  let state = initialEnhancementState;
  const history = [];
  const actions = [];
  const dispatch = (action) => {
    actions.push(action.type);
    state = enhancementReducer(state, action);
    history.push(state.phase);
  };
  const session = createEnhancementSession(dispatch, (prompt, options) =>
    streamEnhance(prompt, { ...options, fetch }),
  );
  return { session, calls, history, actions, get state() { return state; } };
}

test("reducer: success path", () => {
  let state = enhancementReducer(initialEnhancementState, { type: "start", requestId: 1 });
  assert.equal(state.phase, "loading");
  state = enhancementReducer(state, { type: "chunk", requestId: 1, text: "Hello " });
  state = enhancementReducer(state, { type: "chunk", requestId: 1, text: "world " });
  assert.equal(state.output, "Hello world ");
  state = enhancementReducer(state, { type: "succeed", requestId: 1, output: "Hello world" });
  assert.deepEqual(state, { phase: "success", requestId: 1, output: "Hello world", partial: false, error: null });
});

test("reducer: updates for an ended or different request are ignored", () => {
  let state = enhancementReducer(initialEnhancementState, { type: "start", requestId: 1 });
  state = enhancementReducer(state, { type: "chunk", requestId: 1, text: "kept" });
  state = enhancementReducer(state, { type: "stop", requestId: 1 });
  const stopped = state;
  for (const late of [
    { type: "chunk", requestId: 1, text: "late" },
    { type: "succeed", requestId: 1, output: "late" },
    { type: "fail", requestId: 1, message: "late" },
    { type: "stop", requestId: 1 },
  ]) {
    state = enhancementReducer(state, late);
  }
  assert.equal(state, stopped, "nothing changes after Stop");
  state = enhancementReducer(state, { type: "start", requestId: 2 });
  assert.equal(enhancementReducer(state, { type: "chunk", requestId: 1, text: "old" }), state);
  assert.equal(enhancementReducer(state, { type: "start", requestId: 3 }), state, "one request at a time");
});

test("reducer: stop and fail keep the partial output, trimmed, and mark it incomplete", () => {
  let state = enhancementReducer(initialEnhancementState, { type: "start", requestId: 1 });
  state = enhancementReducer(state, { type: "chunk", requestId: 1, text: "\n partial  text \n" });
  const stopped = enhancementReducer(state, { type: "stop", requestId: 1 });
  assert.deepEqual([stopped.phase, stopped.output, stopped.partial], ["stopped", "partial  text", true]);
  const failed = enhancementReducer(state, { type: "fail", requestId: 1, message: "boom" });
  assert.deepEqual([failed.phase, failed.output, failed.partial, failed.error], ["error", "partial  text", true, "boom"]);

  const empty = enhancementReducer(initialEnhancementState, { type: "start", requestId: 1 });
  assert.equal(enhancementReducer(empty, { type: "stop", requestId: 1 }).partial, false);
  assert.equal(enhancementReducer(empty, { type: "fail", requestId: 1, message: "x" }).partial, false);
});

test("session: a successful request", async () => {
  const h = harness(sseResponse([sse({ chunk: "Enhanced " }, { chunk: "prompt" }, { done: true })]));
  assert.equal(h.session.start("Write a CSV parser"), true);
  assert.equal(h.state.phase, "loading");
  assert.equal(h.session.busy, true);
  await settle();
  assert.equal(h.state.phase, "success");
  assert.equal(h.state.output, "Enhanced prompt");
  assert.equal(h.session.busy, false);
});

test("session: duplicate submissions are refused while a request runs", async () => {
  const stream = manualResponse();
  const h = harness(stream);
  assert.equal(h.session.start("first"), true);
  assert.equal(h.session.start("second"), false);
  assert.equal(h.session.start("third"), false);
  await settle();
  assert.equal(h.calls.length, 1);
  stream.push(sse({ chunk: "done" }, { done: true }));
  stream.close();
  await settle();
  assert.equal(h.state.phase, "success");
});

test("session: Stop keeps partial output, aborts the request and ignores late data", async () => {
  const stream = manualResponse();
  const h = harness(stream, sseResponse([sse({ chunk: "next" }, { done: true })]));
  h.session.start("a prompt");
  stream.push(sse({ chunk: "partial " }, { chunk: "output" }));
  await settle();
  assert.equal(h.state.output, "partial output");

  h.session.stop();
  assert.equal(h.state.phase, "stopped");
  assert.equal(h.state.output, "partial output");
  assert.equal(h.state.partial, true);
  assert.equal(h.session.busy, false);
  assert.ok(stream.aborted, "the browser request was aborted");

  const actionsAtStop = h.actions.length;
  stream.push(sse({ chunk: " late" }, { done: true }));
  await settle();
  assert.equal(h.state.phase, "stopped");
  assert.equal(h.state.output, "partial output", "no update after Stop");
  assert.deepEqual(h.actions.slice(actionsAtStop), [], "the aborted request reports nothing (not a failure)");

  assert.equal(h.session.start("again"), true, "a new request works after Stop");
  await settle();
  assert.equal(h.state.phase, "success");
  assert.equal(h.state.output, "next");
  assert.equal(h.calls.length, 2);
});

test("session: Stop before any output", async () => {
  const stream = manualResponse();
  const h = harness(stream);
  h.session.start("a prompt");
  await settle();
  h.session.stop();
  assert.equal(h.state.phase, "stopped");
  assert.equal(h.state.output, "");
  assert.equal(h.state.partial, false);
});

test("session: a failure after partial output keeps it; the next request recovers", async () => {
  const message = "The model provider returned a server error. Please try again.";
  const h = harness(
    sseResponse([sse({ chunk: "half " }, { chunk: "done" }, { error: message })]),
    sseResponse([sse({ chunk: "recovered" }, { done: true })]),
  );
  h.session.start("a prompt");
  await settle();
  assert.equal(h.state.phase, "error");
  assert.equal(h.state.error, message);
  assert.equal(h.state.output, "half done");
  assert.equal(h.state.partial, true);

  h.session.start("a prompt");
  await settle();
  assert.equal(h.state.phase, "success");
  assert.equal(h.state.output, "recovered");
  assert.equal(h.state.error, null);
  assert.equal(h.state.partial, false);
});

test("session: network failure, then recovery", async () => {
  const h = harness(new TypeError("fetch failed"), sseResponse([sse({ chunk: "ok" }, { done: true })]));
  h.session.start("a prompt");
  await settle();
  assert.equal(h.state.phase, "error");
  assert.equal(h.state.error, MESSAGES.network);
  h.session.start("a prompt");
  await settle();
  assert.equal(h.state.phase, "success");
});

test("session: no automatic retries", async () => {
  const h = harness(sseResponse([sse({ error: "Too many requests. Please wait a moment and try again." })]));
  h.session.start("a prompt");
  await settle();
  assert.equal(h.state.phase, "error");
  assert.equal(h.calls.length, 1, "exactly one request");
});

test("session: an unexpected exception shows a generic message, never its text", async () => {
  let state = initialEnhancementState;
  const session = createEnhancementSession(
    (action) => (state = enhancementReducer(state, action)),
    () => Promise.reject(new Error("internal detail: token=abc123 at line 42")),
  );
  session.start("a prompt");
  await settle();
  assert.equal(state.phase, "error");
  assert.equal(state.error, MESSAGES.unexpected);

  const throwing = createEnhancementSession(
    (action) => (state = enhancementReducer(state, action)),
    () => {
      throw new Error("synchronous failure");
    },
  );
  assert.equal(throwing.start("a prompt"), true);
  await settle();
  assert.equal(state.error, MESSAGES.unexpected);
  assert.equal(throwing.busy, false);
});
