"""
FORGE 1.x prompt enhancement
────────────────────────────
    User Prompt
        │
        ▼
    build_forge_prompt()  ← instructions for enhancement
        │
        ▼
    ProviderRouter        ← default profile: Gemini, gemma-4-31b-it
        │
        ▼
    JSON response / SSE chunks

The system prompt, prompt builder, output cleaner, generation parameters and response
fields are unchanged from the original ``app.py``. Model calls go through the provider
layer, so this module has no provider-specific code.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Generator
from contextlib import closing
from typing import Any

from forge.errors import ConfigurationError
from forge.providers.base import GenerationParams, GenerationRequest, TextDelta
from forge.providers.errors import ProviderError
from forge.providers.router import ProviderRouter

logger = logging.getLogger(__name__)

_FORGE_ROLE = """\
You are FORGE — an elite prompt-engineering system.

Your ONLY function: transform raw user input into a precision-crafted,
structured, high-performance AI prompt.

HARD RULES:
• Do NOT answer, solve, or explain the user's topic.
• Do NOT add preamble or commentary.
• Return ONLY the enhanced prompt text, nothing else.
• Preserve the user's intent — enhance precision, clarity, and actionability.
• The output must be 3–10× more detailed and actionable than the raw input.
• Include clear role, context, objective, steps, and format requirements as appropriate.
• Do NOT clutter output with excessive raw asterisks (**) around titles or section headers. Use clean headers, numbered lists, and bullet points.
"""

LEGACY_PARAMS = GenerationParams(
    temperature=0.5,  # low temperature = consistent structured output
    top_p=0.85,
    max_output_tokens=1280,
)

INTERNAL_ERROR_MESSAGE = "An internal error occurred while enhancing the prompt."

# ── Prompt builder ────────────────────────────────────────────────────────


def build_forge_prompt(user_prompt: str) -> str:
    """
    Construct the prompt sent to the model.
    The system instruction is sent separately (see build_request).
    """
    return f"""\
User request:
{user_prompt}

Your task: Transform the user's request into a detailed, structured, high-performance prompt that preserves the user's intent while adding precision, clarity, and actionable details. Output ONLY the enhanced prompt text, with no extra commentary, headers, or labels.
"""


def build_request(user_prompt: str) -> GenerationRequest:
    return GenerationRequest.from_prompt(
        build_forge_prompt(user_prompt), system=_FORGE_ROLE, params=LEGACY_PARAMS
    )


# ── Output parser ─────────────────────────────────────────────────────────


def clean_output(raw: str) -> str:
    """
    Strip any stray structural headers the model might echo back.
    Returns clean, user-ready enhanced prompt text.
    """
    # Remove any [TEMPLATE MATCHED] / [CONFIDENCE] / [ENHANCED PROMPT] echoes
    raw = re.sub(r"\[TEMPLATE MATCHED\][^\n]*\n?", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\[CONFIDENCE\][^\n]*\n?", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\[ENHANCED PROMPT\]\s*:?\s*\n?", "", raw, flags=re.IGNORECASE)
    # Remove leading/trailing separator lines
    raw = re.sub(r"^[━─=]{3,}\s*\n", "", raw, flags=re.MULTILINE)
    return raw.strip()


def client_error_message(exc: BaseException) -> str:
    """A message that is safe to return to clients: never raw upstream or exception text.

    Also logs the failure by category only (no prompt, message or upstream text).
    """
    if isinstance(exc, ProviderError):
        logger.warning(
            "enhance.failed",
            extra={
                "forge": {
                    "category": exc.category.value,
                    "provider": exc.provider,
                    "status_code": exc.status_code,
                }
            },
        )
        return exc.safe_message
    if isinstance(exc, ConfigurationError):
        logger.warning("enhance.failed", extra={"forge": {"category": "configuration"}})
        return str(exc)  # written by FORGE; names variables, never their values
    logger.exception("enhance.internal_error")
    return INTERNAL_ERROR_MESSAGE


# ── Enhancement service ───────────────────────────────────────────────────


class LegacyEnhancer:
    """Runs the FORGE 1.x enhancement through the provider router."""

    def __init__(self, router: ProviderRouter, model: str | None = None) -> None:
        self._router = router
        self._model = model

    def stream(self, user_prompt: str) -> Generator[str, None, None]:
        """Yield raw text chunks as produced (the streaming path is not cleaned, as before)."""
        with closing(self._router.stream(build_request(user_prompt), model=self._model)) as events:
            for event in events:
                if isinstance(event, TextDelta) and event.text:
                    yield event.text

    def enhance(self, user_prompt: str) -> dict[str, Any]:
        """
        Full pipeline: enhancement → cleaned result (non-streaming fallback).
        """
        try:
            response_text = "".join(self.stream(user_prompt))
            enhanced = clean_output(response_text)

            return {
                "success": True,
                "template_id": "",
                "template_name": "",
                "template_matched": "Direct Enhancement",
                "domain": "General",
                # Deprecated: never measured. Kept as null for one release so the response
                # schema is unchanged; see CHANGELOG.md and docs/api.md.
                "confidence": None,
                "score": None,
                "enhanced_prompt": enhanced,
                "result": enhanced,
                "raw": response_text,
            }

        except Exception as exc:  # noqa: BLE001
            message = client_error_message(exc)
            return {
                "success": False,
                "template_id": "ERROR",
                "template_matched": "Error",
                "confidence": None,  # deprecated, see above
                "score": None,
                "enhanced_prompt": f"Error: {message}",
                "result": f"Error: {message}",
                "raw": f"Error: {message}",
            }
