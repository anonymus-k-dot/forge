"""docs/api.md must describe the implemented contract (guards against documentation drift)."""

import json
import re
from pathlib import Path

import pytest

from forge.api.legacy import INVALID_REQUEST_MESSAGE
from forge.app import create_app
from forge.legacy.enhance import INTERNAL_ERROR_MESSAGE
from forge.logging import _VALID_REQUEST_ID
from forge.providers import errors
from forge.providers.config import load_providers_config
from forge.providers.fake import FakeAdapter, FakeResponse
from forge.providers.router import ProviderRouter
from forge.settings import Settings

DOC = (Path(__file__).resolve().parent.parent / "docs" / "api.md").read_text(encoding="utf-8")


def doc_json_block(heading_pattern):
    match = re.search(heading_pattern + r".*?```json\n(.*?)```", DOC, re.S)
    assert match, f"no JSON example after {heading_pattern!r} in docs/api.md"
    return json.loads(match.group(1))


@pytest.fixture
def client():
    adapter = FakeAdapter("gemini", [FakeResponse(("ok",))], default=errors.RateLimitError("x"))
    router = ProviderRouter(
        load_providers_config(), adapters={"gemini": adapter}, sleep=lambda s: None
    )
    return create_app(Settings(), router=router).test_client()


def test_every_client_error_message_is_documented_and_vice_versa():
    code = {
        cls.client_message
        for cls in (
            errors.AuthenticationError,
            errors.InvalidRequestError,
            errors.RateLimitError,
            errors.ProviderUnavailableError,
            errors.ConcurrencyLimitError,
            errors.ProviderTimeoutError,
            errors.UpstreamServerError,
            errors.MalformedResponseError,
            errors.UnsupportedCapabilityError,
            errors.UnknownProviderError,
        )
    } | {INTERNAL_ERROR_MESSAGE}
    documented = set(re.findall(r"^\| [a-z_ ()]+ \| `([^`]+)` \|$", DOC, re.M))
    assert documented == code


def test_request_id_pattern_is_documented():
    assert f"`{_VALID_REQUEST_ID.pattern}`" in DOC


def test_400_messages_are_documented():
    assert "Empty prompt. Please send a non-empty 'prompt' field." in DOC
    assert INVALID_REQUEST_MESSAGE in DOC


def test_documented_success_and_error_bodies_match(client):
    success = client.post("/enhance", json={"prompt": "p", "stream": False}).get_json()
    documented = doc_json_block(r"#### Response — Non-Streaming")
    assert set(documented) == set(success)
    assert documented["confidence"] is None and documented["score"] is None
    assert success["confidence"] is None and success["score"] is None

    error = client.post("/enhance", json={"prompt": "p", "stream": False})
    documented_error = doc_json_block(r"##### 500 Internal Server Error")
    assert error.status_code == 500
    assert set(documented_error) == set(error.get_json())
    assert documented_error["enhanced_prompt"] == error.get_json()["enhanced_prompt"]


def test_documented_health_body_matches(client):
    assert set(doc_json_block(r"- \*\*URL\*\*: `/health`")) == set(client.get("/health").get_json())


def test_documented_ready_states_match_implementation(client):
    documented = set(re.findall(r"^\| `(\w+)` \| (?:200|503) \|", DOC, re.M))
    assert documented == {"ok", "not_configured", "unavailable", "migrations_pending"}
    assert set(doc_json_block(r"- \*\*URL\*\*: `/ready`")) == {"status", "checks"}
    response = client.get("/ready")  # no database configured in this fixture
    assert response.status_code == 503
    assert response.get_json() == {"status": "not_ready", "checks": {"database": "not_configured"}}
