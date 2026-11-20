import { useLayoutEffect, useRef } from "react";
import type { Phase } from "../state/enhancement.ts";
import { Icon } from "./Icon.tsx";

const STATUS: Record<Exclude<Phase, "idle">, string> = {
  loading: "Forging prompt…",
  success: "Enhanced prompt ready",
  stopped: "Stopped",
  error: "Enhancement failed",
};

interface EnhanceControlsProps {
  readonly phase: Phase;
  readonly onEnhance: () => void;
  readonly onStop: () => void;
  readonly modKey: string;
  readonly touchOnly: boolean;
}

export function EnhanceControls({ phase, onEnhance, onStop, modKey, touchOnly }: EnhanceControlsProps) {
  const busy = phase === "loading";
  const enhanceRef = useRef<HTMLButtonElement>(null);
  // Whether Stop had focus. Tracked explicitly: when a request ends the Stop button is
  // hidden, and the browser may drop its focus before any effect could look at it.
  const stopFocused = useRef(false);

  useLayoutEffect(() => {
    if (!busy && stopFocused.current) {
      stopFocused.current = false;
      enhanceRef.current?.focus(); // keep focus beside the control that disappeared
    }
  }, [busy]);

  return (
    <div className="controls">
      <p className="status-line" id="enhance-status">
        {phase !== "idle" ? (
          STATUS[phase]
        ) : touchOnly ? (
          "Tap Enhance prompt to start"
        ) : (
          <>
            Press <kbd className="key">{modKey}</kbd>
            <kbd className="key">Enter</kbd> or select Enhance prompt
          </>
        )}
      </p>
      <div className="control-buttons">
        <button
          type="button"
          className="stop-btn"
          hidden={!busy}
          onClick={onStop}
          onFocus={() => (stopFocused.current = true)}
          onBlur={(event) => {
            if (!event.currentTarget.hidden) stopFocused.current = false; // a real move away
          }}
        >
          <Icon name="stop" />
          <span>Stop</span>
        </button>
        {/* aria-disabled (not disabled) while running: the button keeps focus and stays
            announced; clicks are ignored, so a second request cannot start. */}
        <button
          type="button"
          ref={enhanceRef}
          className="enhance-btn"
          aria-disabled={busy || undefined}
          aria-describedby="enhance-status"
          onClick={busy ? undefined : onEnhance}
        >
          <span>{busy ? "Forging…" : "Enhance prompt"}</span>
          {busy ? <span className="spinner" aria-hidden="true" /> : <Icon name="arrowRight" size={18} />}
        </button>
      </div>
    </div>
  );
}
