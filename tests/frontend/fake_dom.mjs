// A small fake DOM for running the legacy template's real application script under Node
// (no browser, no npm dependencies). It models what the script uses: elements by id,
// attributes, classes, text content, focus, bubbling events and the `hidden`/`disabled`
// properties. Setting or reading `innerHTML` throws, so any use of it fails the tests.

import { readFileSync } from "node:fs";
import vm from "node:vm";

export function appScript(templatePath) {
  const html = readFileSync(templatePath, "utf8");
  const match = /<script data-forge="app">([\s\S]*?)<\/script>/.exec(html);
  if (!match) throw new Error('application script (<script data-forge="app">) not found');
  return match[1];
}

export class FakeEvent {
  constructor(type, init = {}) {
    Object.assign(this, init);
    this.type = type;
    this.defaultPrevented = false;
    this.propagationStopped = false;
  }
  preventDefault() { this.defaultPrevented = true; }
  stopPropagation() { this.propagationStopped = true; }
}

class ClassList {
  constructor() { this.items = new Set(); }
  add(...c) { c.forEach((x) => this.items.add(x)); }
  remove(...c) { c.forEach((x) => this.items.delete(x)); }
  toggle(c, force) {
    const on = force === undefined ? !this.items.has(c) : Boolean(force);
    if (on) this.items.add(c); else this.items.delete(c);
    return on;
  }
  contains(c) { return this.items.has(c); }
}

export class FakeElement {
  constructor(doc, tag) {
    this.ownerDocument = doc;
    this.tagName = tag.toUpperCase();
    this.parentNode = null;
    this.childNodes = [];
    this.listeners = {};
    this.attributes = new Map();
    this.classList = new ClassList();
    this.style = { setProperty() {} };
    this.dataset = {};
    this.value = "";
    this.type = "";
    this.disabled = false;
    this.hidden = false;
    this.isContentEditable = false;
    this.scrollTop = 0;
    this.scrollHeight = 0;
    this.clientHeight = 0;
    this._text = "";
    this._id = "";
  }
  get id() { return this._id; }
  set id(value) {
    this._id = value;
    if (value) this.ownerDocument._ids.set(value, this);
  }
  get className() { return [...this.classList.items].join(" "); }
  set className(value) {
    this.classList.items = new Set(String(value).split(/\s+/).filter(Boolean));
  }
  get innerHTML() { throw new Error("innerHTML must not be used"); }
  set innerHTML(_value) { throw new Error("innerHTML must not be used"); }
  get textContent() { return this._text + this.childNodes.map((c) => c.textContent).join(""); }
  set textContent(value) {
    this.childNodes.forEach((c) => { c.parentNode = null; });
    this.childNodes = [];
    this._text = String(value);
  }
  get children() { return this.childNodes; }
  appendChild(child) {
    if (child.parentNode) child.parentNode._removeChild(child);
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }
  append(...children) {
    children.forEach((c) => {
      if (typeof c === "string") {
        const text = new FakeElement(this.ownerDocument, "#text");
        text._text = c;
        this.appendChild(text);
      } else this.appendChild(c);
    });
  }
  replaceChildren(...children) {
    this.childNodes.forEach((c) => { c.parentNode = null; });
    this.childNodes = [];
    this._text = "";
    this.append(...children);
  }
  remove() { if (this.parentNode) this.parentNode._removeChild(this); }
  _removeChild(child) {
    this.childNodes = this.childNodes.filter((c) => c !== child);
    child.parentNode = null;
  }
  contains(node) {
    for (let n = node; n; n = n.parentNode) if (n === this) return true;
    return false;
  }
  setAttribute(name, value) {
    if (name === "hidden") this.hidden = true;
    else if (name === "disabled") this.disabled = true;
    else if (name === "id") this.id = String(value);
    else this.attributes.set(name, String(value));
  }
  getAttribute(name) {
    if (name === "hidden") return this.hidden ? "" : null;
    if (name === "disabled") return this.disabled ? "" : null;
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }
  hasAttribute(name) { return this.getAttribute(name) !== null; }
  removeAttribute(name) {
    if (name === "hidden") this.hidden = false;
    else if (name === "disabled") this.disabled = false;
    else this.attributes.delete(name);
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  removeEventListener(type, fn) {
    this.listeners[type] = (this.listeners[type] || []).filter((f) => f !== fn);
  }
  dispatchEvent(event) {
    event.target ||= this;
    for (let node = this; node && !event.propagationStopped; node = node.parentNode) {
      for (const fn of node.listeners[event.type] || []) fn.call(node, event);
    }
    if (!event.propagationStopped) this.ownerDocument._dispatchDocument(event);
    return !event.defaultPrevented;
  }
  click() {
    if (this.disabled) return; // like browsers: disabled controls ignore click()
    this.dispatchEvent(new FakeEvent("click"));
  }
  focus() {
    if (this.disabled) return;
    for (let n = this; n; n = n.parentNode) {
      if (n.hidden || n.hasAttribute("inert")) return; // display: none or inert ancestors
    }
    const modal = this.ownerDocument.modalDialog;
    if (modal && !modal.contains(this)) return; // like browsers: the page behind is inert
    if (this.tagName === "DIALOG" && !this.hasAttribute("open")) return;
    for (let n = this.parentNode; n; n = n.parentNode) {
      if (n.tagName === "DIALOG" && !n.hasAttribute("open")) return; // closed dialog: display none
    }
    this.ownerDocument.activeElement = this;
  }
  setSelectionRange() {}
  getBoundingClientRect() { return { left: 0, top: 0 }; }
  closest() { return null; }
}

/** <dialog> with the parts of the HTML spec the page relies on. */
export class FakeDialog extends FakeElement {
  constructor(doc) {
    super(doc, "dialog");
    this.modalCalls = 0;
  }
  get open() { return this.hasAttribute("open"); }
  showModal() {
    if (this.open) throw new Error("InvalidStateError: dialog already open");
    this.modalCalls += 1;
    this.attributes.set("open", "");
    this.ownerDocument.modalDialog = this;
  }
  close() {
    if (!this.open) return;
    this.attributes.delete("open");
    if (this.ownerDocument.modalDialog === this) this.ownerDocument.modalDialog = null;
    this.dispatchEvent(new FakeEvent("close"));
  }
}

export class FakeDocument {
  constructor() {
    this._ids = new Map();
    this.listeners = {};
    this.body = new FakeElement(this, "body");
    this.documentElement = new FakeElement(this, "html");
    this.activeElement = this.body;
    this.modalDialog = null;
  }
  getElementById(id) {
    const node = this._ids.get(id);
    return node && node.id === id && this.body.contains(node) ? node : null; // connected only
  }
  querySelectorAll() { return []; }
  createElement(tag) {
    return tag.toLowerCase() === "dialog" ? new FakeDialog(this) : new FakeElement(this, tag);
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  _dispatchDocument(event) {
    for (const fn of this.listeners[event.type] || []) {
      if (event.propagationStopped) break;
      fn.call(this, event);
    }
  }
  /** Fire a keydown at the focused element (or at `target`), like a real key press. */
  key(key, init = {}, target = this.activeElement) {
    const event = new FakeEvent("keydown", { key, ...init });
    target.dispatchEvent(event);
    // Browsers close a modal dialog on Escape via a cancelable "cancel" event.
    const modal = this.modalDialog;
    if (key === "Escape" && modal && !event.defaultPrevented) {
      const cancel = new FakeEvent("cancel");
      modal.dispatchEvent(cancel);
      if (!cancel.defaultPrevented) modal.close();
    }
    return event;
  }
}

// Mirrors the ids, tags and nesting the application script relies on in index.html
// (tests/test_legacy_ui.py checks that every id the script uses exists in the template).
const LAYOUT = [
  ["shortcuts-trigger", "button", null],
  ["raw-input", "textarea", null],
  ["char-counter", "span", null],
  ["clear-input", "button", null],
  ["enhance-status", "p", null],
  ["stop-btn", "button", null],
  ["enhance-btn", "button", null],
  ["enhance-label", "span", "enhance-btn"],
  ["enhance-spinner", "span", "enhance-btn"],
  ["enhance-arrow", "span", "enhance-btn"],
  ["output-shell", "div", null],
  ["copy-dropdown", "div", "output-shell"],
  ["copy-btn", "button", "copy-dropdown"],
  ["copy-icon", "span", "copy-btn"],
  ["copy-label", "span", "copy-btn"],
  ["copy-menu", "div", "copy-dropdown"],
  ["copy-text", "button", "copy-menu"],
  ["copy-json", "button", "copy-menu"],
  ["output", "div", "output-shell"],
  ["sr-status", "p", null],
  ["toast-container", "div", null],
  ["shortcuts-modal", "dialog", null],
  ["shortcuts-close", "button", "shortcuts-modal"],
  ["modal-mod-key", "kbd", "shortcuts-modal"],
  ["footer-year", "span", null],
];

function addElements(doc, include) {
  for (const [id, tag, parent] of LAYOUT) {
    if (!include(id)) continue;
    const node = doc.createElement(tag);
    node.id = id;
    (parent ? doc.getElementById(parent) : doc.body).appendChild(node);
    if (id === "copy-text") node.dataset.format = "text";
    if (id === "copy-json") node.dataset.format = "json";
    if (id === "copy-btn") node.disabled = true;
    if (id === "stop-btn" || id === "copy-menu") node.hidden = true;
  }
}

export function buildDocument() {
  const doc = new FakeDocument();
  addElements(doc, () => true);
  doc.readyState = "complete";
  return doc;
}

const encoder = new TextEncoder();

function abortError() {
  return new DOMException("The operation was aborted.", "AbortError");
}

/** A fetch whose response body is controlled by the test: push(), close(), fail(). */
export function controllableFetch({ status = 200, json = null } = {}) {
  const calls = [];
  const streams = [];
  const fetch = async (url, init) => {
    if (init.signal && init.signal.aborted) throw abortError();
    calls.push({ url, method: init.method, body: JSON.parse(init.body), signal: init.signal });
    if (json !== null || status !== 200) {
      return new Response(json === null ? "oops" : JSON.stringify(json), {
        status,
        headers: { "content-type": json === null ? "text/plain" : "application/json" },
      });
    }
    let controller;
    const body = new ReadableStream({ start(c) { controller = c; } });
    const handle = {
      closed: false,
      push(text) { if (!handle.closed) controller.enqueue(typeof text === "string" ? encoder.encode(text) : text); },
      close() { if (!handle.closed) { handle.closed = true; controller.close(); } },
    };
    if (init.signal) {
      init.signal.addEventListener("abort", () => {
        if (!handle.closed) { handle.closed = true; controller.error(abortError()); }
      });
    }
    streams.push(handle);
    return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
  };
  return { fetch, calls, streams };
}

/** A fetch that streams the given pieces (strings or byte arrays) and closes. */
export function scriptedFetch(pieces, options) {
  const fake = controllableFetch(options);
  const fetch = async (url, init) => {
    const response = await fake.fetch(url, init);
    const stream = fake.streams.at(-1);
    if (stream) {
      pieces.forEach((p) => stream.push(p));
      stream.close();
    }
    return response;
  };
  return { ...fake, fetch };
}

export function sse(...events) {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
}

/** Load the application script into a fresh fake browser. */
export function load(templatePath, { fetch, touch = false, mac = false, clipboardApi = true } = {}) {
  // Emulate parsing: the script runs when only the elements *before* it exist, then the rest
  // of the page is added and DOMContentLoaded fires (as in a browser).
  const html = readFileSync(templatePath, "utf8");
  const scriptAt = html.indexOf('<script data-forge="app">');
  const beforeScript = (id) => {
    const at = html.indexOf(`id="${id}"`);
    return at !== -1 && at < scriptAt;
  };
  const document = new FakeDocument();
  document.readyState = "loading";
  addElements(document, beforeScript);
  const clipboard = [];
  const timers = [];
  const context = vm.createContext({
    document,
    navigator: {
      platform: mac ? "MacIntel" : "Win32",
      // No Clipboard API on insecure (plain-HTTP, non-localhost) pages.
      clipboard: clipboardApi ? { writeText: async (text) => { clipboard.push(text); } } : undefined,
    },
    console,
    setTimeout: (fn, ms) => { timers.push(fn); return timers.length; },
    clearTimeout() {},
    TextDecoder,
    AbortController,
    requestAnimationFrame: (cb) => { cb(); return 1; },
    matchMedia: (query) => ({ matches: touch && query.includes("coarse"), addEventListener() {} }),
    fetch: fetch || (async () => { throw new Error("no fetch configured"); }),
  });
  context.window = context;
  vm.runInContext(appScript(templatePath), context);
  addElements(document, (id) => !beforeScript(id));
  document.readyState = "interactive";
  document._dispatchDocument(new FakeEvent("DOMContentLoaded"));
  const $ = (id) => document.getElementById(id);
  return { document, $, clipboard, context };
}

/** Let pending promises, stream reads and fetch callbacks run. */
export async function settle(rounds = 40) {
  for (let i = 0; i < rounds; i++) await new Promise((resolve) => setImmediate(resolve));
}
