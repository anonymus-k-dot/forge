import { useEffect, useReducer, useState } from "react";
import { enhancementReducer, initialEnhancementState } from "../state/enhancement.ts";
import type { EnhancementState } from "../state/enhancement.ts";
import { createEnhancementSession } from "../state/session.ts";

export interface Enhancement {
  readonly state: EnhancementState;
  /** Starts a request; returns false while one is already running. */
  readonly start: (prompt: string) => boolean;
  readonly stop: () => void;
}

export function useEnhancement(): Enhancement {
  const [state, dispatch] = useReducer(enhancementReducer, initialEnhancementState);
  const [session] = useState(() => createEnhancementSession(dispatch));
  useEffect(() => () => session.stop(), [session]); // leaving the page cancels the request
  return { state, start: session.start, stop: session.stop };
}
