"""L0 deterministic checks (evaluator ``forge.l0``, version ``1``).

Every rule works on ``text = output.strip()`` (leading/trailing whitespace removed):

    empty output      ``text == ""``. Then *every* check fails with detail ``empty_output``
                      (so e.g. a maximum-length check cannot pass on an empty answer).
    word_count        ``len(re.findall(r"\\S+", text))`` within [min, max]
    char_count        ``len(text)`` (Unicode code points) within [min, max]
    line_count        number of lines of ``text`` that contain a non-whitespace character
    list_items        lines matching a bullet ``^\\s*[-*•]\\s+\\S`` and/or a numbered item
                      ``^\\s*\\d+[.)]\\s+\\S`` (``style`` any | bullet | numbered)
    contains          ``needle in text`` (both case-folded unless ``case_sensitive``)
    not_contains      the negation of ``contains``
    regex             ``re.search(pattern, text, flags)`` finds a match
    json              ``json.loads(text)`` succeeds (NaN/Infinity rejected), the value is an
                      object/array as required, object has ``required_keys``, array length is
                      within [min_items, max_items]. With ``allow_fence`` only, one surrounding
                      Markdown code fence (```` ``` ```` or ```` ```json ````) is removed first.
    code_block        at least ``min_blocks`` fenced blocks (```` ``` ```` at line start, closed
                      by ```` ``` ````); with ``language``, the first word of the fence's info
                      string must equal it case-insensitively

Counts include text inside code blocks. The checks measure format, required-content and
length adherence only — not correctness, usefulness or overall quality.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from forge.benchmark.dataset import (
    CharCount,
    Check,
    CodeBlock,
    Contains,
    Json,
    LineCount,
    ListItems,
    NotContains,
    Regex,
    Task,
    WordCount,
    compile_flags,
)

EVALUATOR_NAME = "forge.l0"
EVALUATOR_VERSION = "1"

_BULLET = re.compile(r"^\s*[-*•]\s+\S")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+\S")
_FENCED_JSON = re.compile(r"\A```(?:json)?[ \t]*\n(.*)\n```\Z", re.DOTALL | re.IGNORECASE)
_CODE_BLOCK = re.compile(r"^```[ \t]*([^\n`]*)\n.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)


@dataclass(frozen=True)
class CheckResult:
    index: int
    type: str
    requirement: str
    passed: bool
    observed: Any
    detail: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "type": self.type,
            "requirement": self.requirement,
            "passed": self.passed,
            "observed": self.observed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class EvaluationResult:
    empty_output: bool
    checks: tuple[CheckResult, ...]

    @property
    def passed_all(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def passed_count(self) -> int:
        return sum(c.passed for c in self.checks)

    def to_json(self) -> dict[str, Any]:
        return {
            "evaluator": EVALUATOR_NAME,
            "evaluator_version": EVALUATOR_VERSION,
            "empty_output": self.empty_output,
            "checks": [c.to_json() for c in self.checks],
            "checks_passed": self.passed_count,
            "checks_total": len(self.checks),
            "passed_all": self.passed_all,
        }


def evaluate(task: Task, output: str) -> EvaluationResult:
    text = output.strip()
    if not text:
        return EvaluationResult(
            True,
            tuple(
                CheckResult(i, c.type, c.requirement, False, None, "empty_output")
                for i, c in enumerate(task.checks)
            ),
        )
    results = []
    for index, check in enumerate(task.checks):
        passed, observed, detail = _run(check, text)
        results.append(CheckResult(index, check.type, check.requirement, passed, observed, detail))
    return EvaluationResult(False, tuple(results))


def _within(value: int, low: int | None, high: int | None) -> bool:
    return (low is None or value >= low) and (high is None or value <= high)


def _run(check: Check, text: str) -> tuple[bool, Any, str | None]:
    if isinstance(check, WordCount):
        count = len(re.findall(r"\S+", text))
        return _within(count, check.min, check.max), count, None
    if isinstance(check, CharCount):
        return _within(len(text), check.min, check.max), len(text), None
    if isinstance(check, LineCount):
        count = sum(1 for line in text.splitlines() if line.strip())
        return _within(count, check.min, check.max), count, None
    if isinstance(check, ListItems):
        count = sum(1 for line in text.splitlines() if _is_item(line, check.style))
        return _within(count, check.min, check.max), count, None
    if isinstance(check, Contains | NotContains):
        found = _contains(text, check.text, check.case_sensitive)
        return (found if isinstance(check, Contains) else not found), found, None
    if isinstance(check, Regex):
        match = re.search(check.pattern, text, compile_flags(check.flags))
        return match is not None, match is not None, None
    if isinstance(check, Json):
        return _json(check, text)
    if isinstance(check, CodeBlock):
        count = sum(
            1
            for match in _CODE_BLOCK.finditer(text)
            if check.language is None
            or (match.group(1).split() or [""])[0].casefold() == check.language.casefold()
        )
        return count >= check.min_blocks, count, None
    raise TypeError(f"unknown check type {type(check).__name__}")  # pragma: no cover


def _is_item(line: str, style: str) -> bool:
    bullet = _BULLET.match(line) is not None
    numbered = _NUMBERED.match(line) is not None
    if style == "bullet":
        return bullet
    if style == "numbered":
        return numbered
    return bullet or numbered


def _contains(text: str, needle: str, case_sensitive: bool) -> bool:
    if case_sensitive:
        return needle in text
    return needle.casefold() in text.casefold()


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant {name}")


def _json(check: Json, text: str) -> tuple[bool, Any, str | None]:
    candidate = text
    if check.allow_fence:
        fenced = _FENCED_JSON.match(text)
        if fenced:
            candidate = fenced.group(1)
    try:
        value = json.loads(candidate, parse_constant=_reject_constant)
    except ValueError:
        return False, "invalid_json", "output is not valid JSON"
    if check.kind == "object":
        if not isinstance(value, dict):
            return False, type(value).__name__, "expected a JSON object"
        missing = [k for k in check.required_keys if k not in value]
        if missing:
            return False, "object", f"missing keys: {', '.join(missing)}"
        return True, "object", None
    if not isinstance(value, list):
        return False, type(value).__name__, "expected a JSON array"
    if not _within(len(value), check.min_items, check.max_items):
        return False, len(value), "array length out of range"
    return True, len(value), None
