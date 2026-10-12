// Runs the real inline application script from the legacy template under Node, with a
// minimal fake DOM and a stubbed fetch that streams SSE frames, then exercises
// "Enhance" and the "Copy as JSON" / "Copy as Markdown" actions.
//
// Usage: node legacy_ui_export.mjs <path/to/index.html>   (exit code 0 = pass)

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const html = readFileSync(process.argv[2], "utf8");
const appScript = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)]
  .map((m) => m[1])
  .find((s) => s.includes('querySelector(".enhance-btn")'));
assert.ok(appScript, "application script not found in template");

class ClassList {
  constructor() { this.items = new Set(); }
  add(...c) { c.forEach((x) => this.items.add(x)); }
  remove(...c) { c.forEach((x) => this.items.delete(x)); }
  toggle(c, force) {
    const on = force === undefined ? !this.items.has(c) : force;
    if (on) this.items.add(c); else this.items.delete(c);
    return on;
  }
  contains(c) { return this.items.has(c); }
}

class El {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase();
    this.childNodes = [];
    this.listeners = {};
    this.style = {};
    this.dataset = {};
    this.classList = new ClassList();
    this.textContent = "";
    this.innerHTML = "";
    this.className = "";
    this.value = "";
    this.disabled = false;
    this.lookups = new Map();
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatch(type) {
    const event = { type, stopPropagation() {}, preventDefault() {} };
    return Promise.all((this.listeners[type] || []).map((fn) => fn(event)));
  }
  click() { return this.dispatch("click"); }
  querySelector(sel) {
    if (!this.lookups.has(sel)) this.lookups.set(sel, new El());
    return this.lookups.get(sel);
  }
  querySelectorAll() { return []; }
  closest(sel) { return this.querySelector(`closest:${sel}`); }
  appendChild(child) { this.childNodes.push(child); return child; }
  append(...children) { children.forEach((c) => this.appendChild(c)); }
  replaceChildren(...children) { this.childNodes = [...children]; }
  remove() {}
  focus() {}
  setSelectionRange() {}
}

const byId = new Map();
const bySelector = new Map();
const copyItems = ["json", "markdown"].map((format) => {
  const item = new El("button");
  item.dataset.format = format;
  return item;
});
const document = {
  getElementById(id) {
    if (!byId.has(id)) byId.set(id, new El());
    return byId.get(id);
  },
  querySelector(sel) {
    if (!bySelector.has(sel)) bySelector.set(sel, new El());
    return bySelector.get(sel);
  },
  querySelectorAll(sel) { return sel === ".copy-dropdown-item" ? copyItems : []; },
  createElement(tag) { return new El(tag); },
  createDocumentFragment() { return new El("#fragment"); },
  addEventListener() {},
};

// Two SSE frames, the second split across network chunks, then the done frame.
const frames = [
  'data: {"chunk": "Act as a senior data engineer.\\n"}\n\n',
  'data: {"chunk": "Parse the CSV ',
  'files robustly.  "}\n\ndata: {"done": true}\n\n',
];
const expectedPrompt = "Act as a senior data engineer.\nParse the CSV files robustly.";

const fetchCalls = [];
const clipboard = [];
const context = vm.createContext({
  document,
  navigator: { platform: "Linux x86_64", clipboard: { writeText: async (t) => { clipboard.push(t); } } },
  console,
  setTimeout,
  clearTimeout,
  TextDecoder,
  requestAnimationFrame: (cb) => cb(),
  fetch: async (url, init) => {
    fetchCalls.push({ url, method: init.method, body: JSON.parse(init.body) });
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        frames.forEach((f) => controller.enqueue(encoder.encode(f)));
        controller.close();
      },
    });
    return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
  },
});

try {
  vm.runInContext(appScript, context);
  const input = document.getElementById("raw-input");
  input.value = "Write a Python script that parses CSV files";
  await document.querySelector(".enhance-btn").click();

  assert.deepEqual(fetchCalls, [
    { url: "/enhance", method: "POST", body: { prompt: input.value, stream: true } },
  ]);

  await copyItems[0].click(); // Copy as JSON
  await new Promise((r) => setTimeout(r, 0));
  const exportedJson = clipboard.at(-1);
  assert.ok(exportedJson, "Copy as JSON wrote nothing to the clipboard");
  assert.deepEqual(JSON.parse(exportedJson), { enhanced_prompt: expectedPrompt });
  for (const fabricated of ["98%", "0.98", "confidence", "score"]) {
    assert.ok(!exportedJson.includes(fabricated), `JSON export contains ${fabricated}`);
  }

  await copyItems[1].click(); // Copy as Markdown (unchanged behavior)
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(clipboard.at(-1), expectedPrompt);

  console.log("PASS legacy UI export:", JSON.stringify(JSON.parse(exportedJson)));
  process.exit(0);
} catch (error) {
  console.error("FAIL legacy UI export:", error.message);
  process.exit(1);
}
