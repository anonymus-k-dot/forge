/**
 * Request lifecycle of the enhancement panel, as a pure reducer.
 *
 *   idle ─start─▶ loading ─succeed─▶ success
 *                    │ ├──stop────▶ stopped   (partial output kept)
 *                    │ └──fail────▶ error     (partial output kept, marked incomplete)
 *                    └──chunk──▶ loading      (output grows while streaming)
 *
 * Every action carries the id of the request it belongs to. Actions for a request that is
 * not the current one, or that arrive after the request finished (late stream data after
 * Stop, say), are ignored: nothing can change the panel once a request has ended.
 */
export type Phase = "idle" | "loading" | "success" | "stopped" | "error";

export interface EnhancementState {
  readonly phase: Phase;
  /** Id of the current (or last) request; 0 before the first one. */
  readonly requestId: number;
  /** What the output panel shows. Once the request has ended, exactly what is copied. */
  readonly output: string;
  /** The output is incomplete: stopped, or failed after some output arrived. */
  readonly partial: boolean;
  /** Safe error message (phase "error" only). */
  readonly error: string | null;
}

export type EnhancementAction =
  | { readonly type: "start"; readonly requestId: number }
  | { readonly type: "chunk"; readonly requestId: number; readonly text: string }
  | { readonly type: "succeed"; readonly requestId: number; readonly output: string }
  | { readonly type: "fail"; readonly requestId: number; readonly message: string }
  | { readonly type: "stop"; readonly requestId: number };

export const initialEnhancementState: EnhancementState = {
  phase: "idle",
  requestId: 0,
  output: "",
  partial: false,
  error: null,
};

export function enhancementReducer(
  state: EnhancementState,
  action: EnhancementAction,
): EnhancementState {
  if (action.type === "start") {
    if (state.phase === "loading") return state; // one request at a time
    return { phase: "loading", requestId: action.requestId, output: "", partial: false, error: null };
  }
  if (action.requestId !== state.requestId || state.phase !== "loading") return state;
  switch (action.type) {
    case "chunk":
      return { ...state, output: state.output + action.text };
    case "succeed":
      return { ...state, phase: "success", output: action.output };
    case "stop": {
      const output = state.output.trim();
      return { ...state, phase: "stopped", output, partial: output !== "" };
    }
    case "fail": {
      const output = state.output.trim();
      return { ...state, phase: "error", output, partial: output !== "", error: action.message };
    }
  }
}
