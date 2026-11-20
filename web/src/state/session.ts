/**
 * Runs enhancement requests and reports their progress as reducer actions.
 *
 * - At most one request at a time: `start` returns false while one is running.
 * - `stop` ends the request in the UI at once and aborts the browser request. Flask then
 *   closes the provider stream; whether the provider stops generating is up to the
 *   provider, so the UI only ever says the request was stopped, not the model.
 * - Updates that arrive after a request ended carry a stale id and are ignored by the
 *   reducer.
 * - No automatic retries: a new request is only ever made by the user.
 */
import { describeFailure, streamEnhance } from "../api/enhance.ts";
import type { StreamOptions } from "../api/enhance.ts";
import type { EnhancementAction } from "./enhancement.ts";

export type StreamFunction = (prompt: string, options: StreamOptions) => Promise<string>;

export interface EnhancementSession {
  /** Starts a request; returns false (and does nothing) while another one is running. */
  start(prompt: string): boolean;
  /** Stops the running request, if any. */
  stop(): void;
  readonly busy: boolean;
}

export function createEnhancementSession(
  dispatch: (action: EnhancementAction) => void,
  stream: StreamFunction = streamEnhance,
): EnhancementSession {
  let nextId = 1;
  let active: { id: number; controller: AbortController } | null = null;

  return {
    get busy() {
      return active !== null;
    },

    start(prompt: string): boolean {
      if (active !== null) return false;
      const id = nextId++;
      const controller = new AbortController();
      active = { id, controller };
      dispatch({ type: "start", requestId: id });
      const onChunk = (text: string) => dispatch({ type: "chunk", requestId: id, text });
      let request: Promise<string>;
      try {
        request = stream(prompt, { signal: controller.signal, onChunk });
      } catch (error) {
        request = Promise.reject(error);
      }
      request
        .then(
          (output) => dispatch({ type: "succeed", requestId: id, output }),
          (error: unknown) => {
            if (!controller.signal.aborted) {
              dispatch({ type: "fail", requestId: id, message: describeFailure(error) });
            }
          },
        )
        .finally(() => {
          if (active?.id === id) active = null;
        });
      return true;
    },

    stop(): void {
      const request = active;
      if (request === null) return;
      active = null;
      dispatch({ type: "stop", requestId: request.id });
      request.controller.abort();
    },
  };
}
