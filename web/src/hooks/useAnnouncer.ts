import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Text for the page's single polite live region. Repeating the same message still
 * announces it: the text alternates a trailing no-break space so it always changes.
 *
 * While `paused` (a modal dialog is open, so the region is inert and would not be read),
 * the latest message is held and delivered when the dialog closes.
 */
export function useAnnouncer(paused = false): [message: string, announce: (message: string) => void] {
  const [message, setMessage] = useState("");
  const held = useRef<string | null>(null);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  const deliver = useCallback((next: string) => {
    setMessage((current) => (current === next ? `${next} ` : next));
  }, []);

  const announce = useCallback(
    (next: string) => {
      if (pausedRef.current) held.current = next;
      else deliver(next);
    },
    [deliver],
  );

  useEffect(() => {
    if (!paused && held.current !== null) {
      deliver(held.current);
      held.current = null;
    }
  }, [paused, deliver]);

  return [message, announce];
}
