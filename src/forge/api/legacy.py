"""FORGE 1.x routes: the original UI and the ``/enhance`` endpoint."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import closing

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    render_template,
    request,
    stream_with_context,
)

from forge.legacy.enhance import LegacyEnhancer, client_error_message

bp = Blueprint("legacy", __name__)

ENHANCER_EXTENSION = "forge.legacy_enhancer"

INVALID_REQUEST_MESSAGE = "Invalid request. Send a JSON object with a string 'prompt' field."


def get_enhancer() -> LegacyEnhancer:
    enhancer: LegacyEnhancer = current_app.extensions[ENHANCER_EXTENSION]
    return enhancer


@bp.route("/")
def home() -> str:
    return render_template("index.html")


@bp.route("/enhance", methods=["POST"])
def enhance() -> Response | tuple[Response, int]:
    data = request.get_json(silent=True) or {}
    raw_prompt = data.get("prompt") if isinstance(data, dict) else None
    if not isinstance(data, dict) or (raw_prompt is not None and not isinstance(raw_prompt, str)):
        # Previously these crashed with AttributeError and returned a 500 HTML page.
        return jsonify({"error": INVALID_REQUEST_MESSAGE}), 400
    user_prompt = (raw_prompt or "").strip()
    stream_requested = data.get("stream", True)  # interpreted by truthiness, as in FORGE 1.x

    if not user_prompt:
        return jsonify({"error": "Empty prompt. Please send a non-empty 'prompt' field."}), 400

    enhancer = get_enhancer()

    if not stream_requested:
        result = enhancer.enhance(user_prompt)
        if not result["success"]:
            return jsonify(result), 500
        return jsonify(result)

    def generate() -> Iterator[str]:
        try:
            # closing(): if the client disconnects, the provider stream (and its
            # connection and concurrency slot) is released immediately.
            with closing(enhancer.stream(user_prompt)) as chunks:
                for chunk in chunks:
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'error': client_error_message(exc)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")
