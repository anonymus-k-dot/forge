// Runs the real inline application script from the legacy template under Node, with a
// fake DOM (fake_dom.mjs) and a stubbed fetch that streams SSE frames, then exercises
// "Enhance" and the "Copy as JSON" / "Copy text" actions.
//
// Usage: node legacy_ui_export.mjs <path/to/index.html>   (exit code 0 = pass)

import assert from "node:assert/strict";
import { load, scriptedFetch, settle } from "./fake_dom.mjs";

// Two SSE frames, the second split across network chunks, then the done frame.
const frames = [
  'data: {"chunk": "Act as a senior data engineer.\\n"}\n\n',
  'data: {"chunk": "Parse the CSV ',
  'files robustly.  "}\n\ndata: {"done": true}\n\n',
];
const expectedPrompt = "Act as a senior data engineer.\nParse the CSV files robustly.";

try {
  const fake = scriptedFetch(frames);
  const ui = load(process.argv[2], { fetch: fake.fetch });
  const input = ui.$("raw-input");
  input.value = "Write a Python script that parses CSV files";
  ui.$("enhance-btn").click();
  await settle();

  assert.deepEqual(
    fake.calls.map(({ url, method, body }) => ({ url, method, body })),
    [{ url: "/enhance", method: "POST", body: { prompt: input.value, stream: true } }],
  );

  ui.$("copy-btn").click();
  ui.$("copy-json").click(); // Copy as JSON
  await settle();
  const exportedJson = ui.clipboard.at(-1);
  assert.ok(exportedJson, "Copy as JSON wrote nothing to the clipboard");
  assert.deepEqual(JSON.parse(exportedJson), { enhanced_prompt: expectedPrompt });
  for (const fabricated of ["98%", "0.98", "confidence", "score"]) {
    assert.ok(!exportedJson.includes(fabricated), `JSON export contains ${fabricated}`);
  }

  ui.$("copy-btn").click();
  ui.$("copy-text").click(); // Copy text: exactly what is displayed
  await settle();
  assert.equal(ui.clipboard.at(-1), expectedPrompt);
  assert.equal(ui.$("output-text").textContent, expectedPrompt);

  console.log("PASS legacy UI export:", JSON.stringify(JSON.parse(exportedJson)));
  process.exit(0);
} catch (error) {
  console.error("FAIL legacy UI export:", error.message);
  process.exit(1);
}
