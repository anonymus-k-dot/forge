/**
 * Incremental parser for the Server-Sent Events stream of `POST /enhance`.
 *
 * Network chunks are arbitrary: one chunk can hold several events, part of one, or end in
 * the middle of a line. (A chunk can also end inside a UTF-8 character; that is handled
 * before this parser by decoding with `TextDecoder` in streaming mode.) Lines may end in
 * "\n", "\r\n" or "\r". An event ends at a blank line and its `data:` lines are joined with
 * "\n", as in the SSE specification. Comments (":") and other fields are ignored.
 */
export class SseParser {
  #buffer = "";
  #data: string[] = [];

  /** Add decoded text; returns the data of every event completed by it. */
  push(text: string): string[] {
    this.#buffer += text;
    const events: string[] = [];
    const buffer = this.#buffer;
    let start = 0;
    for (let i = 0; i < buffer.length; i++) {
      const char = buffer[i];
      if (char !== "\n" && char !== "\r") continue;
      if (char === "\r" && i === buffer.length - 1) break; // may be the first half of "\r\n"
      this.#line(buffer.slice(start, i), events);
      if (char === "\r" && buffer[i + 1] === "\n") i++;
      start = i + 1;
    }
    this.#buffer = buffer.slice(start);
    return events;
  }

  /**
   * End of stream. An event still pending (its terminating blank line never arrived) is
   * returned rather than dropped, so a final frame is not lost to a missing newline.
   */
  end(): string[] {
    const events: string[] = [];
    if (this.#buffer) {
      this.#line(this.#buffer.replace(/\r$/, ""), events);
      this.#buffer = "";
    }
    if (this.#data.length > 0) {
      events.push(this.#data.join("\n"));
      this.#data = [];
    }
    return events;
  }

  #line(line: string, events: string[]): void {
    if (line === "") {
      if (this.#data.length > 0) {
        events.push(this.#data.join("\n"));
        this.#data = [];
      }
      return;
    }
    if (line.startsWith(":")) return; // comment
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "data") this.#data.push(value);
  }
}
