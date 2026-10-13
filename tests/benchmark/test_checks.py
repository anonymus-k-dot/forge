"""Each L0 rule exactly as documented in forge.benchmark.checks."""

import pytest

from forge.benchmark.checks import EVALUATOR_NAME, EVALUATOR_VERSION, evaluate
from tests.benchmark.helpers import make_task

PROMPT = "Answer here."


def outcome(check: dict, output: str):
    task = make_task(prompt=PROMPT, checks=[{**check, "requirement": "Answer"}])
    (result,) = evaluate(task, output).checks
    return result.passed, result.observed


@pytest.mark.parametrize(
    "check, output, expected",
    [
        ({"type": "word_count", "min": 2, "max": 3}, "one two", (True, 2)),
        ({"type": "word_count", "min": 2, "max": 3}, "one two three", (True, 3)),
        ({"type": "word_count", "min": 2, "max": 3}, "one", (False, 1)),
        ({"type": "word_count", "max": 3}, "a b c d", (False, 4)),
        ({"type": "word_count", "max": 3}, "  a\n\tb  ", (True, 2)),
        ({"type": "char_count", "max": 5}, "  héllo  ", (True, 5)),
        ({"type": "char_count", "min": 6}, "hello", (False, 5)),
        ({"type": "line_count", "min": 3, "max": 3}, "a\n\n b\n   \nc", (True, 3)),
        ({"type": "line_count", "max": 1}, "a\nb", (False, 2)),
        ({"type": "list_items", "min": 2}, "- a\n* b\n• c\n1. d\n2) e\n-x", (True, 5)),
        ({"type": "list_items", "style": "bullet", "min": 1}, "1. a\n2. b", (False, 0)),
        ({"type": "list_items", "style": "numbered", "max": 2}, "1. a\n2. b\n- c", (True, 2)),
        ({"type": "list_items", "style": "bullet", "min": 1}, "-   \n- ok", (True, 1)),
        ({"type": "contains", "text": "Paris"}, "we went to PARIS", (True, True)),
        ({"type": "contains", "text": "Paris", "case_sensitive": True}, "PARIS", (False, False)),
        ({"type": "not_contains", "text": "```"}, "plain text", (True, False)),
        ({"type": "not_contains", "text": "```"}, "```py\nx\n```", (False, True)),
        ({"type": "regex", "pattern": "^Answer:"}, "steps\nAnswer: 2", (False, False)),
        (
            {"type": "regex", "pattern": "^Answer:", "flags": ["MULTILINE"]},
            "x\nAnswer: 2",
            (True, True),
        ),
        ({"type": "regex", "pattern": "answer", "flags": ["IGNORECASE"]}, "ANSWER", (True, True)),
        ({"type": "json", "kind": "object", "required_keys": ["a"]}, '{"a": 1}', (True, "object")),
        (
            {"type": "json", "kind": "object", "required_keys": ["a", "b"]},
            '{"a": 1}',
            (False, "object"),
        ),
        ({"type": "json", "kind": "object"}, "[1]", (False, "list")),
        ({"type": "json", "kind": "array", "min_items": 2, "max_items": 2}, "[1, 2]", (True, 2)),
        ({"type": "json", "kind": "array", "max_items": 1}, "[1, 2]", (False, 2)),
        ({"type": "json", "kind": "array"}, "[NaN]", (False, "invalid_json")),
        ({"type": "json", "kind": "object"}, 'Here: {"a": 1}', (False, "invalid_json")),
        ({"type": "json", "kind": "object"}, '```json\n{"a": 1}\n```', (False, "invalid_json")),
        (
            {"type": "json", "kind": "object", "allow_fence": True},
            '```json\n{"a": 1}\n```',
            (True, "object"),
        ),
        ({"type": "code_block"}, "text\n```\ncode\n```\nmore", (True, 1)),
        ({"type": "code_block", "language": "python"}, "```Python main\nx\n```", (True, 1)),
        ({"type": "code_block", "language": "python"}, "```bash\nls\n```", (False, 0)),
        ({"type": "code_block"}, "```\nunclosed", (False, 0)),
        ({"type": "code_block", "min_blocks": 2}, "```\na\n```\n```\nb\n```", (True, 2)),
    ],
)
def test_rules(check, output, expected):
    assert outcome(check, output) == expected


@pytest.mark.parametrize("output", ["", "   \n\t  "])
def test_empty_output_fails_every_check_including_upper_bounds(output):
    task = make_task(
        prompt="Answer in under 10 words without code.",
        checks=[
            {"type": "word_count", "max": 10, "requirement": "under 10 words"},
            {"type": "not_contains", "text": "```", "requirement": "without code"},
        ],
    )
    result = evaluate(task, output)
    assert result.empty_output is True and result.passed_all is False
    assert [(c.passed, c.detail) for c in result.checks] == [(False, "empty_output")] * 2


def test_evaluation_document_and_determinism():
    task = make_task()
    first, second = evaluate(task, "- a\n- b\n- c"), evaluate(task, "- a\n- b\n- c")
    assert first == second
    document = first.to_json()
    assert (document["evaluator"], document["evaluator_version"]) == (
        EVALUATOR_NAME,
        EVALUATOR_VERSION,
    )
    assert (document["checks_passed"], document["checks_total"], document["passed_all"]) == (
        2,
        2,
        True,
    )


def test_longer_or_more_structured_output_is_not_rewarded_by_itself():
    # Upper bounds and exact counts penalise padding; nothing scores length positively.
    task = make_task()
    padded = "- a\n- b\n- c\n- d extra detail\n## Heading\nmore words " * 3
    assert evaluate(task, padded).passed_count < evaluate(task, "- a\n- b\n- c").passed_count
