import { useEffect, useMemo, useRef, useState } from "react";
import { EnhanceControls } from "./components/EnhanceControls.tsx";
import { Hero, SiteFooter, SiteHeader } from "./components/Layout.tsx";
import { OutputPanel } from "./components/OutputPanel.tsx";
import type { CopyNote } from "./components/OutputPanel.tsx";
import { PromptEditor } from "./components/PromptEditor.tsx";
import { ShortcutsDialog } from "./components/ShortcutsDialog.tsx";
import { useAnnouncer } from "./hooks/useAnnouncer.ts";
import { useEnhancement } from "./hooks/useEnhancement.ts";
import { useGlobalShortcuts } from "./hooks/useGlobalShortcuts.ts";
import { copyPayload, copyToClipboard } from "./utils/copy.ts";
import type { CopyFormat } from "./utils/copy.ts";
import { detectPlatform } from "./utils/platform.ts";
import { MAX_PROMPT_CHARS, countCharacters, formatCount, validatePrompt } from "./utils/prompt.ts";

export function App() {
  const platform = useMemo(detectPlatform, []);
  const [prompt, setPrompt] = useState("");
  const [validation, setValidation] = useState<string | null>(null);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [copyNote, setCopyNote] = useState<CopyNote | null>(null);
  const [announcement, announce] = useAnnouncer(shortcutsOpen); // held while the dialog is open
  const { state, start, stop } = useEnhancement();

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const busy = state.phase === "loading";

  const submit = () => {
    if (busy) return; // the session refuses a second request too
    const problem = validatePrompt(prompt);
    if (problem) {
      setValidation(problem.message);
      announce(problem.message);
      inputRef.current?.focus();
      return;
    }
    setValidation(null);
    setCopyNote(null);
    start(prompt);
  };

  const changePrompt = (value: string) => {
    setPrompt(value);
    setValidation(null);
  };

  // Announce request outcomes (one polite live region for the whole page).
  useEffect(() => {
    const { phase, partial, error } = state;
    if (phase === "loading") announce("Enhancing prompt.");
    else if (phase === "success") {
      announce("Enhancement complete. The enhanced prompt is in the output panel.");
    } else if (phase === "stopped") {
      announce(
        partial
          ? "Enhancement stopped. The partial output was kept."
          : "Enhancement stopped before any output arrived.",
      );
    } else if (phase === "error") {
      announce(
        partial
          ? `Enhancement failed before completion. ${error} The partial output was kept.`
          : `Enhancement failed. ${error}`,
      );
    }
    // Only on transitions (a new phase or a new request), not on every streamed chunk.
  }, [state.phase, state.requestId, announce]);

  // Crossing the character limit is announced once, not on every keystroke.
  const over = countCharacters(prompt) > MAX_PROMPT_CHARS;
  const wasOver = useRef(false);
  useEffect(() => {
    if (over === wasOver.current) return;
    wasOver.current = over;
    announce(
      over
        ? `The prompt is over the ${formatCount(MAX_PROMPT_CHARS)}-character limit.`
        : "The prompt is within the character limit again.",
    );
  }, [over, announce]);

  useEffect(() => {
    if (copyNote?.kind !== "copied") return;
    const timer = setTimeout(() => setCopyNote(null), 2500);
    return () => clearTimeout(timer);
  }, [copyNote]);

  const handleCopy = (format: CopyFormat) => {
    const payload = copyPayload(format, state.output, state.partial);
    void copyToClipboard(payload).then((result) => {
      let text: string;
      if (result === "copied") {
        text = format === "json" ? "Copied as JSON." : "Copied to clipboard.";
      } else {
        const how = platform.touchOnly
          ? "copy it from the selection menu"
          : `press ${platform.modKey}+C to copy it`;
        if (format === "text" && selectOutput()) {
          text = `Couldn't copy automatically. The text is selected: ${how}.`;
        } else {
          text = "Couldn't copy automatically. Select the output text and copy it manually.";
        }
      }
      setCopyNote({ kind: result, text });
      announce(text);
    });
  };

  useGlobalShortcuts({
    enabled: !shortcutsOpen,
    onShowShortcuts: () => setShortcutsOpen(true),
    onFocusPrompt: () => inputRef.current?.focus(),
  });

  return (
    <div className="app">
      <a className="skip-link" href="#prompt-input">
        Skip to the prompt
      </a>
      <SiteHeader
        shortcutsOpen={shortcutsOpen}
        onShowShortcuts={() => setShortcutsOpen(true)}
        showShortcutsButton={!platform.touchOnly}
        triggerRef={triggerRef}
      />
      <main className="main">
        <Hero />
        <div className="workspace">
          <div className="workspace-input">
            <PromptEditor
              value={prompt}
              onChange={changePrompt}
              onSubmit={submit}
              error={validation}
              inputRef={inputRef}
            />
            <EnhanceControls
              phase={state.phase}
              onEnhance={submit}
              onStop={stop}
              modKey={platform.modKey}
              touchOnly={platform.touchOnly}
            />
          </div>
          <OutputPanel state={state} onRetry={submit} onCopy={handleCopy} copyNote={copyNote} />
        </div>
      </main>
      <SiteFooter />
      <ShortcutsDialog
        open={shortcutsOpen}
        onClose={() => setShortcutsOpen(false)}
        modKey={platform.modKey}
        fallbackFocusRef={platform.touchOnly ? inputRef : triggerRef}
      />
      <p className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </p>
    </div>
  );
}

/** Selects the displayed output so it can be copied by hand; false if there is none. */
function selectOutput(): boolean {
  const output = document.getElementById("output-text");
  const selection = window.getSelection();
  if (!output || !selection) return false;
  selection.selectAllChildren(output);
  return true;
}
