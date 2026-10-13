"""Versioned task dataset: schema, loading, validation and hashing.

A dataset directory holds ``dataset.json`` (id, version, description, tasks file name) and a
JSON Lines task file. Every check carries a ``requirement``: a phrase that must appear
verbatim (case-insensitively) in the task's own prompt. So every check traces back to
something all conditions receive, and no condition can be scored on a hidden requirement.

Hashes (SHA-256 over ``forge.infrastructure.cache.canonical_json``):
    task_sha256     the validated task definition (``Task.model_dump(mode="json")``),
                    identifying exactly what was asked and how it is checked
    dataset_sha256  ``{"id", "version", "tasks": [{"id", "sha256"}, ... sorted by id]}``
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from forge.errors import ConfigurationError
from forge.infrastructure.cache import canonical_json

TASK_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{2,63}$"
CATEGORIES = (
    "coding",
    "writing",
    "summarization",
    "data_analysis",
    "reasoning",
    "structured_output",
    "agent_tool_use",
    "retrieval",
)
SPEC_LEVELS = ("well", "partial", "vague")
SPLITS = ("dev", "heldout")
REGEX_FLAGS = {"IGNORECASE": re.IGNORECASE, "MULTILINE": re.MULTILINE, "DOTALL": re.DOTALL}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _CheckBase(_Strict):
    # Verbatim (case-insensitive) phrase of the task prompt this check enforces.
    requirement: str = Field(min_length=1, max_length=300)


class _Range(_CheckBase):
    min: int | None = Field(default=None, ge=0)
    max: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_range(self) -> _Range:
        if self.min is None and self.max is None:
            raise ValueError("set min, max, or both")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min must not exceed max")
        return self


class WordCount(_Range):
    type: Literal["word_count"]


class CharCount(_Range):
    type: Literal["char_count"]


class LineCount(_Range):
    type: Literal["line_count"]


class ListItems(_Range):
    type: Literal["list_items"]
    style: Literal["any", "bullet", "numbered"] = "any"


class Contains(_CheckBase):
    type: Literal["contains"]
    text: str = Field(min_length=1, max_length=300)
    case_sensitive: bool = False


class NotContains(_CheckBase):
    type: Literal["not_contains"]
    text: str = Field(min_length=1, max_length=300)
    case_sensitive: bool = False


class Regex(_CheckBase):
    type: Literal["regex"]
    pattern: str = Field(min_length=1, max_length=500)
    flags: tuple[Literal["IGNORECASE", "MULTILINE", "DOTALL"], ...] = ()

    @model_validator(mode="after")
    def _compiles(self) -> Regex:
        try:
            re.compile(self.pattern, compile_flags(self.flags))
        except re.error as exc:
            raise ValueError(f"pattern does not compile: {exc}") from None
        return self


class Json(_CheckBase):
    type: Literal["json"]
    kind: Literal["object", "array"]
    required_keys: tuple[str, ...] = ()
    min_items: int | None = Field(default=None, ge=0)
    max_items: int | None = Field(default=None, ge=0)
    allow_fence: bool = False

    @model_validator(mode="after")
    def _consistent(self) -> Json:
        if self.kind == "array" and self.required_keys:
            raise ValueError("required_keys applies to objects only")
        if self.kind == "object" and (self.min_items is not None or self.max_items is not None):
            raise ValueError("min_items/max_items apply to arrays only")
        if (
            self.min_items is not None
            and self.max_items is not None
            and self.min_items > self.max_items
        ):
            raise ValueError("min_items must not exceed max_items")
        return self


class CodeBlock(_CheckBase):
    type: Literal["code_block"]
    language: str | None = Field(default=None, min_length=1, max_length=40)
    min_blocks: int = Field(default=1, ge=1)


Check = Annotated[
    WordCount
    | CharCount
    | LineCount
    | ListItems
    | Contains
    | NotContains
    | Regex
    | Json
    | CodeBlock,
    Field(discriminator="type"),
]


class Task(_Strict):
    id: str = Field(pattern=TASK_ID_PATTERN)
    version: int = Field(ge=1)
    category: Literal[
        "coding",
        "writing",
        "summarization",
        "data_analysis",
        "reasoning",
        "structured_output",
        "agent_tool_use",
        "retrieval",
    ]
    spec_level: Literal["well", "partial", "vague"]
    split: Literal["dev", "heldout"]
    prompt: str = Field(min_length=1, max_length=4000)
    checks: tuple[Check, ...] = Field(min_length=1)
    # Authoring notes for humans; never sent to any condition.
    notes: str | None = Field(default=None, max_length=1000)
    # Set when the task's checks cannot distinguish a substantive answer from a trivial one
    # without subjective grading: the task is then excluded from "all checks passed"
    # metrics (and reported with its reason). Never sent to any condition.
    limited_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def _requirements_are_in_the_prompt(self) -> Task:
        prompt = self.prompt.casefold()
        for index, check in enumerate(self.checks):
            if check.requirement.casefold() not in prompt:
                raise ValueError(
                    f"checks[{index}].requirement is not a verbatim phrase of the prompt"
                )
        return self

    def definition(self) -> dict[str, Any]:
        document = self.model_dump(mode="json")
        # Omitted when unset, so definitions (and hashes) of tasks written before this field
        # existed are unchanged.
        if document["limited_reason"] is None:
            del document["limited_reason"]
        return document

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.definition())).hexdigest()


class DatasetMeta(_Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(min_length=1, max_length=2000)
    tasks_file: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.jsonl$")


@dataclass(frozen=True)
class Dataset:
    id: str
    version: str
    description: str
    tasks: tuple[Task, ...]

    @property
    def sha256(self) -> str:
        return dataset_sha256(self.id, self.version, self.tasks)

    def select(
        self, *, splits: Iterable[str] = SPLITS, task_ids: Iterable[str] | None = None
    ) -> tuple[Task, ...]:
        """Tasks in the given splits (and, if given, with these IDs), ordered by ID."""
        wanted_splits = set(splits)
        unknown_splits = wanted_splits - set(SPLITS)
        if unknown_splits:
            raise ConfigurationError(f"Unknown split(s): {sorted(unknown_splits)}")
        chosen = [t for t in self.tasks if t.split in wanted_splits]
        if task_ids is not None:
            wanted = set(task_ids)
            missing = wanted - {t.id for t in self.tasks}
            if missing:
                raise ConfigurationError(f"Unknown task id(s): {sorted(missing)}")
            chosen = [t for t in chosen if t.id in wanted]
        if not chosen:
            raise ConfigurationError("The selection contains no tasks.")
        return tuple(sorted(chosen, key=lambda t: t.id))


def dataset_sha256(dataset_id: str, version: str, tasks: Iterable[Task]) -> str:
    document = {
        "id": dataset_id,
        "version": version,
        "tasks": [{"id": t.id, "sha256": t.sha256} for t in sorted(tasks, key=lambda t: t.id)],
    }
    return hashlib.sha256(canonical_json(document)).hexdigest()


def compile_flags(names: Iterable[str]) -> int:
    flags = 0
    for name in names:
        flags |= REGEX_FLAGS[name]
    return flags


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _problems(exc: ValidationError) -> str:
    # Locations and reasons only (never echo input values).
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}" for err in exc.errors()
    )


def parse_tasks(text: str, *, source: str = "<tasks>") -> tuple[Task, ...]:
    """Parse a JSON Lines task file. Every non-blank line must be one valid task."""
    tasks: list[Task] = []
    seen: dict[str, int] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        except ValueError as exc:
            raise ConfigurationError(f"{source}:{line_number}: invalid JSON ({exc})") from None
        try:
            # JSON-mode strict validation: no type coercion (e.g. "3" is not an integer).
            task = Task.model_validate_json(line)
        except ValidationError as exc:
            raise ConfigurationError(f"{source}:{line_number}: {_problems(exc)}") from None
        if task.id in seen:
            raise ConfigurationError(
                f"{source}:{line_number}: duplicate task id {task.id!r} "
                f"(first defined on line {seen[task.id]})"
            )
        seen[task.id] = line_number
        tasks.append(task)
    if not tasks:
        raise ConfigurationError(f"{source}: no tasks defined")
    return tuple(tasks)


def load_dataset(directory: str | Path) -> Dataset:
    root = Path(directory)
    meta_path = root / "dataset.json"
    try:
        meta_text = meta_path.read_text(encoding="utf-8")
        json.loads(meta_text, object_pairs_hook=_reject_duplicate_keys)
        meta = DatasetMeta.model_validate_json(meta_text)
    except FileNotFoundError:
        raise ConfigurationError(f"Dataset metadata not found: {meta_path}") from None
    except ValueError as exc:
        detail = _problems(exc) if isinstance(exc, ValidationError) else str(exc)
        raise ConfigurationError(f"Invalid dataset metadata {meta_path}: {detail}") from None
    tasks_path = root / meta.tasks_file
    try:
        text = tasks_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigurationError(f"Task file not found: {tasks_path}") from None
    tasks = parse_tasks(text, source=str(tasks_path))
    return Dataset(meta.id, meta.version, meta.description, tasks)
