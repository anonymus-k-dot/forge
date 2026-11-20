import { useEffect, useRef } from "react";

interface Shortcuts {
  /** "?": open the shortcuts dialog. */
  readonly onShowShortcuts: () => void;
  /** "/": move focus to the prompt. */
  readonly onFocusPrompt: () => void;
  /** False while a modal dialog is open (the dialog handles its own keys). */
  readonly enabled: boolean;
}

/**
 * Page-level single-key shortcuts. They never fire while typing in a field or with a
 * modifier held, so native shortcuts (Ctrl/⌘+C, Ctrl/⌘+A, …) are never intercepted.
 */
export function useGlobalShortcuts(shortcuts: Shortcuts): void {
  const latest = useRef(shortcuts);
  latest.current = shortcuts;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const { enabled, onShowShortcuts, onFocusPrompt } = latest.current;
      if (!enabled || event.defaultPrevented) return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      const typing =
        target !== null &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);
      if (typing) return;
      if (event.key === "?") {
        event.preventDefault();
        onShowShortcuts();
      } else if (event.key === "/") {
        event.preventDefault();
        onFocusPrompt();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);
}
