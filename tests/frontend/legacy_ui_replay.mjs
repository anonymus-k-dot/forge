// Replays an /enhance response produced by the real Flask app (with a fake provider) into
// the legacy template's application script, split into small network pieces.
//
// Usage: node legacy_ui_replay.mjs <index.html> <scenario.json>   (exit code 0 = pass)
// scenario: {"status": 200, "pieces_b64": [...], "expected_text": str | null,
//            "expected_error": str | null}

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { load, scriptedFetch, settle } from "./fake_dom.mjs";

const [templatePath, scenarioPath] = process.argv.slice(2);
const scenario = JSON.parse(readFileSync(scenarioPath, "utf8"));

try {
  const pieces = scenario.pieces_b64.map((b64) => new Uint8Array(Buffer.from(b64, "base64")));
  const ui = load(templatePath, { fetch: scriptedFetch(pieces).fetch });
  ui.$("raw-input").value = "Write a Python script that parses CSV files";
  ui.$("enhance-btn").click();
  await settle();

  const state = ui.$("output-shell").getAttribute("data-state");
  if (scenario.expected_error !== null) {
    assert.equal(state, "error");
    assert.equal(ui.$("error-message").textContent, scenario.expected_error);
  } else {
    assert.equal(state, "success");
    assert.equal(ui.$("output-text").textContent, scenario.expected_text);
    ui.$("copy-btn").click();
    ui.$("copy-text").click();
    await settle();
    assert.equal(ui.clipboard.at(-1), scenario.expected_text, "copied text equals displayed text");
  }
  console.log("PASS legacy UI replay:", state);
  process.exit(0);
} catch (error) {
  console.error("FAIL legacy UI replay:", error.message);
  process.exit(1);
}
