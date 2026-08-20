import os
from unittest.mock import MagicMock

import pytest

# Ensure GEMINI_API_KEY is present in environment before app imports
os.environ.setdefault("GEMINI_API_KEY", "test-mock-gemini-key")

from app import app  # noqa: E402


@pytest.fixture
def flask_app():
    """Provides the Flask application configured for testing."""
    app.config.update({
        "TESTING": True,
    })
    return app


@pytest.fixture
def client(flask_app):
    """Provides a test client for sending HTTP requests."""
    return flask_app.test_client()


class MockChunk:
    """Mock structure mimicking google-genai streaming chunk."""
    def __init__(self, text: str):
        self.text = text


@pytest.fixture
def mock_genai_stream(monkeypatch):
    """Factory fixture to mock client.models.generate_content_stream."""
    def _setter(chunks):
        mock_chunks = [MockChunk(c) for c in chunks]
        mock_generate = MagicMock(return_value=iter(mock_chunks))
        import app as app_module
        monkeypatch.setattr(app_module.client.models, "generate_content_stream", mock_generate)
        return mock_generate

    return _setter
