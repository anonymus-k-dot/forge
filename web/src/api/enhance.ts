/**
 * Client for the existing `POST /enhance` streaming contract (unchanged backend):
 *
 *   request:  {"prompt": string, "stream": true}
 *   response: text/event-stream frames, each `data: <json>`:
 *             {"chunk": string}  part of the enhanced prompt (zero or more)
 *             {"done": true}     generation completed
 *             {"error": string}  generation failed; the message is safe to show
 *   400:      JSON {"error": string} (empty prompt, malformed body)
 *
 * Every failure becomes an `EnhanceError` with a safe, actionable message. Cancellation
 * (the caller aborts the signal) is not a failure: the abort error is rethrown as is.
 * There are no automatic retries: each call makes at most one request.
 */
import { SseParser } from "./sse.ts";

export const ENHANCE_URL = "/enhance";

export type FailureKind = "server" | "http" | "network" | "protocol" | "incomplete" | "empty";

export const MESSAGES = {
  network: "Could not reach the FORGE server. Check your connection and try again.",
  protocol: "The server sent a response FORGE could not read. Please try again.",
  incomplete:
    "The connection closed before the enhanced prompt was complete. Please try again.",
  empty: "The model returned no text. Try a more specific prompt.",
  unexpected: "The enhancement service did not respond as expected. Please try again.",
} as const;

const MAX_SERVER_MESSAGE = 500;

export class EnhanceError extends Error {
  readonly kind: FailureKind;

  constructor(kind: FailureKind, message: string) {
    super(message);
    this.name = "EnhanceError";
    this.kind = kind;
  }
}

export interface StreamOptions {
  signal: AbortSignal;
  /** Called with each non-empty piece of output as it arrives. */
  onChunk: (chunk: string) => void;
  fetch?: typeof fetch;
}

/**
 * Streams an enhancement. Resolves with the complete enhanced prompt (outer whitespace
 * trimmed; everything inside is kept exactly) once the server sends `done`.
 */
export async function streamEnhance(prompt: string, options: StreamOptions): Promise<string> {
  const { signal, onChunk } = options;
  const fetchImpl = options.fetch ?? globalThis.fetch.bind(globalThis);

  let response: Response;
  try {
    response = await fetchImpl(ENHANCE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ prompt, stream: true }),
      signal,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new EnhanceError("network", MESSAGES.network);
  }

  if (!response.ok) throw new EnhanceError("http", await httpErrorMessage(response, signal));
  const contentType = response.headers.get("Content-Type") ?? "";
  if (!contentType.includes("text/event-stream") || response.body === null) {
    throw new EnhanceError("protocol", MESSAGES.protocol);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  let text = "";

  /** Applies one frame; returns true when it is the completion frame. */
  const apply = (data: string): boolean => {
    const frame = parseFrame(data);
    if (typeof frame.error === "string") {
      throw new EnhanceError("server", serverMessage(frame.error));
    }
    if (typeof frame.chunk === "string" && frame.chunk !== "") {
      text += frame.chunk;
      onChunk(frame.chunk);
    }
    return frame.done === true;
  };
  const complete = (): string => {
    const output = text.trim();
    if (output === "") throw new EnhanceError("empty", MESSAGES.empty);
    return output;
  };

  try {
    for (;;) {
      let result: ReadableStreamReadResult<Uint8Array>;
      try {
        result = await reader.read();
      } catch (error) {
        if (signal.aborted) throw error;
        throw new EnhanceError("incomplete", MESSAGES.incomplete);
      }
      if (result.done) break;
      for (const data of parser.push(decoder.decode(result.value, { stream: true }))) {
        if (apply(data)) return complete();
      }
    }
    for (const data of [...parser.push(decoder.decode()), ...parser.end()]) {
      if (apply(data)) return complete();
    }
    throw new EnhanceError("incomplete", MESSAGES.incomplete);
  } finally {
    // Releases the connection when we stop reading early (done, error frame, abort).
    reader.cancel().catch(() => undefined);
  }
}

/** Safe text for any failure (never an internal exception message). */
export function describeFailure(error: unknown): string {
  return error instanceof EnhanceError ? error.message : MESSAGES.unexpected;
}

function parseFrame(data: string): Record<string, unknown> {
  let frame: unknown;
  try {
    frame = JSON.parse(data);
  } catch {
    throw new EnhanceError("protocol", MESSAGES.protocol);
  }
  if (typeof frame !== "object" || frame === null || Array.isArray(frame)) {
    throw new EnhanceError("protocol", MESSAGES.protocol);
  }
  return frame as Record<string, unknown>;
}

function serverMessage(message: string): string {
  const text = message.trim();
  if (text === "") return MESSAGES.unexpected;
  return text.length > MAX_SERVER_MESSAGE ? `${text.slice(0, MAX_SERVER_MESSAGE)}…` : text;
}

async function httpErrorMessage(response: Response, signal: AbortSignal): Promise<string> {
  const fallback = `The server returned HTTP ${response.status}. Please try again.`;
  if (!(response.headers.get("Content-Type") ?? "").includes("application/json")) return fallback;
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "error" in body) {
      const { error } = body as { error: unknown };
      if (typeof error === "string" && error.trim() !== "") return serverMessage(error);
    }
  } catch (error) {
    if (signal.aborted) throw error;
  }
  return fallback;
}
