"""Shared builders for provider tests."""

from __future__ import annotations

import copy
import json
from typing import Any

from forge.providers.config import ProvidersConfig, parse_providers_config

BASE_CONFIG: dict[str, Any] = {
    "default_model": "main",
    "providers": {
        "p": {
            "type": "fake",
            "max_concurrency": 2,
            "acquire_timeout_seconds": 0,
            "retry": {
                "max_attempts": 3,
                "base_delay_seconds": 1.0,
                "max_delay_seconds": 4.0,
                "max_retry_after_seconds": 10.0,
            },
        }
    },
    "models": {"main": {"provider": "p", "model": "model-x"}},
}


def make_config(**provider_overrides: Any) -> ProvidersConfig:
    data = copy.deepcopy(BASE_CONFIG)
    data["providers"]["p"].update(provider_overrides)
    return parse_providers_config(json.dumps(data))


class RecordingSleep:
    """Replacement for time.sleep that records delays instead of waiting."""

    def __init__(self, on_sleep: Any = None) -> None:
        self.delays: list[float] = []
        self._on_sleep = on_sleep

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)
        if self._on_sleep is not None:
            self._on_sleep(seconds)


class MaxRng:
    """random.Random stand-in whose uniform() returns the upper bound (deterministic)."""

    def uniform(self, low: float, high: float) -> float:
        return high
