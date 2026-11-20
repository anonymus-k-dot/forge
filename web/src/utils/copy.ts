/** What the copy menu puts on the clipboard, and how it gets there. */
export type CopyFormat = "text" | "json";

/** "Copy text" is exactly the displayed output; "Copy as JSON" wraps it (same as the legacy UI). */
export function copyPayload(format: CopyFormat, output: string, partial: boolean): string {
  if (format === "text") return output;
  const document: { enhanced_prompt: string; partial?: true } = { enhanced_prompt: output };
  if (partial) document.partial = true;
  return JSON.stringify(document, null, 2);
}

export type CopyResult = "copied" | "failed";

/** The browser features used for copying (injectable for tests). */
export interface ClipboardEnvironment {
  readonly clipboard?: { writeText(text: string): Promise<void> } | undefined;
  readonly document?: Document | undefined;
}

function browserEnvironment(): ClipboardEnvironment {
  return {
    clipboard: typeof navigator !== "undefined" ? navigator.clipboard : undefined,
    document: typeof document !== "undefined" ? document : undefined,
  };
}

/**
 * Copies text. Uses the Clipboard API where it exists (HTTPS and localhost pages); on
 * plain-HTTP pages, or if the browser refuses, falls back to the older copy command.
 * Must be called from a user action (click or key press).
 */
export async function copyToClipboard(
  text: string,
  environment: ClipboardEnvironment = browserEnvironment(),
): Promise<CopyResult> {
  const { clipboard, document } = environment;
  if (clipboard && typeof clipboard.writeText === "function") {
    try {
      await clipboard.writeText(text);
      return "copied";
    } catch {
      // Permission refused or document not focused: try the fallback below.
    }
  }
  return document && copyWithCommand(text, document) ? "copied" : "failed";
}

function copyWithCommand(text: string, document: Document): boolean {
  if (typeof document.execCommand !== "function" || !document.body) return false;
  const previous = document.activeElement;
  const buffer = document.createElement("textarea");
  buffer.value = text;
  buffer.setAttribute("readonly", "");
  buffer.setAttribute("aria-hidden", "true");
  buffer.className = "clipboard-buffer";
  document.body.append(buffer);
  buffer.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  }
  buffer.remove();
  if (previous && typeof (previous as HTMLElement).focus === "function") {
    (previous as HTMLElement).focus();
  }
  return copied;
}
