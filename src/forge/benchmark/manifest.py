"""Run manifest: everything that determines what a run asks and how it is checked.

``manifest_sha256 = sha256(canonical_json(manifest))``; ``manifest.json`` holds exactly those
canonical bytes. Identical inputs give the identical hash on every run; any change to the
protocol, dataset/task definitions, conditions (templates, system prompts, parameters),
model profiles, evaluator or FORGE version changes it.

Deliberately *not* in the manifest (recorded per run in ``run.json`` instead): run ID,
timestamps, budget limits, cache settings, output paths. They do not change what is asked or
how it is evaluated. Credentials, environment variables, API key variable names and
provider base URLs are never included.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

import forge
from forge.benchmark import PROTOCOL_ID, PROTOCOL_VERSION
from forge.benchmark.checks import EVALUATOR_NAME, EVALUATOR_VERSION
from forge.benchmark.conditions import TARGET_PARAMS, Condition
from forge.benchmark.dataset import Dataset, Task
from forge.infrastructure.cache import canonical_json
from forge.providers.router import ProviderRouter

MANIFEST_VERSION = 1


def profile_description(router: ProviderRouter, profile_name: str) -> dict[str, Any]:
    profile = router.profile(profile_name)
    return {
        "profile": profile.name,
        "provider": profile.provider,
        "provider_type": router.config.providers[profile.provider].type,
        "model": profile.model,
        "profile_params": asdict(profile.params),
    }


def build_manifest(
    *,
    dataset: Dataset,
    tasks: Sequence[Task],
    splits: Sequence[str],
    conditions: Sequence[Condition],
    target: dict[str, Any],
    rewriter: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "manifest_version": MANIFEST_VERSION,
        "protocol": {"id": PROTOCOL_ID, "version": PROTOCOL_VERSION},
        "forge_version": forge.__version__,
        "dataset": {
            "id": dataset.id,
            "version": dataset.version,
            "sha256": dataset.sha256,
            "task_count": len(dataset.tasks),
        },
        "selection": {
            "splits": sorted(splits),
            "tasks": [
                {
                    "id": t.id,
                    "sha256": t.sha256,
                    "split": t.split,
                    "category": t.category,
                    "spec_level": t.spec_level,
                }
                for t in tasks
            ],
        },
        "conditions": [c.describe() for c in conditions],
        "models": {
            "target": {**target, "request_params": asdict(TARGET_PARAMS)},
            "rewriter": rewriter,
        },
        "samples_per_case": 1,
        "evaluator": {"name": EVALUATOR_NAME, "version": EVALUATOR_VERSION},
    }


def manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return canonical_json(manifest)


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(manifest_bytes(manifest)).hexdigest()
