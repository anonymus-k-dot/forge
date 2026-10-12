import copy
import json
from pathlib import Path

import pytest

from forge.errors import ConfigurationError
from forge.providers.base import Capabilities, GenerationParams
from forge.providers.config import load_providers_config, parse_providers_config

from .helpers import BASE_CONFIG

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse(data):
    return parse_providers_config(json.dumps(data))


def with_provider(**fields):
    data = copy.deepcopy(BASE_CONFIG)
    data["providers"]["p"] = fields
    return data


class TestPackagedAndExampleConfig:
    def test_packaged_default_preserves_legacy_gemini(self):
        config = load_providers_config()
        assert config.default_model == "legacy-enhancer"
        profile = config.models["legacy-enhancer"]
        assert (profile.provider, profile.model) == ("gemini", "gemma-4-31b-it")
        gemini = config.providers["gemini"]
        assert gemini.type == "google_genai"
        assert gemini.api_key_env == "GEMINI_API_KEY"

    def test_example_config_is_valid(self):
        config = load_providers_config(REPO_ROOT / "config" / "providers.example.json")
        assert {"gemini", "groq", "ollama", "llamacpp"} <= set(config.providers)
        assert config.providers["ollama"].auth == "none"


class TestValidation:
    @pytest.mark.parametrize(
        ("provider", "expected"),
        [
            ({"type": "google_genai"}, "require api_key_env"),
            (
                {"type": "google_genai", "api_key_env": "K", "base_url": "https://x"},
                "not supported",
            ),
            ({"type": "openai_compatible", "api_key_env": "K"}, "require base_url"),
            ({"type": "openai_compatible", "base_url": "https://x"}, "requires api_key_env"),
            (
                {
                    "type": "openai_compatible",
                    "base_url": "http://x",
                    "auth": "none",
                    "api_key_env": "K",
                },
                "must not be set",
            ),
            ({"type": "openai_compatible", "base_url": "ftp://x", "auth": "none"}, "http(s)"),
            (
                {"type": "openai_compatible", "base_url": "https://u:pw@x", "auth": "none"},
                "credentials",
            ),
            ({"type": "openai_compatible", "base_url": "https://x?key=1", "auth": "none"}, "query"),
            ({"type": "fake", "max_concurrency": 0}, "max_concurrency"),
            ({"type": "fake", "retry": {"max_attempts": 0}}, "max_attempts"),
            ({"type": "unknown"}, "type"),
        ],
    )
    def test_invalid_provider(self, provider, expected):
        with pytest.raises(ConfigurationError, match="Invalid provider configuration") as info:
            parse(with_provider(**provider))
        assert expected in str(info.value)

    def test_unknown_provider_reference(self):
        data = copy.deepcopy(BASE_CONFIG)
        data["models"]["main"]["provider"] = "missing"
        with pytest.raises(ConfigurationError, match="unknown provider"):
            parse(data)

    def test_default_model_must_exist(self):
        data = copy.deepcopy(BASE_CONFIG)
        data["default_model"] = "nope"
        with pytest.raises(ConfigurationError, match="default_model"):
            parse(data)

    def test_secrets_in_config_are_rejected_without_being_echoed(self):
        secret = "gsk_live_SECRET_VALUE_1234567890"
        data = with_provider(type="openai_compatible", base_url="https://x", api_key=secret)
        with pytest.raises(ConfigurationError) as info:
            parse(data)
        assert secret not in str(info.value)
        # A key pasted into api_key_env fails the variable-name pattern, also without echo.
        data = with_provider(type="openai_compatible", base_url="https://x", api_key_env=secret)
        with pytest.raises(ConfigurationError) as info:
            parse(data)
        assert "api_key_env" in str(info.value)
        assert secret not in str(info.value)

    def test_invalid_json_reports_position_not_content(self):
        with pytest.raises(ConfigurationError, match="line 1, column") as info:
            parse_providers_config('{"api_key": "secret-xyz",', source="f.json")
        assert "secret-xyz" not in str(info.value)

    def test_missing_file(self, tmp_path):
        with pytest.raises(ConfigurationError, match="not found"):
            load_providers_config(tmp_path / "absent.json")


class TestConversions:
    def test_capability_overrides(self):
        config = parse(with_provider(type="fake", capabilities={"seed": True, "streaming": False}))
        caps = config.providers["p"].capabilities.apply_to(Capabilities())
        assert caps == Capabilities(
            streaming=False, system_instruction=True, seed=True, usage_reporting=False
        )

    def test_model_params(self):
        data = copy.deepcopy(BASE_CONFIG)
        data["models"]["main"]["params"] = {"temperature": 0.2, "max_output_tokens": 50}
        params = parse(data).models["main"].params.to_params()
        assert params == GenerationParams(temperature=0.2, max_output_tokens=50)

    def test_base_url_trailing_slash_removed(self):
        config = parse(
            with_provider(type="openai_compatible", base_url="http://h:1/v1/", auth="none")
        )
        assert config.providers["p"].base_url == "http://h:1/v1"
