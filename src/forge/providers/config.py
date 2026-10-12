"""Secret-free provider and model-profile configuration (JSON).

Credentials are never stored in the file: a provider names the environment variable that
holds its key (``api_key_env``), and the value is read at first use.
"""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from forge.errors import ConfigurationError
from forge.providers.base import Capabilities, GenerationParams
from forge.providers.retry import RetryPolicy

DEFAULT_CONFIG_RESOURCE = "default_providers.json"

_NAME_PATTERN = r"^[a-z0-9][a-z0-9_.-]{0,63}$"
_ENV_VAR_PATTERN = r"^[A-Z_][A-Z0-9_]{0,127}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RetryConfig(_Strict):
    max_attempts: int = Field(default=3, ge=1, le=10)
    base_delay_seconds: float = Field(default=0.5, ge=0, le=60)
    max_delay_seconds: float = Field(default=8.0, ge=0, le=300)
    max_retry_after_seconds: float = Field(default=20.0, ge=0, le=600)

    def to_policy(self) -> RetryPolicy:
        return RetryPolicy(**self.model_dump())


class CapabilitiesConfig(_Strict):
    """Overrides of an adapter type's default capabilities; unset fields keep the default."""

    streaming: bool | None = None
    system_instruction: bool | None = None
    seed: bool | None = None
    usage_reporting: bool | None = None

    def apply_to(self, defaults: Capabilities) -> Capabilities:
        overrides = {k: v for k, v in self.model_dump().items() if v is not None}
        return Capabilities(**{**defaults.__dict__, **overrides})


class ProviderConfig(_Strict):
    type: Literal["google_genai", "openai_compatible", "fake"]
    base_url: str | None = None
    auth: Literal["bearer", "none"] = "bearer"
    api_key_env: str | None = Field(default=None, pattern=_ENV_VAR_PATTERN)
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    max_concurrency: int = Field(default=4, ge=1, le=256)
    acquire_timeout_seconds: float = Field(default=10.0, ge=0, le=600)
    retry: RetryConfig = RetryConfig()  # frozen, so a shared default is safe
    capabilities: CapabilitiesConfig = CapabilitiesConfig()
    max_tokens_field: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    fake_response: str | None = None

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("must be an absolute http(s) URL")
        if parts.username or parts.password:
            raise ValueError("must not contain credentials; use api_key_env")
        if parts.query or parts.fragment:
            raise ValueError("must not contain a query string or fragment")
        return value.rstrip("/")

    @model_validator(mode="after")
    def _check_type_requirements(self) -> ProviderConfig:
        if self.type == "google_genai":
            if not self.api_key_env:
                raise ValueError("google_genai providers require api_key_env")
            if self.base_url is not None:
                raise ValueError("base_url is not supported for google_genai providers")
        elif self.type == "openai_compatible":
            if self.base_url is None:
                raise ValueError("openai_compatible providers require base_url")
            if self.auth == "bearer" and not self.api_key_env:
                raise ValueError(
                    'auth "bearer" requires api_key_env (use auth "none" for keyless endpoints)'
                )
            if self.auth == "none" and self.api_key_env:
                raise ValueError('api_key_env must not be set when auth is "none"')
        if self.fake_response is not None and self.type != "fake":
            raise ValueError("fake_response is only valid for fake providers")
        return self


class ParamsConfig(_Strict):
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    seed: int | None = None

    def to_params(self) -> GenerationParams:
        return GenerationParams(**self.model_dump())


class ModelProfileConfig(_Strict):
    provider: str
    model: str = Field(min_length=1, max_length=256)
    params: ParamsConfig = ParamsConfig()


class ProvidersConfig(_Strict):
    default_model: str
    providers: dict[str, ProviderConfig] = Field(min_length=1)
    models: dict[str, ModelProfileConfig] = Field(min_length=1)

    @field_validator("providers", "models")
    @classmethod
    def _check_names(cls, value: dict[str, Any]) -> dict[str, Any]:
        for name in value:
            if not re.match(_NAME_PATTERN, name):
                raise ValueError(
                    f"invalid name {name!r}: use lowercase letters, digits, '-', '_', '.'"
                )
        return value

    @model_validator(mode="after")
    def _check_references(self) -> ProvidersConfig:
        for name, profile in self.models.items():
            if profile.provider not in self.providers:
                raise ValueError(f"model {name!r} references unknown provider {profile.provider!r}")
        if self.default_model not in self.models:
            raise ValueError(f"default_model {self.default_model!r} is not defined in models")
        return self


def load_providers_config(path: str | Path | None = None) -> ProvidersConfig:
    """Load and validate provider configuration from ``path``, or the packaged default."""
    if path is None:
        source = f"<packaged {DEFAULT_CONFIG_RESOURCE}>"
        text = (
            resources.files("forge.providers").joinpath(DEFAULT_CONFIG_RESOURCE).read_text("utf-8")
        )
    else:
        source = str(path)
        try:
            text = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ConfigurationError(f"Provider configuration file not found: {source}") from None
        except OSError as exc:
            raise ConfigurationError(
                f"Provider configuration file could not be read: {source} ({type(exc).__name__})"
            ) from None
    return parse_providers_config(text, source=source)


def parse_providers_config(text: str, *, source: str = "<string>") -> ProvidersConfig:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"Invalid JSON in provider configuration {source} at line {exc.lineno}, column {exc.colno}"
        ) from None
    try:
        return ProvidersConfig.model_validate(data)
    except ValidationError as exc:
        # Rebuild the message from locations and reasons only: pydantic's default message
        # echoes input values, which could include a secret pasted into the wrong field.
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ConfigurationError(f"Invalid provider configuration {source}: {problems}") from None
