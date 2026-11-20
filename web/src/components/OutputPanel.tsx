import { useLayoutEffect, useRef } from "react";
import type { EnhancementState } from "../state/enhancement.ts";
import type { CopyFormat } from "../utils/copy.ts";
import { CopyMenu } from "./CopyMenu.tsx";
import { Icon } from "./Icon.tsx";

export interface CopyNote {
  readonly kind: "copied" | "failed";
  readonly text: string;
}

interface OutputPanelProps {
  readonly state: EnhancementState;
  readonly onRetry: () => void;
  readonly onCopy: (format: CopyFormat) => void;
  readonly copyNote: CopyNote | null;
}

const NOTICES = {
  stopped: "Stopped. Partial output: it may be incomplete.",
  error: "Generation failed before completion. The partial output below is incomplete.",
} as const;

/** The enhanced prompt. Model output is untrusted text and is only ever rendered as text. */
export function OutputPanel({ state, onRetry, onCopy, copyNote }: OutputPanelProps) {
  const { phase, output, partial, error } = state;
  const bodyRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);
  const loading = phase === "loading";
  const canCopy = !loading && output !== "";

  // While streaming, keep the newest text in view unless the reader has scrolled up.
  useLayoutEffect(() => {
    const body = bodyRef.current;
    if (loading && body && followRef.current) body.scrollTop = body.scrollHeight;
  }, [loading, output]);

  const onScroll = () => {
    const body = bodyRef.current;
    if (body) followRef.current = body.scrollHeight - body.scrollTop - body.clientHeight < 24;
  };

  const text = output ? (
    <pre className="output-text" id="output-text">
      {output}
    </pre>
  ) : null;

  let content;
  if (phase === "idle") {
    content = (
      <EmptyState title="Ready to forge">
        Enter a rough prompt and select Enhance prompt to get a structured, precise version.
      </EmptyState>
    );
  } else if (loading) {
    content = text ?? (
      <div className="skeleton" aria-hidden="true">
        {[38, 92, 78, 86, 64, 72].map((width) => (
          <span key={width} className={`skeleton-line w${width}`} />
        ))}
      </div>
    );
  } else if (phase === "success") {
    content = text;
  } else if (phase === "stopped") {
    content = partial ? (
      <>
        <p className="output-notice">{NOTICES.stopped}</p>
        {text}
      </>
    ) : (
      <EmptyState title="Stopped">
        No output arrived before you stopped. Your prompt is unchanged.
      </EmptyState>
    );
  } else {
    content = (
      <>
        <div className="error-box">
          <Icon name="alert" size={26} />
          <p className="error-title">Enhancement failed</p>
          <p className="error-message" id="error-message">
            {error}
          </p>
          <button type="button" className="retry-btn" onClick={onRetry}>
            <Icon name="refresh" />
            <span>Try again</span>
          </button>
        </div>
        {partial && (
          <>
            <p className="output-notice">{NOTICES.error}</p>
            {text}
          </>
        )}
      </>
    );
  }

  return (
    <section className="output-shell" data-state={phase} aria-labelledby="output-label">
      <div className="output-head">
        <div className="output-heading">
          <h2 id="output-label" className="field-label">
            Architected output
          </h2>
          <p className="output-hint">The enhanced prompt, shown exactly as it will be copied.</p>
        </div>
        <CopyMenu disabled={!canCopy} copied={copyNote?.kind === "copied"} onCopy={onCopy} />
      </div>
      {copyNote && (
        <p className="copy-note" data-kind={copyNote.kind}>
          {copyNote.text}
        </p>
      )}
      <div
        ref={bodyRef}
        className={phase === "idle" || (phase === "stopped" && !partial) ? "output-body centered" : "output-body"}
        role="region"
        aria-label="Enhanced prompt"
        aria-busy={loading}
        tabIndex={0}
        onScroll={onScroll}
      >
        {content}
      </div>
    </section>
  );
}

function EmptyState({ title, children }: { title: string; children: string }) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon name="spark" size={30} />
      </span>
      <p className="empty-title">{title}</p>
      <p className="empty-text">{children}</p>
    </div>
  );
}
