"""
FORGE – Flask application
─────────────────────────
NEW Architecture:
    User Prompt
        │
        ▼
    select_template()   ← pure-Python, no LLM, zero tokens
        │
        ▼
    build_forge_prompt()  ← injects ONLY the selected template (~200 tokens)
        │
        ▼
    Gemma-4 31B         ← returns enhanced prompt
        │
        ▼
    JSON response

Token usage vs old architecture:
    Old: ~15 000 tokens per request (all 90 templates shipped every time)
    New: ~300–400 tokens per request
"""

from __future__ import annotations

import os
import re

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from google import genai
from google.genai import types

from template_selector import select_template

load_dotenv()

# ── App & client ──────────────────────────────────────────────────────────

app = Flask(__name__)

_api_key = os.getenv("GEMINI_API_KEY")
if not _api_key:
    raise ValueError(
        "GEMINI_API_KEY is not set. "
        "Add it to your .env file: GEMINI_API_KEY=your_key_here"
    )

client = genai.Client(api_key=_api_key)

# ── Model configuration ───────────────────────────────────────────────────

GEMMA_MODEL = "gemma-4-31b-it"

LLM_CONFIG = types.GenerateContentConfig(
    temperature=0.3,   # low temperature = consistent structured output
    top_p=0.85,
    max_output_tokens=2048,
)

# ── Prompt builder ────────────────────────────────────────────────────────

_FORGE_ROLE = """\
You are FORGE — an elite prompt-engineering system.

Your ONLY function: transform raw user input into a precision-crafted,
structured, high-performance AI prompt using the provided template.

HARD RULES:
• Do NOT answer, solve, or explain the user's topic.
• Do NOT add preamble or commentary.
• Return ONLY the enhanced prompt text, nothing else.
• Preserve the user's intent — enhance precision and structure, not direction.
• The output must be 3–10× more detailed and actionable than the raw input.
"""


def build_forge_prompt(user_prompt: str, template) -> str:
    """
    Construct the minimal, high-signal prompt sent to Gemma.
    Only the selected template's structure is included — not all 90.
    """
    return f"""\
{_FORGE_ROLE}

━━━ SELECTED TEMPLATE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ID:      {template.id}
Name:    {template.name}
Domain:  {template.domain}

━━━ TEMPLATE STRUCTURE (your output skeleton) ━━━━━━━━━━━━━━━━━━━━━━━━━━━
{template.structure.strip()}

━━━ USER REQUEST ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{user_prompt.strip()}

━━━ YOUR TASK ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Using the TEMPLATE STRUCTURE as your skeleton:

1. Assign the role exactly as specified.
2. Include EVERY structural section listed in the template.
3. Fill each section with the user's specific context, topic, and technology.
4. Add expert-level precision: concrete directives, output requirements, formatting rules.
5. Make the prompt immediately usable by any capable AI with zero further editing.

OUTPUT: Return ONLY the enhanced prompt. No headers, no labels, no commentary.
"""


# ── Output parser ─────────────────────────────────────────────────────────

def _clean_output(raw: str) -> str:
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


# ── Core enhancement function ─────────────────────────────────────────────

def enhance_prompt(user_prompt: str) -> dict:
    """
    Full pipeline: local template selection → Gemma enhancement → parsed result.
    """
    try:
        # 1. Select template locally (0 LLM tokens)
        template, confidence, score = select_template(user_prompt)

        # 2. Build lean prompt (~300–400 tokens)
        forge_input = build_forge_prompt(user_prompt, template)

        # 3. Stream from Gemma
        response_text = ""
        for chunk in client.models.generate_content_stream(
            model=GEMMA_MODEL,
            contents=forge_input,
            config=LLM_CONFIG,
        ):
            if chunk.text:
                response_text += chunk.text

        # 4. Clean and return
        enhanced = _clean_output(response_text)

        return {
            "success": True,
            "template_id":      template.id,
            "template_name":    template.name,
            "template_matched": f"{template.id} – {template.name}",
            "domain":           template.domain,
            "confidence":       confidence,
            "score":            score,
            "enhanced_prompt":  enhanced,
            "result":           enhanced,   # kept for frontend backward-compat
            "raw":              response_text,
        }

    except Exception as exc:
        return {
            "success": False,
            "template_id":      "ERROR",
            "template_matched": "Error",
            "confidence":       "N/A",
            "score":            0,
            "enhanced_prompt":  f"Error: {exc}",
            "result":           f"Error: {exc}",
            "raw":              f"Error: {exc}",
        }


# ── Flask routes ──────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/enhance", methods=["POST"])
def enhance():
    data = request.get_json(silent=True) or {}
    user_prompt = data.get("prompt", "").strip()

    if not user_prompt:
        return jsonify({"error": "Empty prompt. Please send a non-empty 'prompt' field."}), 400

    result = enhance_prompt(user_prompt)

    if not result["success"]:
        return jsonify(result), 500

    return jsonify({
        "success":          True,
        "template":         result["template_matched"],
        "template_id":      result["template_id"],
        "domain":           result["domain"],
        "confidence":       result["confidence"],
        "score":            result["score"],
        "result":           result["enhanced_prompt"],       # primary field
        "enhanced_prompt":  result["enhanced_prompt"],       # alias
    })


@app.route("/health", methods=["GET"])
def health():
    """Quick liveness check — also confirms template library loaded."""
    from template_registry import ALL_TEMPLATES
    return jsonify({
        "status":           "ok",
        "templates_loaded": len(ALL_TEMPLATES),
        "model":            GEMMA_MODEL,
    })


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)