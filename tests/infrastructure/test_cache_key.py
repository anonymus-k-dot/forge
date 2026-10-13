"""Cache-key correctness: stable for equivalent requests, distinct for any behavioral change,
never containing secrets."""

import re

import pytest

from forge.infrastructure.cache import (
    CACHE_KEY_VERSION,
    cache_key,
    cache_key_document,
    canonical_json,
)
from forge.providers.base import GenerationParams, GenerationRequest, Message
from forge.providers.fake import FakeAdapter
from forge.providers.google_genai import GoogleGenAIAdapter
from forge.providers.openai_compatible import OpenAICompatibleAdapter

SECRET = "sk-live-SECRET-VALUE-0123456789"
BASE = GenerationRequest(
    messages=(Message("user", "Summarise the report."),),
    system="Be concise.",
    params=GenerationParams(temperature=0.2, top_p=0.9, max_output_tokens=200),
)


def openai(**overrides):
    options = dict(
        base_url="https://api.example.test/v1",
        auth="bearer",
        api_key_env="K",
        get_secret=lambda _: SECRET,
        timeout_seconds=30,
    )
    options.update(overrides)
    return OpenAICompatibleAdapter("groq", **options)


def google():
    return GoogleGenAIAdapter(
        "gemini", api_key_env="K", get_secret=lambda _: SECRET, timeout_seconds=30
    )


ADAPTERS = {"openai": openai, "google": google, "fake": lambda: FakeAdapter("fake")}


@pytest.mark.parametrize("make", ADAPTERS.values(), ids=ADAPTERS.keys())
class TestStability:
    def test_identical_requests_give_identical_keys(self, make):
        a, b = make(), make()
        same = GenerationRequest(
            messages=(Message("user", "Summarise the report."),),
            system="Be concise.",
            params=GenerationParams(max_output_tokens=200, top_p=0.9, temperature=0.2),
        )
        assert cache_key(a, "m", BASE) == cache_key(b, "m", same)

    def test_key_is_sha256_hex(self, make):
        assert re.fullmatch(r"[0-9a-f]{64}", cache_key(make(), "m", BASE))

    def test_namespace_order_does_not_matter(self, make):
        adapter = make()
        assert cache_key(adapter, "m", BASE, {"a": 1, "b": 2}) == cache_key(
            adapter, "m", BASE, {"b": 2, "a": 1}
        )


VARIANTS = {
    "model": ("other-model", BASE, None),
    "system": (
        "m",
        GenerationRequest(messages=BASE.messages, system="Be verbose.", params=BASE.params),
        None,
    ),
    "no_system": ("m", GenerationRequest(messages=BASE.messages, params=BASE.params), None),
    "message_text": (
        "m",
        GenerationRequest((Message("user", "Summarise the report!"),), BASE.system, BASE.params),
        None,
    ),
    "message_role": (
        "m",
        GenerationRequest(
            (Message("assistant", "Summarise the report."),), BASE.system, BASE.params
        ),
        None,
    ),
    "extra_turn": (
        "m",
        GenerationRequest(BASE.messages + (Message("user", "More."),), BASE.system, BASE.params),
        None,
    ),
    "temperature": (
        "m",
        GenerationRequest(BASE.messages, BASE.system, GenerationParams(0.3, 0.9, 200)),
        None,
    ),
    "top_p": (
        "m",
        GenerationRequest(BASE.messages, BASE.system, GenerationParams(0.2, 0.8, 200)),
        None,
    ),
    "max_tokens": (
        "m",
        GenerationRequest(BASE.messages, BASE.system, GenerationParams(0.2, 0.9, 201)),
        None,
    ),
    "seed": (
        "m",
        GenerationRequest(BASE.messages, BASE.system, GenerationParams(0.2, 0.9, 200, seed=7)),
        None,
    ),
    "namespace": ("m", BASE, {"evaluator_version": "2"}),
}


@pytest.mark.parametrize("make", ADAPTERS.values(), ids=ADAPTERS.keys())
@pytest.mark.parametrize("variant", VARIANTS.values(), ids=VARIANTS.keys())
def test_any_behavioral_difference_changes_the_key(make, variant):
    adapter = make()
    model, request, namespace = variant
    assert cache_key(adapter, model, request, namespace) != cache_key(adapter, "m", BASE)


class TestEndpointIdentity:
    def test_different_endpoints_do_not_share_entries(self):
        assert cache_key(openai(), "m", BASE) != cache_key(
            openai(base_url="http://localhost:11434/v1", auth="none", api_key_env=None), "m", BASE
        )

    def test_max_tokens_field_name_is_part_of_the_request(self):
        assert cache_key(openai(), "m", BASE) != cache_key(
            openai(max_tokens_field="max_completion_tokens"), "m", BASE
        )

    def test_different_providers_do_not_share_entries(self):
        assert len({cache_key(make(), "m", BASE) for make in ADAPTERS.values()}) == 3

    def test_credentials_do_not_change_the_key(self):
        other = openai(get_secret=lambda _: "a-completely-different-key")
        assert cache_key(openai(), "m", BASE) == cache_key(other, "m", BASE)


class TestSecretsAndCanonicalForm:
    @pytest.mark.parametrize("make", ADAPTERS.values(), ids=ADAPTERS.keys())
    def test_no_secret_in_key_document(self, make):
        document = canonical_json(cache_key_document(make(), "m", BASE))
        assert SECRET.encode() not in document
        assert b"Authorization" not in document and b"Bearer" not in document

    def test_canonical_json_rules(self):
        assert canonical_json({"b": 1, "a": "ü"}) == '{"a":"ü","b":1}'.encode()
        assert canonical_json({"x": 1}) != canonical_json({"x": 1.0})
        with pytest.raises(ValueError):
            canonical_json({"x": float("nan")})

    def test_key_version_is_part_of_the_document(self):
        assert cache_key_document(FakeAdapter("f"), "m", BASE)["key_version"] == CACHE_KEY_VERSION
