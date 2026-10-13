"""Builders for benchmark tests: tasks, datasets, fake-provider routers and runs."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from forge.benchmark.dataset import Dataset, Task
from forge.benchmark.runner import BenchmarkRunner, RunOptions
from forge.providers.base import GenerationRequest
from forge.providers.config import parse_providers_config
from forge.providers.fake import FakeAdapter, FakeCall, FakeResponse, FakeStep
from forge.providers.router import ProviderRouter
from tests.providers.helpers import RecordingSleep

REPO_ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = REPO_ROOT / "benchmarks" / "pilot-v0"
OFFLINE_PROVIDERS = PILOT_DIR / "offline-providers.json"

PROVIDERS = {
    "default_model": "target",
    "providers": {
        "rw": {"type": "fake", "max_concurrency": 1, "retry": {"max_attempts": 2}},
        "tg": {"type": "fake", "max_concurrency": 1, "retry": {"max_attempts": 2}},
    },
    "models": {
        "rewriter": {"provider": "rw", "model": "rewriter-model"},
        "target": {"provider": "tg", "model": "target-model"},
    },
}


def make_task(
    task_id: str = "task-001",
    prompt: str = "List three fruits as bullet points, under 20 words.",
    checks: list[dict[str, Any]] | None = None,
    **fields: Any,
) -> Task:
    data = {
        "id": task_id,
        "version": 1,
        "category": "writing",
        "spec_level": "well",
        "split": "dev",
        "prompt": prompt,
        "checks": checks
        or [
            {"type": "list_items", "style": "bullet", "min": 3, "max": 3, "requirement": "three"},
            {"type": "word_count", "max": 20, "requirement": "under 20 words"},
        ],
        **fields,
    }
    return Task.model_validate_json(json.dumps(data))


def make_dataset(*tasks: Task, version: str = "0.0.1") -> Dataset:
    return Dataset("test-set", version, "test dataset", tasks or (make_task(),))


class Responder(FakeAdapter):
    """Fake adapter whose reply is computed from the request (``respond(model, request)``)."""

    def __init__(self, name: str, respond: Callable[[str, GenerationRequest], FakeStep]) -> None:
        super().__init__(name)
        self._respond = respond

    def _next_step(self, method: str, model: str, request: GenerationRequest) -> FakeStep:
        with self._lock:
            self.calls.append(FakeCall(method, model, request))
        return self._respond(model, request)


def text_reply(text: str) -> Callable[[str, GenerationRequest], FakeStep]:
    return lambda _model, _request: FakeResponse((text,) if text else ())


GOOD_ANSWER = "- apple\n- pear\n- plum"


def make_router(
    rewriter: FakeAdapter | None = None, target: FakeAdapter | None = None, **config: Any
) -> ProviderRouter:
    data = json.loads(json.dumps(PROVIDERS))
    data.update(config)
    return ProviderRouter(
        parse_providers_config(json.dumps(data)),
        adapters={
            "rw": rewriter or Responder("rw", text_reply("Rewritten: list three fruits.")),
            "tg": target or Responder("tg", text_reply(GOOD_ANSWER)),
        },
        sleep=RecordingSleep(),
    )


def options(tmp_path: Path, dataset: Dataset | None = None, **overrides: Any) -> RunOptions:
    values: dict[str, Any] = {
        "dataset": dataset or make_dataset(),
        "target_profile": "target",
        "rewriter_profile": "rewriter",
        "budget_limits": {"max_model_calls": 1000},
        "output_dir": tmp_path / "runs",
    }
    values.update(overrides)
    return RunOptions(**values)


def run(tmp_path: Path, router: ProviderRouter | None = None, **overrides: Any):
    runner_kwargs = {
        k: overrides.pop(k) for k in ("should_stop", "cache_store", "database") if k in overrides
    }
    return BenchmarkRunner(router or make_router(), **runner_kwargs).run(
        options(tmp_path, **overrides)
    )


def read_records(directory: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (directory / "results.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def read_run(directory: Path) -> dict[str, Any]:
    return json.loads((directory / "run.json").read_text(encoding="utf-8"))
