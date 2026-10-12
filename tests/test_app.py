from app import GEMMA_MODEL, _clean_output, build_forge_prompt, enhance_prompt


class TestUnitFunctions:
    """Unit tests for internal helper and prompt crafting functions."""

    def test_build_forge_prompt_structure(self):
        user_input = "Write a python script to parse CSV files."
        prompt = build_forge_prompt(user_input)

        assert "User request:" in prompt
        assert user_input in prompt
        assert "Transform the user's request into a detailed" in prompt

    def test_clean_output_removes_template_headers(self):
        raw_output = (
            "[TEMPLATE MATCHED] Code Optimizer\n"
            "[CONFIDENCE] 99%\n"
            "[ENHANCED PROMPT]:\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Act as an expert Python engineer and design a robust CSV parser."
        )
        cleaned = _clean_output(raw_output)

        assert "[TEMPLATE MATCHED]" not in cleaned
        assert "[CONFIDENCE]" not in cleaned
        assert "[ENHANCED PROMPT]" not in cleaned
        assert "━━━━━━━━━━━━━━━━━━━━━" not in cleaned
        assert cleaned == "Act as an expert Python engineer and design a robust CSV parser."

    def test_clean_output_handles_plain_text(self):
        plain = "You are a senior data analyst. Analyze the following metrics..."
        assert _clean_output(plain) == plain

    def test_enhance_prompt_success(self, mock_genai_stream):
        mock_genai_stream(["Act as a ", "senior cloud architect."])
        result = enhance_prompt("Build AWS infra")

        assert result["success"] is True
        assert result["enhanced_prompt"] == "Act as a senior cloud architect."
        assert result["domain"] == "General"
        # Step 3: fabricated metrics deprecated; keys kept, values null.
        assert result["confidence"] is None and result["score"] is None

    def test_enhance_prompt_failure_handling(self, monkeypatch):
        import app as app_module

        def faulty_stream(*args, **kwargs):
            raise RuntimeError("API connection timeout")

        monkeypatch.setattr(app_module.client.models, "generate_content_stream", faulty_stream)
        result = enhance_prompt("Any prompt")

        assert result["success"] is False
        # Step 2: clients get a safe normalized message, never the raw exception text.
        assert result["enhanced_prompt"] == "Error: The model provider request failed unexpectedly."
        assert "API connection timeout" not in str(result)
        assert result["template_id"] == "ERROR"


class TestRoutes:
    """Integration tests for Flask API endpoints."""

    def test_home_page(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert b"<!DOCTYPE html>" in response.data
        assert b"FORGE" in response.data

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()

        assert data["status"] == "ok"
        assert data["model"] == GEMMA_MODEL
        assert data["templates_loaded"] == 0

    def test_enhance_missing_or_empty_prompt(self, client):
        # Empty body
        res1 = client.post("/enhance", json={})
        assert res1.status_code == 400
        assert "Empty prompt" in res1.get_json()["error"]

        # Blank whitespace prompt
        res2 = client.post("/enhance", json={"prompt": "   "})
        assert res2.status_code == 400
        assert "Empty prompt" in res2.get_json()["error"]

    def test_enhance_non_streaming_success(self, client, mock_genai_stream):
        mock_genai_stream(["Enhanced: Create a microservices architecture."])
        response = client.post("/enhance", json={
            "prompt": "Create microservices",
            "stream": False
        })

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["enhanced_prompt"] == "Enhanced: Create a microservices architecture."
        # Step 3: fabricated metrics deprecated; keys kept, values null.
        assert data["confidence"] is None and data["score"] is None

    def test_enhance_non_streaming_error_response(self, client, monkeypatch):
        import app as app_module

        def faulty_stream(*args, **kwargs):
            raise ConnectionError("Upstream service unavailable")

        monkeypatch.setattr(app_module.client.models, "generate_content_stream", faulty_stream)

        response = client.post("/enhance", json={
            "prompt": "Test prompt",
            "stream": False
        })
        assert response.status_code == 500
        data = response.get_json()
        assert data["success"] is False
        # Step 2: a connection failure is classified "unavailable" and reported safely.
        assert data["enhanced_prompt"] == (
            "Error: The model provider is currently unavailable. Please try again later."
        )
        assert "Upstream service unavailable" not in response.get_data(as_text=True)

    def test_enhance_streaming_success(self, client, mock_genai_stream):
        mock_genai_stream(["Chunk 1 ", "Chunk 2"])
        response = client.post("/enhance", json={
            "prompt": "Test prompt",
            "stream": True
        })

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["Content-Type"]

        stream_data = response.data.decode("utf-8")
        assert 'data: {"chunk": "Chunk 1 "}' in stream_data
        assert 'data: {"chunk": "Chunk 2"}' in stream_data
        assert 'data: {"done": true}' in stream_data

    def test_enhance_streaming_error_event(self, client, monkeypatch):
        import app as app_module

        def faulty_stream(*args, **kwargs):
            raise ValueError("Invalid payload")

        monkeypatch.setattr(app_module.client.models, "generate_content_stream", faulty_stream)

        response = client.post("/enhance", json={
            "prompt": "Test prompt",
            "stream": True
        })

        assert response.status_code == 200
        stream_data = response.data.decode("utf-8")
        # Step 2: same SSE error frame, with a safe message instead of the raw exception.
        assert stream_data == 'data: {"error": "The model provider request failed unexpectedly."}\n\n'
        assert "Invalid payload" not in stream_data
