// Real-browser check of the built frontend (/app/) in headless Chrome, driven over the
// DevTools protocol with Node built-ins only (no browser-automation dependency).
//
// Usage: node app.browser.mjs <chrome-executable> <base-url> <screenshot-dir>
// Run by tests/test_web_frontend.py (FORGE_BROWSER_TESTS=1) against Flask with a scripted
// fake provider. The browser can resolve only 127.0.0.1: nothing leaves the machine.
// Prompt markers understood by that fake provider: MARK-SLOW (40 chunks, 0.2 s apart),
// MARK-ERROR (provider unavailable), MARK-FLAKY (fails once per prompt, then succeeds),
// MARK-PARTIAL (two chunks, then an error frame).
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [chromePath, base, outDir] = process.argv.slice(2);
if (!chromePath || !base || !outDir) {
  console.error("usage: node app.browser.mjs <chrome> <base-url> <screenshot-dir>");
  process.exit(2);
}
mkdirSync(outDir, { recursive: true });
const APP = `${base}/app/`;
const profile = mkdtempSync(join(tmpdir(), "forge-web-cdp-"));
const chrome = spawn(
  chromePath,
  [
    "--headless=new",
    "--remote-debugging-port=0",
    `--user-data-dir=${profile}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1",
    "--window-size=1280,900",
    "about:blank",
  ],
  { stdio: "ignore" },
);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok: Boolean(ok) });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail && !ok ? `  — ${detail}` : ""}`);
}

const EXPECTED = [
  "Act as a senior data engineer.\n",
  "Use user_id_field and src/**/*.py; keep <b>tags</b> & **asterisks** _as typed_.\n",
  "```python\nprint('café ✓')\n```\n",
  "IMPORTANT: copy exactly.",
]
  .join("")
  .trim();

// ── DevTools protocol plumbing ──────────────────────────────────────────────
async function devtoolsPort() {
  const file = join(profile, "DevToolsActivePort");
  for (let i = 0; i < 150; i++) {
    if (existsSync(file)) return readFileSync(file, "utf8").split("\n")[0].trim();
    await sleep(100);
  }
  throw new Error("Chrome did not start");
}

function connect(url) {
  const ws = new WebSocket(url);
  let id = 0;
  const pending = new Map();
  const listeners = [];
  ws.onmessage = (message) => {
    const msg = JSON.parse(message.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else resolve(msg.result);
    } else if (msg.method) listeners.forEach((fn) => fn(msg));
  };
  const opened = new Promise((resolve) => (ws.onopen = resolve));
  return {
    opened,
    send: (method, params = {}) =>
      new Promise((resolve, reject) => {
        const n = ++id;
        pending.set(n, { resolve, reject });
        ws.send(JSON.stringify({ id: n, method, params }));
      }),
    on: (fn) => listeners.push(fn),
    close: () => ws.close(),
  };
}

let page;
async function evaluate(expression) {
  const r = await page.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) {
    throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  }
  return r.result.value;
}
async function waitFor(expression, timeout = 8000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (await evaluate(expression)) return true;
    await sleep(40);
  }
  return false;
}
const q = (selector) => JSON.stringify(selector);
async function click(selector) {
  const box = await evaluate(`(() => { const el = document.querySelector(${q(selector)});
    if (!el) return null; el.scrollIntoView({ block: "nearest" }); const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
  if (!box) throw new Error(`no element ${selector}`);
  await clickAt(box.x, box.y);
}
async function clickAt(x, y) {
  for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) {
    await page.send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 });
  }
}
const KEYS = {
  Enter: { key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: "\r" },
  Escape: { key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 },
  Tab: { key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 },
  ArrowDown: { key: "ArrowDown", code: "ArrowDown", windowsVirtualKeyCode: 40 },
  ArrowUp: { key: "ArrowUp", code: "ArrowUp", windowsVirtualKeyCode: 38 },
  Home: { key: "Home", code: "Home", windowsVirtualKeyCode: 36 },
  End: { key: "End", code: "End", windowsVirtualKeyCode: 35 },
  "?": { key: "?", code: "Slash", windowsVirtualKeyCode: 191, text: "?", modifiers: 8 },
  "/": { key: "/", code: "Slash", windowsVirtualKeyCode: 191, text: "/" },
};
async function press(name, extra = {}) {
  const k = { ...KEYS[name], ...extra };
  await page.send("Input.dispatchKeyEvent", { type: k.text ? "keyDown" : "rawKeyDown", ...k });
  await page.send("Input.dispatchKeyEvent", { type: "keyUp", ...k, text: undefined });
}
const CTRL = 2;
const SHIFT = 8;
async function setPrompt(text) {
  await evaluate(`(() => { const t = document.querySelector("#prompt-input"); t.focus(); t.select(); })()`);
  if (text === "") await page.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: "Delete", code: "Delete", windowsVirtualKeyCode: 46 });
  else await page.send("Input.insertText", { text });
  await sleep(30);
}
const phase = () => evaluate(`document.querySelector(".output-shell").dataset.state`);
const prompt = () => evaluate(`document.querySelector("#prompt-input").value`);
const focused = () =>
  evaluate(`(() => { const a = document.activeElement; if (!a) return null;
    return a.id || (a.getAttribute("role") === "menuitem" ? "item:" + a.textContent.trim() : a.className || a.tagName); })()`);
const announced = () => evaluate(`document.querySelector('[role="status"]').textContent`);
const clipboard = async () => (await evaluate(`navigator.clipboard.readText()`)).replaceAll("\r", "");
const server = async () => (await fetch(`${base}/__test/state`)).json();
async function screenshot(name) {
  const shot = await page.send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(outDir, `${name}.png`), Buffer.from(shot.data, "base64"));
}
async function load(url = APP) {
  await page.send("Page.navigate", { url });
  await waitFor(`document.readyState === "complete"`);
  await waitFor(`!!document.querySelector(".app") || !!document.querySelector(".boot")`);
  await sleep(500); // entrance animation
}
async function submitAndWait(text, until = "success") {
  await setPrompt(text);
  await click(".enhance-btn");
  return waitFor(`document.querySelector(".output-shell").dataset.state === ${q(until)}`);
}
async function useMenuItem(index) {
  await click("#copy-btn");
  await sleep(250);
  await click(`#copy-menu-list [role="menuitem"]:nth-child(${index + 1})`);
  await sleep(300);
}

// ── The checks ──────────────────────────────────────────────────────────────
const consoleProblems = [];
const foreignRequests = [];
try {
  const port = await devtoolsPort();
  const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
  const browser = connect(version.webSocketDebuggerUrl);
  await browser.opened;
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" })).json();
  page = connect(target.webSocketDebuggerUrl);
  await page.opened;
  page.on((msg) => {
    if (msg.method === "Runtime.exceptionThrown") {
      consoleProblems.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
    }
    if (msg.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(msg.params.type)) {
      consoleProblems.push(msg.params.args.map((a) => a.value ?? a.description ?? "").join(" "));
    }
    if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
      consoleProblems.push(`${msg.params.entry.text} ${msg.params.entry.url || ""}`);
    }
    if (msg.method === "Network.requestWillBeSent") {
      const url = msg.params.request.url;
      if (!url.startsWith(base) && !url.startsWith("data:")) foreignRequests.push(url);
    }
  });
  for (const domain of ["Runtime", "Log", "Page", "Network"]) await page.send(`${domain}.enable`);
  await page.send("Emulation.setFocusEmulationEnabled", { enabled: true });
  await browser.send("Browser.grantPermissions", {
    origin: base,
    permissions: ["clipboardReadWrite", "clipboardSanitizedWrite"],
  });
  console.log(`${version.Browser}; ${APP}`);

  // 1. Loads, renders, native cursor
  await load();
  const loaded = await evaluate(`({ app: !!document.querySelector(".app"), boot: !!document.querySelector(".boot"),
    title: document.title, h1: document.querySelector("h1")?.textContent, state: document.querySelector(".output-shell")?.dataset.state,
    cursor: getComputedStyle(document.querySelector("#prompt-input")).cursor,
    bg: getComputedStyle(document.body).backgroundColor, accent: getComputedStyle(document.querySelector(".brand")).color })`);
  check("app renders (React mounted, boot shell replaced)", loaded.app && !loaded.boot && loaded.state === "idle", JSON.stringify(loaded));
  check("title and heading", loaded.title === "FORGE — Prompt Engine" && loaded.h1 === "Elevate your Vision", JSON.stringify(loaded));
  check("dark surface and champagne accent from local CSS", loaded.bg === "rgb(6, 6, 8)" && loaded.accent === "rgb(197, 168, 128)", JSON.stringify(loaded));
  check("native text cursor in the editor", ["auto", "text"].includes(loaded.cursor), loaded.cursor);
  await screenshot("01-idle");

  // 2. Validation (no request is sent)
  const callsBefore = (await server()).calls;
  await click(".enhance-btn");
  await sleep(100);
  let v = await evaluate(`({ error: document.querySelector("#prompt-error")?.textContent,
    invalid: document.querySelector("#prompt-input").getAttribute("aria-invalid"), focus: document.activeElement.id })`);
  check("empty prompt: message, aria-invalid, focus on the editor", v.error === "Enter a prompt to enhance." && v.invalid === "true" && v.focus === "prompt-input", JSON.stringify(v));
  check("empty prompt is announced", (await announced()).includes("Enter a prompt to enhance."));
  await setPrompt("too short");
  await click(".enhance-btn");
  await sleep(100);
  v = await evaluate(`document.querySelector("#prompt-error")?.textContent`);
  check("too-short prompt is rejected", /at least 10 characters/.test(v ?? ""), v);
  await setPrompt("a".repeat(2001));
  await sleep(100);
  v = await evaluate(`({ level: document.querySelector("#prompt-counter").dataset.level, text: document.querySelector("#prompt-counter").textContent })`);
  check("over the limit: counter shows the error level", v.level === "over" && v.text.startsWith("2,001 / 2,000"), JSON.stringify(v));
  check("crossing the limit is announced", (await announced()).includes("over the 2,000-character limit"));
  await click(".enhance-btn");
  await sleep(100);
  v = await evaluate(`document.querySelector("#prompt-error")?.textContent`);
  check("over-limit prompt is rejected with the exact excess", v === "The prompt is 2,001 characters; the limit is 2,000. Remove 1 to continue.", v);
  check("validation never sends a request", (await server()).calls === callsBefore);

  // 3. Success with Ctrl+Enter; literal output; copy
  await setPrompt("Write a Python script that parses CSV files");
  await press("Enter", { modifiers: CTRL, text: undefined });
  check("Ctrl+Enter in the editor enhances", await waitFor(`document.querySelector(".output-shell").dataset.state === "success"`));
  const out = await evaluate(`(() => { const p = document.querySelector("#output-text");
    return { text: p.textContent, tag: p.tagName, children: p.childElementCount, ws: getComputedStyle(p).whiteSpace }; })()`);
  check("output is literal text (tags, Markdown, paths, fences)", out.text === EXPECTED && out.tag === "PRE" && out.children === 0, JSON.stringify({ ...out, text: out.text.slice(0, 60) }));
  check("whitespace and line breaks preserved", out.ws === "pre-wrap", out.ws);
  check("completion is announced", (await announced()).includes("Enhancement complete"));
  await screenshot("02-success");
  await useMenuItem(0);
  check("Copy text puts exactly the displayed text on the clipboard", (await clipboard()) === EXPECTED);
  v = await evaluate(`({ note: document.querySelector(".copy-note")?.textContent, label: document.querySelector("#copy-btn").textContent })`);
  check("copy feedback (note and button label)", v.note === "Copied to clipboard." && v.label.includes("Copied"), JSON.stringify(v));
  await useMenuItem(1);
  check("Copy as JSON", JSON.stringify(JSON.parse(await clipboard())) === JSON.stringify({ enhanced_prompt: EXPECTED }));
  await evaluate(`(() => { const t = document.querySelector("#output-text").firstChild; const r = document.createRange();
    r.setStart(t, 0); r.setEnd(t, 30); const s = getSelection(); s.removeAllRanges(); s.addRange(r); })()`);
  await page.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: "c", code: "KeyC", windowsVirtualKeyCode: 67, modifiers: CTRL, commands: ["copy"] });
  await page.send("Input.dispatchKeyEvent", { type: "keyUp", key: "c", code: "KeyC", windowsVirtualKeyCode: 67, modifiers: CTRL });
  await sleep(150);
  check("Ctrl+C copies the selected part (native copy not intercepted)", (await clipboard()) === EXPECTED.slice(0, 30));

  // 4. Enter and Escape in the editor behave natively; the prompt is kept
  await setPrompt("Line one of a prompt");
  const before = (await server()).calls;
  await page.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: "\r" });
  await page.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
  await press("Escape");
  await sleep(100);
  check("Enter inserts a newline, not a request", (await prompt()) === "Line one of a prompt\n" && (await server()).calls === before, JSON.stringify(await prompt()));
  check("Escape keeps the prompt", (await prompt()).startsWith("Line one of a prompt"));

  // 5. Loading state, duplicate prevention, Stop
  await setPrompt("Stream slowly please MARK-SLOW for stop");
  const callsAtStart = (await server()).calls;
  await click(".enhance-btn");
  await waitFor(`document.querySelector(".output-shell").dataset.state === "loading"`);
  v = await evaluate(`({ busy: document.querySelector('[aria-label="Enhanced prompt"]').getAttribute("aria-busy"),
    stop: !document.querySelector(".stop-btn").hidden, disabled: document.querySelector(".enhance-btn").getAttribute("aria-disabled"),
    spinner: !!document.querySelector(".enhance-btn .spinner"), label: document.querySelector(".enhance-btn").textContent,
    copy: document.querySelector("#copy-btn").disabled })`);
  check("loading: aria-busy, Stop shown, Enhance aria-disabled, spinner, Copy disabled", v.busy === "true" && v.stop && v.disabled === "true" && v.spinner && v.copy, JSON.stringify(v));
  check("loading is announced", (await announced()).includes("Enhancing prompt."));
  await click(".enhance-btn");
  await evaluate(`document.querySelector("#prompt-input").focus()`);
  await press("Enter", { modifiers: CTRL, text: undefined });
  await sleep(300);
  check("no duplicate request while one is running", (await server()).calls === callsAtStart + 1, JSON.stringify(await server()));
  await waitFor(`(document.querySelector("#output-text")?.textContent || "").includes("slow-03")`);
  await screenshot("03-streaming");
  await click(".stop-btn");
  await sleep(100);
  const stopped = await evaluate(`({ state: document.querySelector(".output-shell").dataset.state,
    notice: document.querySelector(".output-notice")?.textContent, text: document.querySelector("#output-text")?.textContent,
    focus: document.activeElement.className, stopHidden: document.querySelector(".stop-btn").hidden })`);
  check("Stop: stopped state, partial output kept with a notice", stopped.state === "stopped" && /^slow-00/.test(stopped.text) && /Partial output/.test(stopped.notice ?? ""), JSON.stringify(stopped));
  check("Stop: focus moves to Enhance, Stop hidden", stopped.focus === "enhance-btn" && stopped.stopHidden, JSON.stringify(stopped));
  check("stopping is announced", (await announced()).includes("Enhancement stopped. The partial output was kept."));
  await sleep(1000);
  check("no updates after Stop", (await evaluate(`document.querySelector("#output-text").textContent`)) === stopped.text);
  let released = false;
  for (let i = 0; i < 30 && !released; i++) {
    released = (await server()).open_streams === 0;
    if (!released) await sleep(100);
  }
  check("the server released the provider stream after Stop", released, JSON.stringify(await server()));
  await screenshot("04-stopped");
  await useMenuItem(1);
  v = JSON.parse(await clipboard());
  check("Copy as JSON of stopped output is marked partial", v.partial === true && v.enhanced_prompt === stopped.text, JSON.stringify(v));
  check("a new request after Stop succeeds", await submitAndWait("Write a Python script that parses CSV files"));

  // 6. Errors and recovery
  check("provider error shows the error state", await submitAndWait("Please fail MARK-ERROR with this prompt", "error"));
  v = await evaluate(`({ message: document.querySelector("#error-message")?.textContent, retry: !!document.querySelector(".retry-btn"),
    partial: !!document.querySelector("#output-text") })`);
  check("the server's safe message is shown, with Try again", /unavailable/i.test(v.message ?? "") && v.retry && !v.partial, JSON.stringify(v));
  check("the prompt is kept after an error", (await prompt()) === "Please fail MARK-ERROR with this prompt");
  check("the error is announced", (await announced()).startsWith("Enhancement failed."));
  await screenshot("05-error");
  check("a request that fails once …", await submitAndWait("Flaky request MARK-FLAKY please", "error"));
  await click(".retry-btn");
  check("… succeeds with Try again (user-initiated, no automatic retry)", await waitFor(`document.querySelector(".output-shell").dataset.state === "success"`));
  check("recovered output", (await evaluate(`document.querySelector("#output-text").textContent`)) === "Recovered after retry.");

  await setPrompt("Partial then fail MARK-PARTIAL");
  await click(".enhance-btn");
  await evaluate(`document.querySelector(".stop-btn").focus()`);
  check("failure after partial output", await waitFor(`document.querySelector(".output-shell").dataset.state === "error"`));
  v = await evaluate(`({ text: document.querySelector("#output-text")?.textContent, notice: document.querySelector(".output-notice")?.textContent,
    message: document.querySelector("#error-message")?.textContent, focus: document.activeElement.className })`);
  check("partial output is kept and marked incomplete", v.text === "Partial line one.\nPartial line two." && /failed before completion/.test(v.notice ?? "") && !!v.message, JSON.stringify(v));
  check("focus leaves the hidden Stop button for Enhance", v.focus === "enhance-btn", v.focus);
  await screenshot("06-partial-error");
  await useMenuItem(1);
  v = JSON.parse(await clipboard());
  check("Copy as JSON after a failure is marked partial", v.partial === true && v.enhanced_prompt === "Partial line one.\nPartial line two.");

  // 7. Page shortcuts and the shortcuts dialog
  await evaluate(`document.activeElement.blur()`);
  await press("/");
  check("/ moves focus to the prompt", (await focused()) === "prompt-input");
  const promptBeforeDialog = await prompt();
  await evaluate(`document.querySelector(".enhance-btn").focus()`);
  await press("?");
  await sleep(150);
  v = await evaluate(`({ open: document.querySelector("#shortcuts-dialog").open, modal: document.querySelector("#shortcuts-dialog").matches(":modal"),
    focus: document.activeElement.getAttribute("aria-label"), expanded: document.querySelector(".shortcuts-trigger").getAttribute("aria-expanded") })`);
  check("? opens the shortcuts dialog as a modal, focus inside", v.open && v.modal && v.focus === "Close keyboard shortcuts" && v.expanded === "true", JSON.stringify(v));
  const inside = [];
  for (let i = 0; i < 5; i++) {
    await press("Tab", i % 2 ? { modifiers: SHIFT } : {});
    inside.push(await evaluate(`document.querySelector("#shortcuts-dialog").contains(document.activeElement)`));
  }
  check("Tab and Shift+Tab stay inside the dialog", inside.every(Boolean), JSON.stringify(inside));
  const ax = await page.send("Accessibility.getFullAXTree");
  const names = ax.nodes.filter((n) => !n.ignored).map((n) => n.name?.value).filter(Boolean);
  check("the page behind the dialog is hidden from assistive technology", names.includes("Keyboard shortcuts") && !names.includes("Enhance prompt"), names.slice(0, 12).join(" | "));
  await screenshot("07-dialog");
  await press("Escape");
  await sleep(150);
  v = await evaluate(`({ open: document.querySelector("#shortcuts-dialog").open, focus: document.activeElement.className,
    expanded: document.querySelector(".shortcuts-trigger").getAttribute("aria-expanded") })`);
  check("Escape closes it and returns focus to where it was", !v.open && v.focus === "enhance-btn" && v.expanded === "false", JSON.stringify(v));
  await click(".shortcuts-trigger");
  await sleep(150);
  check("the header button opens it", await evaluate(`document.querySelector("#shortcuts-dialog").open`));
  await click("#shortcuts-dialog .icon-btn");
  await sleep(150);
  v = await evaluate(`({ open: document.querySelector("#shortcuts-dialog").open, focus: document.activeElement.className })`);
  check("the close button closes it; focus back on the trigger", !v.open && v.focus === "shortcuts-trigger", JSON.stringify(v));
  await click(".shortcuts-trigger");
  await sleep(150);
  await clickAt(8, 8);
  await sleep(150);
  check("a click on the backdrop closes it", !(await evaluate(`document.querySelector("#shortcuts-dialog").open`)));
  check("the dialog never changes the prompt", (await prompt()) === promptBeforeDialog);
  // The live region is inert behind the modal: an outcome reached meanwhile is announced on close.
  await setPrompt("Partial then fail MARK-PARTIAL");
  await click(".enhance-btn");
  await press("?");
  await waitFor(`document.querySelector(".output-shell").dataset.state === "error"`);
  await sleep(100);
  const whileOpen = await announced();
  await press("Escape");
  await sleep(150);
  const afterClose = await announced();
  check("an outcome reached while the dialog is open is announced once it closes", !whileOpen.includes("failed") && afterClose.startsWith("Enhancement failed before completion"), JSON.stringify({ whileOpen, afterClose }));

  // 8. Copy menu by keyboard
  await evaluate(`document.querySelector("#copy-btn").focus()`);
  await press("ArrowDown");
  await sleep(80);
  const seq = [await focused()];
  for (const key of ["ArrowDown", "ArrowDown", "End", "Home", "ArrowUp"]) {
    await press(key);
    await sleep(40);
    seq.push(await focused());
  }
  check("menu keys: ↓ opens on the first item; ↓ ↑ wrap; Home/End", JSON.stringify(seq) === JSON.stringify(["item:Copy text", "item:Copy as JSON", "item:Copy text", "item:Copy as JSON", "item:Copy text", "item:Copy as JSON"]), JSON.stringify(seq));
  check("expanded state while open", (await evaluate(`document.querySelector("#copy-btn").getAttribute("aria-expanded")`)) === "true");
  await press("Escape");
  await sleep(80);
  v = await evaluate(`({ hidden: document.querySelector("#copy-menu-list").hidden, focus: document.activeElement.id,
    expanded: document.querySelector("#copy-btn").getAttribute("aria-expanded") })`);
  check("Escape closes the menu and returns focus to Copy", v.hidden && v.focus === "copy-btn" && v.expanded === "false", JSON.stringify(v));
  await press("Enter");
  await sleep(80);
  check("Enter on Copy opens the menu on its first item", (await focused()) === "item:Copy text");
  await press("ArrowDown");
  await press("Enter");
  await sleep(300);
  v = JSON.parse(await clipboard());
  check("choosing Copy as JSON by keyboard copies and closes the menu", v.partial === true && (await evaluate(`document.querySelector("#copy-menu-list").hidden`)) && (await focused()) === "copy-btn");
  await press("ArrowDown");
  await press("Tab");
  await sleep(80);
  check("Tab closes the menu", await evaluate(`document.querySelector("#copy-menu-list").hidden`));
  await evaluate(`document.querySelector("#copy-btn").focus()`);
  await press("ArrowDown");
  await sleep(80);
  await press("/");
  await sleep(80);
  check("a shortcut that moves focus away closes the menu", (await focused()) === "prompt-input" && (await evaluate(`document.querySelector("#copy-menu-list").hidden`)));
  await setPrompt("Write a Python script that parses CSV files");
  await press("Enter", { modifiers: CTRL, text: undefined });
  await waitFor(`document.querySelector(".output-shell").dataset.state === "success"`);
  await sleep(100);
  check("the menu does not reopen by itself after the next request", (await evaluate(`document.querySelector("#copy-menu-list").hidden`)) && (await focused()) === "prompt-input");

  // 9. Small viewports and high zoom (no horizontal scrolling, nothing clipped)
  for (const [w, h, label] of [[1280, 900, "desktop"], [640, 450, "200% zoom"], [320, 256, "400% zoom"], [375, 812, "phone"]]) {
    await page.send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
    await load();
    await submitAndWait("Write a Python script that parses CSV files");
    v = await evaluate(`(() => { const e = document.documentElement, b = document.querySelector(".enhance-btn").getBoundingClientRect(),
      c = document.querySelector("#copy-btn").getBoundingClientRect();
      return { overflow: e.scrollWidth - innerWidth, enhance: [b.left, b.right], copy: [c.left, c.right],
        sticky: getComputedStyle(document.querySelector(".site-header")).position }; })()`);
    check(`${label}: no horizontal overflow; controls within the width`, v.overflow <= 0 && v.enhance[0] >= 0 && v.enhance[1] <= w && v.copy[0] >= 0 && v.copy[1] <= w, JSON.stringify(v));
    if (h < 600) check(`${label}: header does not stick over the content`, v.sticky !== "sticky", v.sticky);
    await screenshot(`08-${w}x${h}`);
    await evaluate(`document.activeElement.blur()`);
    await press("?");
    await sleep(200);
    v = await evaluate(`(() => { const d = document.querySelector("#shortcuts-dialog"), p = d.querySelector(".shortcuts-panel");
      d.scrollTop = 0; const top = p.getBoundingClientRect(), close = d.querySelector(".icon-btn").getBoundingClientRect();
      d.scrollTop = d.scrollHeight; const bottom = p.getBoundingClientRect().bottom;
      return { top: top.top, left: top.left, right: top.right, closeTop: close.top, closeRight: close.right, bottom, vh: innerHeight, vw: innerWidth }; })()`);
    check(`${label}: dialog title and close button reachable, panel fits`, v.top >= 0 && v.closeTop >= 0 && v.left >= 0 && v.right <= v.vw && v.closeRight <= v.vw && v.bottom <= v.vh + 1, JSON.stringify(v));
    await screenshot(`09-dialog-${w}x${h}`);
    await press("Escape");
  }
  await page.send("Emulation.clearDeviceMetricsOverride");

  // 10. Reduced motion
  await page.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  await load();
  v = await evaluate(`[".hero", ".workspace", ".empty-icon"].map((s) => parseFloat(getComputedStyle(document.querySelector(s)).animationDuration))`);
  check("reduced motion: animations are effectively off", v.every((d) => d <= 0.001), JSON.stringify(v));
  await page.send("Emulation.setEmulatedMedia", { features: [] });

  // 11. Without JavaScript the page still explains itself
  await page.send("Emulation.setScriptExecutionDisabled", { value: true });
  await load();
  v = await evaluate(`document.body.innerText`).catch(() => null);
  await page.send("Emulation.setScriptExecutionDisabled", { value: false });
  // (evaluate itself still works: the setting only blocks page scripts)
  check("without JavaScript: brand and an explanation, not a blank page", typeof v === "string" && v.includes("FORGE") && v.includes("needs JavaScript"), String(v));

  // 12. Copy fallback when the Clipboard API is missing and copying is refused
  const { identifier } = await page.send("Page.addScriptToEvaluateOnNewDocument", {
    source: `Object.defineProperty(Navigator.prototype, "clipboard", { get: () => undefined, configurable: true });
             Document.prototype.execCommand = () => false;`,
  });
  await load();
  await submitAndWait("Write a Python script that parses CSV files");
  await useMenuItem(0);
  v = await evaluate(`({ note: document.querySelector(".copy-note")?.textContent, kind: document.querySelector(".copy-note")?.dataset.kind,
    selected: String(getSelection()) })`);
  check("no clipboard access: useful message and the output is selected for manual copying", v.kind === "failed" && /Couldn't copy automatically\. The text is selected/.test(v.note ?? "") && v.selected.replaceAll("\r", "") === EXPECTED, JSON.stringify({ ...v, selected: v.selected.slice(0, 40) }));
  await page.send("Page.removeScriptToEvaluateOnNewDocument", { identifier });

  check("no console errors or exceptions", consoleProblems.length === 0, JSON.stringify(consoleProblems));
  check("no requests to any other origin", foreignRequests.length === 0, JSON.stringify(foreignRequests));
} catch (error) {
  check("browser run completed", false, error.stack);
} finally {
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - failed}/${results.length} checks passed`);
  try {
    page?.close();
  } catch {
    // ignore
  }
  chrome.kill();
  await sleep(500);
  try {
    rmSync(profile, { recursive: true, force: true });
  } catch {
    // Chrome may still hold files briefly on Windows
  }
  process.exit(failed ? 1 : 0);
}
