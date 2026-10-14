// Behaviour tests for the legacy UI (src/forge/templates/index.html), run against the
// template's real application script in a fake DOM. Run: node --test tests/frontend/
// No network: every request goes to an in-test fake fetch.

import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { FakeEvent, controllableFetch, load, scriptedFetch, settle, sse } from "./fake_dom.mjs";

const TEMPLATE =
  process.env.FORGE_TEMPLATE ||
  fileURLToPath(new URL("../../src/forge/templates/index.html", import.meta.url));

const PROMPT = "Write a Python script that parses CSV files";

async function enhance(ui, prompt = PROMPT) {
  ui.$("raw-input").value = prompt;
  ui.$("enhance-btn").click();
  await settle();
}

function shown(ui) {
  const pre = ui.$("output-text");
  return pre ? pre.textContent : null;
}

async function copy(ui, format) {
  ui.$("copy-btn").click();
  ui.$(format === "json" ? "copy-json" : "copy-text").click();
  await settle();
  return ui.clipboard.at(-1);
}

const LITERAL = [
  "Name columns user_id_field and order_total_amount.\n",
  "Glob: src/**/*.py and *.md; path C:\\Users\\me\\file_v2.txt\n",
  "IMPORTANT:\n```python\nprint('<b>bold</b>' * 2)\n```\n",
  '<script>alert("x")</script> & <img src=x onerror=alert(1)> **not bold** _not italic_',
];

test("output is literal text and identical to what is copied", async () => {
  const ui = load(TEMPLATE, { fetch: scriptedFetch([sse(...LITERAL.map((chunk) => ({ chunk })), { done: true })]).fetch });
  await enhance(ui);
  const expected = LITERAL.join("").trim();
  assert.equal(shown(ui), expected);
  assert.equal(ui.$("output-text").tagName, "PRE");
  assert.equal(await copy(ui, "text"), expected);
  assert.deepEqual(JSON.parse(await copy(ui, "json")), { enhanced_prompt: expected });
});

test("frames split across network chunks, including inside UTF-8 characters", async () => {
  const body = new TextEncoder().encode(sse({ chunk: "Café ✓ résumé " }, { chunk: "naïve — done" }, { done: true }));
  const pieces = [];
  for (let i = 0; i < body.length; i += 3) pieces.push(body.slice(i, i + 3));
  const ui = load(TEMPLATE, { fetch: scriptedFetch(pieces).fetch });
  await enhance(ui);
  assert.equal(shown(ui), "Café ✓ résumé naïve — done");
  assert.equal(ui.$("output-shell").getAttribute("data-state"), "success");
});

test("loading, success and live-region states", async () => {
  const fake = controllableFetch();
  const ui = load(TEMPLATE, { fetch: fake.fetch });
  assert.equal(ui.$("output-shell").getAttribute("data-state"), "idle");
  assert.equal(ui.$("copy-btn").disabled, true);
  ui.$("raw-input").value = PROMPT;
  ui.$("enhance-btn").click();
  await settle();
  assert.equal(ui.$("output-shell").getAttribute("data-state"), "loading");
  assert.equal(ui.$("output").getAttribute("aria-busy"), "true");
  assert.equal(ui.$("enhance-btn").disabled, true);
  assert.equal(ui.$("stop-btn").hidden, false);
  assert.equal(ui.$("enhance-spinner").hidden, false);
  assert.match(ui.$("sr-status").textContent, /Enhancing/);
  fake.streams[0].push(sse({ chunk: "Partial " }));
  await settle();
  assert.equal(shown(ui), "Partial ");
  assert.equal(ui.$("copy-btn").disabled, true, "no copying while streaming");
  fake.streams[0].push(sse({ chunk: "result." }, { done: true }));
  fake.streams[0].close();
  await settle();
  assert.equal(ui.$("output-shell").getAttribute("data-state"), "success");
  assert.equal(ui.$("output").getAttribute("aria-busy"), "false");
  assert.equal(ui.$("stop-btn").hidden, true);
  assert.equal(ui.$("enhance-spinner").hidden, true);
  assert.equal(ui.$("copy-btn").disabled, false);
  assert.match(ui.$("sr-status").textContent, /complete/);
  assert.equal(ui.$("raw-input").value, PROMPT);
});

const BACKEND_ERRORS = [
  "The model provider's rate limit was reached (rate_limit). Please wait and try again.",
  "The model provider did not respond in time (timeout). Please try again.",
  "The model provider is currently unavailable. Please try again later.",
  "The model provider returned a server error. Please try again later.",
  "The model provider rejected the server's credentials.",
  "The model provider rejected the request as invalid.",
  "The model provider returned an invalid response.",
  "The selected model does not support this request.",
  "Too many requests are in progress for this model provider. Please try again shortly.",
  "The model provider request failed unexpectedly.",
  "An internal error occurred while enhancing the prompt.",
];

for (const message of BACKEND_ERRORS) {
  test(`backend error is shown verbatim: ${message.slice(0, 40)}`, async () => {
    const ui = load(TEMPLATE, { fetch: scriptedFetch([sse({ error: message })]).fetch });
    await enhance(ui);
    assert.equal(ui.$("error-message").textContent, message);
    assert.equal(ui.$("output-shell").getAttribute("data-state"), "error");
    assert.ok(ui.$("sr-status").textContent.includes(message), "announced to screen readers");
    assert.equal(ui.$("raw-input").value, PROMPT, "the prompt is preserved");
    assert.equal(ui.$("copy-btn").disabled, true);
  });
}

test("error after partial output, HTTP errors and network failure", async () => {
  let ui = load(TEMPLATE, {
    fetch: scriptedFetch([sse({ chunk: "partial" }, { error: "The model provider returned a server error. Please try again later." })]).fetch,
  });
  await enhance(ui);
  assert.equal(ui.$("error-message").textContent, "The model provider returned a server error. Please try again later.");
  assert.equal(ui.$("output-text") === null, true, "incomplete output is not presented as a result");

  ui = load(TEMPLATE, { fetch: controllableFetch({ status: 400, json: { error: "Empty prompt. Please send a non-empty 'prompt' field." } }).fetch });
  await enhance(ui);
  assert.equal(ui.$("error-message").textContent, "Empty prompt. Please send a non-empty 'prompt' field.");

  ui = load(TEMPLATE, { fetch: controllableFetch({ status: 502 }).fetch });
  await enhance(ui);
  assert.equal(ui.$("error-message").textContent, "The server returned HTTP 502. Please try again.");

  ui = load(TEMPLATE, { fetch: async () => { throw new TypeError("Failed to fetch"); } });
  await enhance(ui);
  assert.match(ui.$("error-message").textContent, /Could not reach the FORGE server/);

  ui = load(TEMPLATE, { fetch: scriptedFetch([sse({ chunk: "cut off" })]).fetch }); // no done frame
  await enhance(ui);
  assert.match(ui.$("error-message").textContent, /connection closed before/);
});

test("retry after a failure runs exactly one new request and succeeds", async () => {
  let calls = 0;
  const fail = scriptedFetch([sse({ error: "The model provider is currently unavailable. Please try again later." })]);
  const ok = scriptedFetch([sse({ chunk: "Recovered." }, { done: true })]);
  const ui = load(TEMPLATE, { fetch: (url, init) => (++calls === 1 ? fail.fetch(url, init) : ok.fetch(url, init)) });
  await enhance(ui);
  ui.$("error-retry").click();
  ui.$("enhance-btn").click(); // disabled while loading: ignored
  await settle();
  assert.equal(calls, 2);
  assert.equal(shown(ui), "Recovered.");
  assert.equal(ui.$("output-shell").getAttribute("data-state"), "success");
});

test("no duplicate concurrent requests", async () => {
  const fake = controllableFetch();
  const ui = load(TEMPLATE, { fetch: fake.fetch });
  ui.$("raw-input").value = PROMPT;
  ui.$("enhance-btn").click();
  ui.document.key("Enter", { ctrlKey: true }, ui.$("raw-input"));
  ui.document.key("Enter", { metaKey: true }, ui.$("raw-input"));
  await settle();
  assert.equal(fake.calls.length, 1);
});

test("stop keeps partial output, ignores later data, and allows a clean new request", async () => {
  const fake = controllableFetch();
  const ui = load(TEMPLATE, { fetch: fake.fetch });
  ui.$("raw-input").value = PROMPT;
  ui.$("enhance-btn").click();
  await settle();
  fake.streams[0].push(sse({ chunk: "First part of the " }));
  await settle();
  ui.$("stop-btn").focus();
  ui.$("stop-btn").click();
  await settle();
  assert.equal(fake.calls[0].signal.aborted, true, "the browser request is aborted");
  assert.equal(ui.document.activeElement.id, "enhance-btn", "focus moves off the hidden Stop button");
  assert.match(ui.$("sr-status").textContent, /stopped/i);
  assert.equal(ui.$("output-shell").getAttribute("data-state"), "stopped");
  assert.equal(shown(ui), "First part of the");
  assert.match(ui.$("output").textContent, /Stopped\. Partial output/);
  assert.equal(await copy(ui, "text"), "First part of the", "the notice is not copied");
  assert.deepEqual(JSON.parse(await copy(ui, "json")), { enhanced_prompt: "First part of the", partial: true });
  assert.equal(ui.$("stop-btn").hidden, true);
  assert.equal(ui.$("raw-input").value, PROMPT);
  fake.streams[0].push(sse({ chunk: "LATE DATA" }, { done: true }));
  await settle();
  assert.equal(shown(ui), "First part of the", "no updates after cancellation");

  ui.$("enhance-btn").click();
  await settle();
  assert.equal(fake.calls.length, 2);
  fake.streams[1].push(sse({ chunk: "Fresh result." }, { done: true }));
  fake.streams[1].close();
  await settle();
  assert.equal(shown(ui), "Fresh result.");
  assert.equal(ui.$("output-shell").getAttribute("data-state"), "success");
  assert.deepEqual(JSON.parse(await copy(ui, "json")), { enhanced_prompt: "Fresh result." });
});

test("stop before any output", async () => {
  const fake = controllableFetch();
  const ui = load(TEMPLATE, { fetch: fake.fetch });
  ui.$("raw-input").value = PROMPT;
  ui.$("enhance-btn").click();
  await settle();
  ui.$("stop-btn").click();
  await settle();
  assert.equal(ui.$("output-shell").getAttribute("data-state"), "stopped");
  assert.match(ui.$("output").textContent, /No output was received/);
  assert.equal(ui.$("copy-btn").disabled, true);
});

test("Ctrl/Cmd+C is not intercepted, so a selected part of the output can be copied", async () => {
  const ui = load(TEMPLATE, { fetch: scriptedFetch([sse({ chunk: "Line one.\nLine two." }, { done: true })]).fetch });
  await enhance(ui);
  const before = ui.clipboard.length;
  for (const modifier of [{ ctrlKey: true }, { metaKey: true }]) {
    const event = ui.document.key("c", modifier, ui.$("output-text"));
    assert.equal(event.defaultPrevented, false, "the browser's own copy (of the selection) runs");
  }
  await settle();
  assert.equal(ui.clipboard.length, before, "the page does not overwrite the clipboard");
});

test("Escape never clears the prompt", async () => {
  const ui = load(TEMPLATE);
  ui.$("raw-input").value = PROMPT;
  ui.$("raw-input").focus();
  ui.document.key("Escape");
  ui.document.key("Escape", {}, ui.document.body);
  assert.equal(ui.$("raw-input").value, PROMPT);
});

test("input validation does not send a request", async () => {
  const fake = controllableFetch();
  const ui = load(TEMPLATE, { fetch: fake.fetch });
  await enhance(ui, "short");
  await enhance(ui, "x".repeat(2001));
  await enhance(ui, "   ");
  assert.equal(fake.calls.length, 0);
  assert.match(ui.$("sr-status").textContent, /Enter a prompt first/);
  const counter = ui.$("char-counter");
  const cases = [
    ["short", "char-counter-warn"],
    ["x".repeat(2001), "char-counter-error"],
    [PROMPT, "char-counter-ok"],
  ];
  for (const [value, cls] of cases) {
    ui.$("raw-input").value = value;
    ui.$("raw-input").dispatchEvent(new FakeEvent("input"));
    assert.equal(counter.classList.contains(cls), true, cls);
    assert.equal(counter.textContent, `${value.length}/2000 chars`);
  }
});

test("shortcuts dialog: native modal, inert background, focus in and back, Escape", () => {
  const ui = load(TEMPLATE);
  const modal = ui.$("shortcuts-modal");
  const trigger = ui.$("shortcuts-trigger");
  assert.equal(modal.tagName, "DIALOG");
  assert.equal(modal.open, false);
  ui.$("shortcuts-close").focus();
  assert.notEqual(ui.document.activeElement.id, "shortcuts-close", "closed dialog is not focusable");

  ui.$("raw-input").value = PROMPT;
  trigger.focus();
  trigger.click();
  assert.equal(modal.open, true);
  assert.equal(modal.modalCalls, 1, "opened with showModal(), so the page behind is inert");
  assert.equal(trigger.getAttribute("aria-expanded"), "true");
  assert.equal(ui.document.activeElement.id, "shortcuts-close", "focus moves into the dialog");
  ui.$("raw-input").focus();
  ui.$("enhance-btn").focus();
  assert.equal(ui.document.activeElement.id, "shortcuts-close", "background cannot take focus");
  ui.document.key("/", {}, ui.document.activeElement);
  ui.document.key("?", {}, ui.document.activeElement);
  assert.equal(ui.document.activeElement.id, "shortcuts-close", "page shortcuts are off while open");

  ui.document.key("Escape");
  assert.equal(modal.open, false, "Escape closes the dialog");
  assert.equal(trigger.getAttribute("aria-expanded"), "false");
  assert.equal(ui.document.activeElement.id, "shortcuts-trigger", "focus returns to the trigger");
  assert.equal(ui.$("raw-input").value, PROMPT, "Escape does not clear the prompt");
  ui.$("raw-input").focus();
  assert.equal(ui.document.activeElement.id, "raw-input", "the page is interactive again");

  ui.document.key("?", {}, ui.document.body);
  assert.equal(modal.open, true, "? opens the dialog");
  ui.$("shortcuts-close").click();
  assert.equal(modal.open, false, "the close button closes it");

  trigger.focus();
  trigger.click();
  modal.dispatchEvent(new FakeEvent("click")); // click on the backdrop area
  assert.equal(modal.open, false, "a backdrop click closes it");
  assert.equal(ui.document.activeElement.id, "shortcuts-trigger");
  trigger.click();
  ui.$("shortcuts-close").dispatchEvent(new FakeEvent("keydown", { key: "Tab" })); // inside
  assert.equal(modal.open, true, "keys inside the panel do not close it");
  ui.$("shortcuts-close").click();

  ui.$("raw-input").focus();
  ui.document.key("?");
  assert.equal(modal.open, false, "typing ? in the prompt does not open it");
  ui.document.key("/", {}, ui.document.body);
  assert.equal(ui.document.activeElement.id, "raw-input", "/ focuses the prompt");
});

test("copy menu: disabled without output, keyboard navigation, Escape, expanded state", async () => {
  const ui = load(TEMPLATE, { fetch: scriptedFetch([sse({ chunk: "Copy me." }, { done: true })]).fetch });
  const button = ui.$("copy-btn");
  const dropdown = ui.$("copy-dropdown");
  button.click();
  assert.equal(dropdown.classList.contains("open"), false, "no menu without output");
  await enhance(ui);
  button.focus();
  ui.document.key("ArrowDown");
  assert.equal(dropdown.classList.contains("open"), true);
  assert.equal(ui.$("copy-menu").hidden, false, "menu is shown (display) before its item is focused");
  assert.equal(button.getAttribute("aria-expanded"), "true");
  assert.equal(ui.document.activeElement.id, "copy-text");
  ui.document.key("ArrowDown");
  assert.equal(ui.document.activeElement.id, "copy-json");
  ui.document.key("ArrowDown");
  assert.equal(ui.document.activeElement.id, "copy-text", "wraps around");
  ui.document.key("End");
  assert.equal(ui.document.activeElement.id, "copy-json");
  ui.document.key("Home");
  assert.equal(ui.document.activeElement.id, "copy-text");
  ui.document.key("Escape");
  assert.equal(dropdown.classList.contains("open"), false);
  assert.equal(ui.$("copy-menu").hidden, true, "closed menu is display: none");
  assert.equal(button.getAttribute("aria-expanded"), "false");
  assert.equal(ui.document.activeElement.id, button.id, "focus returns to the Copy button");

  button.click();
  ui.document.activeElement.click(); // "Copy text"
  await settle();
  assert.equal(ui.clipboard.at(-1), "Copy me.");
  assert.equal(dropdown.classList.contains("open"), false);
  assert.equal(ui.document.activeElement.id, button.id);
  assert.match(ui.$("sr-status").textContent, /Copied/);

  button.click();
  ui.document.body.click(); // outside click closes
  assert.equal(dropdown.classList.contains("open"), false);
});

test("keyboard hints match the device", () => {
  const touch = load(TEMPLATE, { touch: true });
  assert.equal(touch.$("enhance-status").textContent, "Tap Enhance Prompt to enhance");
  const mac = load(TEMPLATE, { mac: true });
  assert.match(mac.$("enhance-status").textContent, /⌘Enter/);
  assert.equal(mac.$("modal-mod-key").textContent, "⌘");
  const pc = load(TEMPLATE);
  assert.match(pc.$("enhance-status").textContent, /CtrlEnter/);
  assert.equal(pc.$("footer-year").textContent, String(new Date().getFullYear()));
});

test("without the Clipboard API, Copy explains what to do instead of failing", async () => {
  const { fetch } = scriptedFetch([sse({ chunk: "Copy me." }, { done: true })]);
  const ui = load(TEMPLATE, { fetch, clipboardApi: false });
  await enhance(ui);
  ui.$("copy-btn").click();
  ui.$("copy-text").click();
  await settle();
  assert.equal(ui.clipboard.length, 0);
  assert.match(ui.$("sr-status").textContent, /unavailable.*Select the text and copy it manually/);
  assert.equal(shown(ui), "Copy me.", "output is untouched");
});
