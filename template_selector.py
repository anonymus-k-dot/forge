"""
FORGE – Local template selection engine.

Scores every template against the user prompt using trigger matching,
then returns the best match, a confidence label, and the raw score.

Architecture:
    User prompt → preprocess → score_trigger() × 90 templates → highest score wins
    → if score == 0, domain-keyword fallback → confidence label

Scoring priorities
──────────────────
  20  Exact full-prompt match (rare)
  10  3+ word phrase found verbatim
   6  2-word phrase found verbatim
   3  Single word at exact word boundary
   2  Single word prefix match  (e.g. "crash" → "crashing")
   1  Trigger substring inside a compound word (e.g. "error" in "TypeError")
"""

from __future__ import annotations
import re
from typing import Tuple

from template_registry import ALL_TEMPLATES
from forge_templates.base import ForgeTemplate


# ── Text preprocessing ────────────────────────────────────────────────────

def _preprocess(text: str) -> str:
    """
    Normalise user input for robust trigger matching:
      • Split camelCase / PascalCase so "NullPointerException" becomes
        "null pointer exception" — making "exception" matchable.
      • Collapse extra whitespace.
      • Lowercase.
    """
    # PascalCase run → insert spaces (e.g. "NullPointerException" → "Null Pointer Exception")
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    # Snake / kebab / dot separators → spaces
    text = re.sub(r"[_\-.]", " ", text)
    text = text.lower()
    # Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()


# ── Per-trigger scoring ───────────────────────────────────────────────────

def _score_trigger(text: str, trigger: str) -> int:
    """
    Score a single trigger against the preprocessed prompt text.
    text and trigger are both already lowercased.
    """
    # ① Exact full-prompt match
    if text == trigger:
        return 20

    # ② Verbatim phrase / word found in text
    if trigger in text:
        n_words = len(trigger.split())
        if n_words >= 3:
            return 10
        if n_words == 2:
            return 6
        # Single word — check for true word boundary
        if re.search(r"\b" + re.escape(trigger) + r"\b", text):
            return 3
        # Substring inside a compound word (e.g. "error" in "typeerror")
        return 1

    # ③ Single-word prefix match (handles inflections: "crash" → "crashing")
    if " " not in trigger:
        if re.search(r"\b" + re.escape(trigger), text):
            return 2
        return 0

    # ④ Multi-word trigger — every word present as prefix (order-free)
    words = trigger.split()
    if all(re.search(r"\b" + re.escape(w), text) for w in words):
        return 3   # weaker than verbatim phrase

    # ⑤ Most words present (partial match for 3+ word triggers)
    if len(words) >= 3:
        hits = sum(1 for w in words if re.search(r"\b" + re.escape(w), text))
        if hits >= len(words) - 1:
            return 2

    return 0


def _score_template(text: str, template: ForgeTemplate) -> int:
    return sum(_score_trigger(text, t) for t in template.triggers)


# ── Domain-level fallback hints ──────────────────────────────────────────
# Only consulted when NO template-level trigger fires at all (score == 0).
# Keys are template IDs that best represent each domain.

_DOMAIN_HINTS: dict[str, list[str]] = {
    "C2":  ["code", "function", "class", "script", "program", "implement",
             "python", "javascript", "typescript", "java", "rust", "c++",
             "module", "library", "framework", "snippet", "method", "syntax"],
    "R2":  ["research", "study", "academic", "literature", "findings",
             "paper", "journal", "scholar", "survey", "hypothesis"],
    "W1":  ["write", "article", "blog", "essay", "content", "draft",
             "copy", "story", "report", "newsletter", "post"],
    "D1":  ["data", "analytics", "statistics", "dataset", "metric",
             "chart", "graph", "kpi", "dashboard", "insight"],
    "P1":  ["product", "feature", "roadmap", "sprint", "backlog",
             "launch", "user story", "stakeholder", "agile", "scrum"],
    "M5":  ["marketing", "campaign", "brand", "audience", "conversion",
             "lead", "funnel", "sales", "growth", "customer"],
}


# ── Public API ────────────────────────────────────────────────────────────

def select_template(user_prompt: str) -> Tuple[ForgeTemplate, str, int]:
    """
    Select the best-matching FORGE template for user_prompt.

    Returns
    ───────
    (template, confidence, score)
        template   — ForgeTemplate instance
        confidence — "HIGH" | "MEDIUM" | "LOW"
        score      — raw numeric score (for debug / logging)
    """
    text = _preprocess(user_prompt)

    # ── Score every template ──────────────────────────────────────────────
    scored = sorted(
        [(_score_template(text, t), t) for t in ALL_TEMPLATES.values()],
        key=lambda x: x[0],
        reverse=True,
    )
    best_score, best_template = scored[0]

    # ── Domain-hint fallback when nothing fires ───────────────────────────
    if best_score == 0:
        for fallback_id, keywords in _DOMAIN_HINTS.items():
            if any(kw in text for kw in keywords):
                best_template = ALL_TEMPLATES[fallback_id]
                best_score = 1
                break

    # ── Absolute last-resort fallback ─────────────────────────────────────
    if best_template is None:
        best_template = ALL_TEMPLATES["C1"]
        best_score = 0

    # ── Confidence band ───────────────────────────────────────────────────
    if best_score >= 20:
        confidence = "HIGH"
    elif best_score >= 8:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return best_template, confidence, best_score


# ── Debug helper ──────────────────────────────────────────────────────────

def explain_selection(user_prompt: str, top_n: int = 5) -> None:
    """Print the top-N scored templates. Useful during development."""
    text = _preprocess(user_prompt)
    scored = sorted(
        [(_score_template(text, t), t) for t in ALL_TEMPLATES.values()],
        key=lambda x: x[0],
        reverse=True,
    )
    print(f"\n  Prompt : {user_prompt!r}")
    print(f"  Parsed : {text!r}")
    print("  " + "─" * 55)
    for score, tmpl in scored[:top_n]:
        print(f"  {score:>4}  [{tmpl.id:>3}]  {tmpl.name}")
    print()


# ── Smoke test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("crashing with NullPointerException on login",    "C2 – Bug Triage"),
        ("write a blog post about AI trends in 2025",      "W1 – SEO Blog"),
        ("analyze customer churn patterns in my dataset",  "D8 – Cohort Analysis"),
        ("go-to-market plan for our new SaaS product",     "P5 – GTM"),
        ("unit tests for my authentication module",        "C4 – Test Generation"),
        ("Google Ads headlines for project management",    "M2 – Ad Headlines"),
        ("completely random thing nobody expects",          "fallback"),
    ]
    for prompt, expected in tests:
        tmpl, conf, score = select_template(prompt)
        tick = "✓" if tmpl.id in expected else "·"
        print(f"{tick} [{conf:6}] score={score:>3}  [{tmpl.id:>3}] {tmpl.name}")
        print(f"   expected: {expected}")
        print(f"   prompt  : {prompt}")
        print()