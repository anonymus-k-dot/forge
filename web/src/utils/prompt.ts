/** Prompt limits and validation (the backend accepts any non-empty prompt; these are the UI's). */
export const MIN_PROMPT_CHARS = 10;
export const MAX_PROMPT_CHARS = 2000;
/** The counter turns to a warning from here. */
export const WARN_PROMPT_CHARS = 1800;

const numberFormat = new Intl.NumberFormat("en-US");
export const formatCount = (n: number): string => numberFormat.format(n);

/** Characters as a person counts them: code points, so an emoji counts once. */
export function countCharacters(text: string): number {
  return Array.from(text).length;
}

export type PromptProblem = "empty" | "too-short" | "too-long";

export interface PromptValidation {
  readonly problem: PromptProblem;
  readonly message: string;
}

export function validatePrompt(text: string): PromptValidation | null {
  const trimmed = countCharacters(text.trim());
  if (trimmed === 0) return { problem: "empty", message: "Enter a prompt to enhance." };
  if (trimmed < MIN_PROMPT_CHARS) {
    return {
      problem: "too-short",
      message: `Enter at least ${MIN_PROMPT_CHARS} characters so there is something to enhance.`,
    };
  }
  const total = countCharacters(text);
  if (total > MAX_PROMPT_CHARS) {
    return {
      problem: "too-long",
      message:
        `The prompt is ${formatCount(total)} characters; the limit is ` +
        `${formatCount(MAX_PROMPT_CHARS)}. Remove ${formatCount(total - MAX_PROMPT_CHARS)} to continue.`,
    };
  }
  return null;
}

export type CounterLevel = "normal" | "warn" | "over";

export function counterLevel(count: number): CounterLevel {
  if (count > MAX_PROMPT_CHARS) return "over";
  if (count >= WARN_PROMPT_CHARS) return "warn";
  return "normal";
}
