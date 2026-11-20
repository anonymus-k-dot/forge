// Fakes for the unit tests: fetch, streamed responses, and a way to let promises settle.
// No network: every response is built here.

const encoder = new TextEncoder();

/** SSE text for frames, exactly as Flask's /enhance writes them. */
export const sse = (...frames) => frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join("");

/** Splits text into UTF-8 byte pieces of `size` bytes (cuts through characters too). */
export function bytePieces(text, size) {
  const bytes = encoder.encode(text);
  const pieces = [];
  for (let i = 0; i < bytes.length; i += size) pieces.push(bytes.slice(i, i + size));
  return pieces;
}

function streamFrom(pieces, signal, failWith) {
  const queue = pieces.map((piece) => (typeof piece === "string" ? encoder.encode(piece) : piece));
  return new ReadableStream({
    start(controller) {
      signal?.addEventListener("abort", () => {
        try {
          controller.error(signal.reason);
        } catch {
          // already closed
        }
      });
    },
    pull(controller) {
      if (queue.length > 0) controller.enqueue(queue.shift());
      else if (failWith) controller.error(failWith);
      else controller.close();
    },
  });
}

/** Builds a response (given the request's abort signal). */
export function sseResponse(pieces, { status = 200, contentType = "text/event-stream", failWith } = {}) {
  return (signal) =>
    new Response(streamFrom(pieces, signal, failWith), {
      status,
      headers: { "Content-Type": contentType },
    });
}

export function jsonResponse(body, status) {
  return () =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export function textResponse(body, status, contentType = "text/html") {
  return () => new Response(body, { status, headers: { "Content-Type": contentType } });
}

/** A response the test feeds piece by piece (to interleave Stop, late data, …). */
export function manualResponse() {
  let controller;
  let signal;
  const stream = new ReadableStream({
    start(c) {
      controller = c;
    },
  });
  return {
    respond(requestSignal) {
      signal = requestSignal;
      signal?.addEventListener("abort", () => {
        try {
          controller.error(signal.reason);
        } catch {
          // already closed
        }
      });
      return new Response(stream, { headers: { "Content-Type": "text/event-stream" } });
    },
    push(text) {
      try {
        controller.enqueue(encoder.encode(text));
        return true;
      } catch {
        return false; // the stream was cancelled or errored (after Stop)
      }
    },
    close() {
      try {
        controller.close();
      } catch {
        // already closed
      }
    },
    get aborted() {
      return Boolean(signal?.aborted);
    },
  };
}

/**
 * A fetch that answers request n with responders[n] (a function of the abort signal, or an
 * Error to reject with). Records every call.
 */
export function scriptedFetch(...responders) {
  const calls = [];
  const fetch = async (url, init) => {
    calls.push({ url, method: init.method, headers: init.headers, body: JSON.parse(init.body) });
    const responder = responders[calls.length - 1];
    if (responder === undefined) throw new Error(`unexpected request #${calls.length}`);
    if (responder instanceof Error) throw responder;
    if (init.signal?.aborted) throw init.signal.reason;
    return typeof responder === "function" ? responder(init.signal) : responder.respond(init.signal);
  };
  return { fetch, calls };
}

/** Let pending promises and stream reads run. */
export async function settle(rounds = 30) {
  for (let i = 0; i < rounds; i++) await new Promise((resolve) => setImmediate(resolve));
}
