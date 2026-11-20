/** Device hints for keyboard labels (never used to change behaviour). */
export interface Platform {
  /** "⌘" on Apple devices, "Ctrl" elsewhere. */
  readonly modKey: string;
  /** A touch device without a fine pointer: keyboard shortcuts are not suggested. */
  readonly touchOnly: boolean;
}

export function detectPlatform(): Platform {
  const nav = typeof navigator !== "undefined" ? navigator : undefined;
  const data = nav as (Navigator & { userAgentData?: { platform?: string } }) | undefined;
  const name = data?.userAgentData?.platform || nav?.platform || "";
  const touchOnly =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(hover: none) and (pointer: coarse)").matches;
  return { modKey: /Mac|iPhone|iPad|iPod/i.test(name) ? "⌘" : "Ctrl", touchOnly };
}
