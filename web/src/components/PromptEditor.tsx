import type { KeyboardEvent, RefObject } from "react";
import {
  MAX_PROMPT_CHARS,
  counterLevel,
  countCharacters,
  formatCount,
} from "../utils/prompt.ts";

const EXAMPLES = [
  {
    label: "Launch announcement",
    prompt:
      "Write a launch announcement for a developer tool that turns meeting transcripts into structured Jira tickets.",
  },
  {
    label: "Research summary",
    prompt:
      "Summarize the attached research paper and extract the three most actionable findings for a product team.",
  },
  {
    label: "Code refactor",
    prompt: "Refactor this Python function to be async, type-safe, and covered by pytest cases.",
  },
] as const;

interface PromptEditorProps {
  readonly value: string;
  readonly onChange: (value: string) => void;
  /** Ctrl/⌘+Enter in the editor. */
  readonly onSubmit: () => void;
  /** Validation message from the last attempt to submit, if any. */
  readonly error: string | null;
  readonly inputRef: RefObject<HTMLTextAreaElement | null>;
}

export function PromptEditor({ value, onChange, onSubmit, error, inputRef }: PromptEditorProps) {
  const count = countCharacters(value);
  const level = counterLevel(count);

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Only Ctrl/⌘+Enter is handled here; every other key (Escape included) behaves natively.
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.altKey) {
      event.preventDefault();
      onSubmit();
    }
  };

  const fill = (text: string) => {
    onChange(text);
    inputRef.current?.focus();
  };

  const describedBy = error ? "prompt-counter prompt-error" : "prompt-counter";

  return (
    <section className="card editor" aria-labelledby="prompt-label">
      <div className="editor-head">
        <label id="prompt-label" htmlFor="prompt-input" className="field-label">
          Raw input
        </label>
        <div className="editor-tools">
          <span id="prompt-counter" className="counter" data-level={level}>
            {formatCount(count)} / {formatCount(MAX_PROMPT_CHARS)}
            <span className="visually-hidden"> characters</span>
            {level === "over" && <span className="visually-hidden">, over the limit</span>}
          </span>
          <button
            type="button"
            className="ghost-btn"
            onClick={() => fill("")}
            disabled={value === ""}
          >
            Clear
          </button>
        </div>
      </div>
      <div className="input-wrap">
        <textarea
          id="prompt-input"
          ref={inputRef}
          className="prompt-input"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Enter the rough prompt here…"
          rows={8}
          spellCheck
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
        />
        <span className="focus-line" aria-hidden="true" />
      </div>
      {error && (
        <p id="prompt-error" className="field-error">
          {error}
        </p>
      )}
      <div className="examples" role="group" aria-label="Example prompts">
        {EXAMPLES.map((example) => (
          <button
            key={example.label}
            type="button"
            className="chip"
            onClick={() => fill(example.prompt)}
          >
            {example.label}
          </button>
        ))}
      </div>
    </section>
  );
}
