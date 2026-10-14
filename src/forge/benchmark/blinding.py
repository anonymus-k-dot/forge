"""Blinded export of target answers for human rating, and the ratings schema (Step 7).

``export_blind`` writes, for one verified run, a rater folder containing only:

    items.jsonl            what raters see: an opaque ``item_id``, the task ID, the original
                           task prompt and one answer. Tasks and the answers within a task are
                           shuffled with a recorded seed. No condition name, transformed
                           prompt, model, profile, latency, usage or record order is included.
    rating-template.jsonl  one empty rating per item

and, at a separate path that must lie outside the rater folder, the key: item → condition
mapping and the outcomes that are not rated. The key is never given to raters. This is an
access-separation safeguard, not cryptographic protection: anyone with the key, the run
directory, or the run's results and the blinding seed can recover the conditions.

Outcomes that cannot be rated are classified, before anything is seen, as:

    condition_failure  the condition produced no usable answer: an empty target answer, an
                       empty rewrite, or a provider ``invalid_request`` for the condition's
                       own request — scored 0 on the primary outcome
    infrastructure     provider/runtime failures (rate limit, timeout, unavailable, server
                       error, malformed response, authentication, configuration,
                       unsupported capability, unknown) and pairs that were never run —
                       excluded from scoring and reported
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from forge.benchmark.dataset import Dataset
from forge.benchmark.records import ResultRecord
from forge.benchmark.verify import verify_run
from forge.errors import ConfigurationError
from forge.infrastructure.cache import canonical_json

KEY_VERSION = 1
CONDITION_FAILURE_ERRORS = frozenset({"invalid_request"})


class Rating(BaseModel):
    """One rater's judgement of one item (rubric ``forge-step7-answer-quality`` 1.0.0)."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    item_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    rater_id: str = Field(min_length=1, max_length=64)
    task_success: int = Field(ge=0, le=3)
    instruction_adherence: int = Field(ge=0, le=2)
    factual_error: bool
    unsupported_claim: bool
    # An adjudicated rating resolves a disagreement and replaces the raters' scores.
    adjudicated: bool = False
    notes: str | None = Field(default=None, max_length=2000)


def load_ratings(path: str | Path) -> list[Rating]:
    ratings = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            ratings.append(Rating.model_validate_json(line))
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}"
                for e in exc.errors()
            )
            raise ConfigurationError(f"{path}:{number}: invalid rating ({problems})") from None
    return ratings


def classify_unrated(record: ResultRecord) -> tuple[str, str] | None:
    """(category, reason) for a record whose answer cannot be rated; None if ratable."""
    if record.status == "evaluated":
        if record.evaluation is not None and record.evaluation.empty_output:
            return "condition_failure", "empty_answer"
        return None
    if record.status == "not_run":
        return "infrastructure", f"not_run:{record.reason}"
    if record.reason == "empty_transform_output":
        return "condition_failure", "empty_rewrite"
    errors = [e.error_category for e in record.executions if e.status == "error"]
    category = errors[-1] if errors else "unknown"
    if category in CONDITION_FAILURE_ERRORS:
        return "condition_failure", f"provider_error:{category}"
    return "infrastructure", f"provider_error:{category}"


def _records(directory: Path) -> list[ResultRecord]:
    return [
        ResultRecord.model_validate_json(line)
        for line in (directory / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _inside(path: Path, folder: Path) -> bool:
    resolved, root = path.resolve(), folder.resolve()
    return resolved == root or root in resolved.parents


def export_blind(
    run_dir: str | Path,
    dataset: Dataset,
    out_dir: str | Path,
    *,
    key_path: str | Path,
    seed: int,
) -> dict[str, Any]:
    run_path, out, key_file = Path(run_dir), Path(out_dir), Path(key_path)
    if _inside(key_file, out):
        raise ConfigurationError("The key must be stored outside the rater folder (--out).")
    if key_file.exists():
        raise ConfigurationError(f"Key file already exists: {key_file}")
    report = verify_run(run_path, dataset)
    if not report.valid:
        raise ConfigurationError(f"Run does not verify: {'; '.join(report.problems[:3])}")
    run_doc = json.loads((run_path / "run.json").read_bytes())
    tasks = {t.id: t for t in dataset.tasks}
    by_task: dict[str, list[ResultRecord]] = {}
    for record in _records(run_path):
        by_task.setdefault(record.task_id, []).append(record)

    rng = random.Random(seed)
    task_order = sorted(by_task)
    rng.shuffle(task_order)
    used: set[str] = set()

    def new_id() -> str:
        while True:
            candidate = f"{rng.getrandbits(64):016x}"
            if candidate not in used:
                used.add(candidate)
                return candidate

    items: list[dict[str, Any]] = []
    key_items: dict[str, dict[str, str]] = {}
    unrated: list[dict[str, str]] = []
    for task_id in task_order:
        task = tasks[task_id]
        ratable = []
        for record in sorted(by_task[task_id], key=lambda r: r.condition):
            outcome = classify_unrated(record)
            if outcome is not None:
                unrated.append(
                    {
                        "task_id": task_id,
                        "condition": record.condition,
                        "category": outcome[0],
                        "reason": outcome[1],
                    }
                )
                continue
            ratable.append(record)
        rng.shuffle(ratable)
        for position, record in enumerate(ratable, 1):
            item_id = new_id()
            answer = record.executions[-1].output_text
            assert answer is not None
            items.append(
                {
                    "item_id": item_id,
                    "task_id": task_id,
                    "position": position,
                    "task_prompt": task.prompt,
                    "answer": answer,
                }
            )
            key_items[item_id] = {"task_id": task_id, "condition": record.condition}

    key = {
        "key_version": KEY_VERSION,
        "run_id": run_doc["run_id"],
        "manifest_sha256": run_doc["manifest_sha256"],
        "dataset_sha256": dataset.sha256,
        "measurement": run_doc["measurement"],
        "seed": seed,
        "items": key_items,
        "unrated": unrated,
    }
    out.mkdir(parents=True, exist_ok=False)
    _write_jsonl(out / "items.jsonl", items)
    _write_jsonl(
        out / "rating-template.jsonl",
        (
            {
                "item_id": i["item_id"],
                "rater_id": "",
                "task_success": None,
                "instruction_adherence": None,
                "factual_error": None,
                "unsupported_claim": None,
                "notes": None,
            }
            for i in items
        ),
    )
    key_file.parent.mkdir(parents=True, exist_ok=True)
    with key_file.open("xb") as handle:  # never overwrite an existing key
        handle.write(canonical_json(key))
    return {
        "items": len(items),
        "unrated": len(unrated),
        "rater_directory": str(out),
        "rater_files": sorted(p.name for p in out.iterdir()),
        "key": str(key_file),
    }


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_bytes(b"".join(canonical_json(row) + b"\n" for row in rows))
