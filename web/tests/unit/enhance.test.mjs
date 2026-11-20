import assert from "node:assert/strict";
import { test } from "node:test";
import { ENHANCE_URL, EnhanceError, MESSAGES, streamEnhance } from "../../src/api/enhance.ts";
import {
  bytePieces,
  jsonResponse,
  manualResponse,
  scriptedFetch,
  settle,
  sse,
  sseResponse,
  textResponse,
} from "./helpers.mjs";

const LITERAL = [
  "Name columns user_id_field and order_total_amount.\n",
  "Glob: src/**/*.py and *.md; path C:\\Users\\me\\file_v2.txt\n",
  "IMPORTANT:\n```python\nprint('<b>bold</b>' * 2)\n```\n",
  '<script>alert("x")</script> & **not bold** _not italic_ — café ✓ 🚀',
];

async function run(responder, prompt = "Write a CSV parser") {
  const { fetch, calls } = scriptedFetch(responder);
  const chunks = [];
  const controller = new AbortController();
  const promise = streamEnhance(prompt, {
    signal: controller.signal,
    onChunk: (chunk) => chunks.push(chunk),
    fetch,
  });
  return { promise, chunks, calls, controller };
}

async function failure(responder) {
  const { promise, chunks } = await run(responder);
  const error = await promise.then(
    () => assert.fail("expected a failure"),
    (e) => e,
  );
  assert.ok(error instanceof EnhanceError, `not an EnhanceError: ${error}`);
  return { error, chunks };
}

test("sends the existing contract: POST /enhance with {prompt, stream: true}", async () => {
  const { promise, calls } = await run(sseResponse([sse({ chunk: "ok" }, { done: true })]), "My prompt");
  assert.equal(await promise, "ok");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, ENHANCE_URL);
  assert.equal(calls[0].url, "/enhance");
  assert.equal(calls[0].method, "POST");
  assert.equal(calls[0].headers["Content-Type"], "application/json");
  assert.deepEqual(calls[0].body, { prompt: "My prompt", stream: true });
});

test("output is returned literally, whatever the network split (even inside UTF-8 characters)", async () => {
  const body = sse(...LITERAL.map((chunk) => ({ chunk })), { done: true });
  const expected = LITERAL.join("").trim();
  for (const size of [1, 2, 3, 5, 7, 64, body.length]) {
    const { promise, chunks } = await run(sseResponse(bytePieces(body, size)));
    assert.equal(await promise, expected, `pieces of ${size} bytes`);
    assert.equal(chunks.join(""), LITERAL.join(""));
  }
});

test("several frames in one network chunk", async () => {
  const { promise, chunks } = await run(
    sseResponse([sse({ chunk: "a" }, { chunk: "b" }, { chunk: "c" }, { done: true })]),
  );
  assert.equal(await promise, "abc");
  assert.deepEqual(chunks, ["a", "b", "c"]);
});

test("only outer whitespace is trimmed from the final result", async () => {
  const { promise } = await run(sseResponse([sse({ chunk: "\n\n  a\n\n\tb  c  \n" }, { done: true })]));
  assert.equal(await promise, "a\n\n\tb  c");
});

test("an error frame shows the server's safe message, also after partial output", async () => {
  const message = "The model provider is currently unavailable. Please try again later.";
  let result = await failure(sseResponse([sse({ error: message })]));
  assert.equal(result.error.kind, "server");
  assert.equal(result.error.message, message);

  result = await failure(sseResponse([sse({ chunk: "partial " }, { chunk: "text" }, { error: message })]));
  assert.equal(result.error.message, message);
  assert.deepEqual(result.chunks, ["partial ", "text"], "partial output was delivered before the error");
});

test("malformed frames are a protocol error", async () => {
  for (const body of ["data: {not json\n\n", "data: [1, 2]\n\n", 'data: "text"\n\n', "data: null\n\n"]) {
    const { error } = await failure(sseResponse([body]));
    assert.equal(error.kind, "protocol", body);
    assert.equal(error.message, MESSAGES.protocol);
  }
});

test("a response that is not an event stream is a protocol error", async () => {
  const { error } = await failure(textResponse("<html>proxy page</html>", 200));
  assert.equal(error.kind, "protocol");
});

test("HTTP errors use the server's JSON message, or say which status came back", async () => {
  let { error } = await failure(
    jsonResponse({ error: "Empty prompt. Please send a non-empty 'prompt' field." }, 400),
  );
  assert.equal(error.kind, "http");
  assert.equal(error.message, "Empty prompt. Please send a non-empty 'prompt' field.");

  ({ error } = await failure(textResponse("<h1>Internal Server Error</h1>", 500)));
  assert.equal(error.message, "The server returned HTTP 500. Please try again.");

  ({ error } = await failure(jsonResponse({ detail: "x" }, 502)));
  assert.equal(error.message, "The server returned HTTP 502. Please try again.");
});

test("a network failure says the server could not be reached", async () => {
  const { error } = await failure(new TypeError("fetch failed"));
  assert.equal(error.kind, "network");
  assert.equal(error.message, MESSAGES.network);
});

test("a stream that ends without the completion frame is incomplete, never a success", async () => {
  const { error, chunks } = await failure(sseResponse([sse({ chunk: "half an answer" })]));
  assert.equal(error.kind, "incomplete");
  assert.equal(error.message, MESSAGES.incomplete);
  assert.deepEqual(chunks, ["half an answer"]);
});

test("a connection that breaks mid-stream is incomplete", async () => {
  const { error } = await failure(
    sseResponse([sse({ chunk: "a" })], { failWith: new TypeError("terminated") }),
  );
  assert.equal(error.kind, "incomplete");
});

test("completion with no text is reported as empty output", async () => {
  const { error } = await failure(sseResponse([sse({ chunk: "  \n " }, { done: true })]));
  assert.equal(error.kind, "empty");
});

test("long or blank server messages are bounded", async () => {
  let { error } = await failure(sseResponse([sse({ error: "x".repeat(2000) })]));
  assert.ok(error.message.length <= 501);
  ({ error } = await failure(sseResponse([sse({ error: "   " })])));
  assert.equal(error.message, MESSAGES.unexpected);
});

test("cancelling rejects with the abort error and delivers nothing afterwards", async () => {
  const stream = manualResponse();
  const { promise, chunks, controller } = await run(stream);
  stream.push(sse({ chunk: "first" }));
  await settle();
  assert.deepEqual(chunks, ["first"]);
  controller.abort();
  stream.push(sse({ chunk: "late" }, { done: true }));
  const error = await promise.then(
    () => assert.fail("expected the abort to reject"),
    (e) => e,
  );
  assert.equal(error.name, "AbortError");
  assert.ok(!(error instanceof EnhanceError));
  assert.deepEqual(chunks, ["first"], "no data after cancellation");
  assert.ok(stream.aborted);
});

test("frames after the completion frame are ignored", async () => {
  const { promise, chunks } = await run(sseResponse([sse({ chunk: "a" }, { done: true }, { chunk: "b" })]));
  assert.equal(await promise, "a");
  assert.deepEqual(chunks, ["a"]);
});
