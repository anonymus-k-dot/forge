import assert from "node:assert/strict";
import { test } from "node:test";
import { SseParser } from "../../src/api/sse.ts";

const parseAll = (pieces) => {
  const parser = new SseParser();
  const events = pieces.flatMap((piece) => parser.push(piece));
  return [...events, ...parser.end()];
};

const STREAM = 'data: {"chunk": "a"}\n\ndata: {"chunk": "b"}\n\ndata: {"done": true}\n\n';
const EXPECTED = ['{"chunk": "a"}', '{"chunk": "b"}', '{"done": true}'];

test("one chunk holding several events", () => {
  assert.deepEqual(parseAll([STREAM]), EXPECTED);
});

test("events split at every possible point, down to single characters", () => {
  for (let cut = 1; cut < STREAM.length; cut++) {
    assert.deepEqual(parseAll([STREAM.slice(0, cut), STREAM.slice(cut)]), EXPECTED, `cut at ${cut}`);
  }
  assert.deepEqual(parseAll([...STREAM]), EXPECTED);
});

test("CRLF and CR line endings, including a CRLF split across chunks", () => {
  const crlf = STREAM.replaceAll("\n", "\r\n");
  assert.deepEqual(parseAll([crlf]), EXPECTED);
  for (let cut = 1; cut < crlf.length; cut++) {
    assert.deepEqual(parseAll([crlf.slice(0, cut), crlf.slice(cut)]), EXPECTED, `cut at ${cut}`);
  }
  assert.deepEqual(parseAll([STREAM.replaceAll("\n", "\r")]), EXPECTED);
});

test("an incomplete event waits for its blank line", () => {
  const parser = new SseParser();
  assert.deepEqual(parser.push('data: {"chunk": "a"}\n'), []);
  assert.deepEqual(parser.push("\n"), ['{"chunk": "a"}']);
});

test("multi-line data is joined with newlines; comments and other fields are ignored", () => {
  const events = parseAll([": keep-alive\n", "event: message\nid: 7\ndata: line 1\ndata:line 2\n\n"]);
  assert.deepEqual(events, ["line 1\nline 2"]);
});

test("blank lines without data produce no events", () => {
  assert.deepEqual(parseAll(["\n\n\r\n", ": comment\n\n"]), []);
});

test("a final event without its blank line is still returned at the end of the stream", () => {
  assert.deepEqual(parseAll(['data: {"done": true}']), ['{"done": true}']);
  assert.deepEqual(parseAll(['data: {"done": true}\r']), ['{"done": true}']);
});

test("multi-line data with CRLF or CR endings, split anywhere, stays one event", () => {
  for (const eol of ["\r\n", "\r"]) {
    const stream = `data: line 1${eol}data: line 2${eol}${eol}`;
    for (let cut = 1; cut < stream.length; cut++) {
      const events = parseAll([stream.slice(0, cut), stream.slice(cut)]);
      assert.deepEqual(events, ["line 1\nline 2"], `${JSON.stringify(eol)} cut at ${cut}`);
    }
  }
});
