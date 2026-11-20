import assert from "node:assert/strict";
import { test } from "node:test";
import { copyPayload, copyToClipboard } from "../../src/utils/copy.ts";
import {
  MAX_PROMPT_CHARS,
  MIN_PROMPT_CHARS,
  counterLevel,
  countCharacters,
  validatePrompt,
} from "../../src/utils/prompt.ts";

test("characters are counted as people count them (code points)", () => {
  assert.equal(countCharacters(""), 0);
  assert.equal(countCharacters("abc"), 3);
  assert.equal(countCharacters("🚀🚀"), 2);
  assert.equal(countCharacters("café"), 4);
});

test("empty and whitespace-only prompts are rejected", () => {
  for (const text of ["", "   ", "\n\t \n"]) assert.equal(validatePrompt(text).problem, "empty");
});

test("very short prompts are rejected (same minimum as the classic interface)", () => {
  assert.equal(MIN_PROMPT_CHARS, 10);
  assert.equal(validatePrompt("too short").problem, "too-short");
  assert.equal(validatePrompt("  123456789  ").problem, "too-short");
  assert.equal(validatePrompt("1234567890"), null);
});

test("the 2,000-character limit", () => {
  assert.equal(MAX_PROMPT_CHARS, 2000);
  assert.equal(validatePrompt("a".repeat(2000)), null);
  const over = validatePrompt("a".repeat(2001));
  assert.equal(over.problem, "too-long");
  assert.equal(over.message, "The prompt is 2,001 characters; the limit is 2,000. Remove 1 to continue.");
  assert.equal(validatePrompt("🚀".repeat(2000)), null, "2,000 emoji are 2,000 characters");
  assert.deepEqual(
    [counterLevel(0), counterLevel(1799), counterLevel(1800), counterLevel(2000), counterLevel(2001)],
    ["normal", "normal", "warn", "warn", "over"],
  );
});

const OUTPUT = "Line 1 with user_id and **stars**\n```py\nprint('<b>')\n```";

test("Copy text is exactly the displayed output; Copy as JSON wraps it", () => {
  assert.equal(copyPayload("text", OUTPUT, false), OUTPUT);
  assert.deepEqual(JSON.parse(copyPayload("json", OUTPUT, false)), { enhanced_prompt: OUTPUT });
  assert.deepEqual(JSON.parse(copyPayload("json", OUTPUT, true)), { enhanced_prompt: OUTPUT, partial: true });
  assert.ok(!/score|confidence/.test(copyPayload("json", OUTPUT, false)), "no fabricated metrics");
});

function fakeDocument({ execResult }) {
  const appended = [];
  const focused = [];
  const previous = { focus: () => focused.push("previous") };
  return {
    appended,
    focused,
    document: {
      body: { append: (node) => appended.push(node) },
      activeElement: previous,
      createElement: () => ({
        value: "",
        className: "",
        setAttribute() {},
        select() {},
        remove() {
          this.removed = true;
        },
      }),
      execCommand: (command) => {
        assert.equal(command, "copy");
        if (execResult instanceof Error) throw execResult;
        return execResult;
      },
    },
  };
}

test("clipboard: the Clipboard API when available", async () => {
  const written = [];
  const result = await copyToClipboard("text", {
    clipboard: { writeText: async (text) => void written.push(text) },
    document: fakeDocument({ execResult: false }).document,
  });
  assert.equal(result, "copied");
  assert.deepEqual(written, ["text"]);
});

test("clipboard: falls back to the copy command when the API is missing or refuses", async () => {
  for (const clipboard of [undefined, { writeText: async () => Promise.reject(new Error("denied")) }]) {
    const fake = fakeDocument({ execResult: true });
    const result = await copyToClipboard("fallback text", { clipboard, document: fake.document });
    assert.equal(result, "copied");
    assert.equal(fake.appended[0].value, "fallback text");
    assert.equal(fake.appended[0].removed, true, "the temporary buffer is removed");
    assert.deepEqual(fake.focused, ["previous"], "focus goes back where it was");
  }
});

test("clipboard: reports failure when nothing works", async () => {
  for (const execResult of [false, new Error("not allowed")]) {
    const fake = fakeDocument({ execResult });
    assert.equal(await copyToClipboard("x", { clipboard: undefined, document: fake.document }), "failed");
  }
  assert.equal(await copyToClipboard("x", { clipboard: undefined, document: undefined }), "failed");
});
