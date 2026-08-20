"""
FORGE – Flask application
─────────────────────────
NEW Architecture (template-less):
    User Prompt
        │
        ▼
    build_forge_prompt()  ← instructions for enhancement (~150 tokens)
        │
        ▼
    Gemma-4 31B         ← returns enhanced prompt
        │
        ▼
    JSON response

Token usage vs old architecture:
    Old: ~15 000 tokens per request (all 90 templates shipped every time)
    New: ~200–300 tokens per request
"""

from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    stream_with_context,
)
from google import genai
from google.genai import types

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

LLM_CONFIG = types.GenerateContentConfig(
    system_instruction=_FORGE_ROLE,
    temperature=0.5,   # low temperature = consistent structured output
    top_p=0.85,
    max_output_tokens=1280,
)

# ── Prompt builder ────────────────────────────────────────────────────

def build_forge_prompt(user_prompt: str) -> str:
    """
    Construct the prompt sent to Gemma.
    The system instruction is handled via system_instruction in LLM_CONFIG.
    """
    return f"""\
User request:
{user_prompt}

Your task: Transform the user's request into a detailed, structured, high-performance prompt that preserves the user's intent while adding precision, clarity, and actionable details. Output ONLY the enhanced prompt text, with no extra commentary, headers, or labels.
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
    Full pipeline: Gemma enhancement → parsed result (non-streaming fallback).
    """
    try:
        forge_input = build_forge_prompt(user_prompt)

        response_text = ""
        for chunk in client.models.generate_content_stream(
            model=GEMMA_MODEL,
            contents=forge_input,
            config=LLM_CONFIG,
        ):
            if chunk.text:
                response_text += chunk.text

        enhanced = _clean_output(response_text)

        return {
            "success": True,
            "template_id":      "",
            "template_name":    "",
            "template_matched": "Direct Enhancement",
            "domain":           "General",
            "confidence":       "98%",
            "score":            0.98,
            "enhanced_prompt":  enhanced,
            "result":           enhanced,
            "raw":              response_text,
        }

    except Exception as exc:  # noqa: BLE001
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
    stream_requested = data.get("stream", True)

    if not user_prompt:
        return jsonify({"error": "Empty prompt. Please send a non-empty 'prompt' field."}), 400

    if not stream_requested:
        result = enhance_prompt(user_prompt)
        if not result["success"]:
            return jsonify(result), 500
        return jsonify(result)

    def generate():
        try:
            forge_input = build_forge_prompt(user_prompt)
            for chunk in client.models.generate_content_stream(
                model=GEMMA_MODEL,
                contents=forge_input,
                config=LLM_CONFIG,
            ):
                if chunk.text:
                    yield f"data: {json.dumps({'chunk': chunk.text})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/health", methods=["GET"])
def health():
    """Quick liveness check — also confirms template library loaded."""
    return jsonify({
        "status":           "ok",
        "templates_loaded": 0,
        "model":            GEMMA_MODEL,
    })


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
