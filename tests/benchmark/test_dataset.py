"""Task dataset schema, validation and hashing (including the shipped pilot-v0)."""

import json
from collections import Counter

import pytest

from forge.benchmark.dataset import (
    CATEGORIES,
    SPEC_LEVELS,
    Dataset,
    dataset_sha256,
    load_dataset,
    parse_tasks,
)
from forge.errors import ConfigurationError
from tests.benchmark.helpers import PILOT_DIR, make_task


def line(**overrides):
    data = {
        "id": "t-001",
        "version": 1,
        "category": "coding",
        "spec_level": "well",
        "split": "dev",
        "prompt": "Answer in under 10 words.",
        "checks": [{"type": "word_count", "max": 10, "requirement": "under 10 words"}],
    }
    data.update(overrides)
    return json.dumps(data)


class TestPilotDataset:
    def test_pilot_v0_is_valid_versioned_and_balanced(self):
        dataset = load_dataset(PILOT_DIR)
        assert (dataset.id, dataset.version) == ("forge-pilot", "0.1.0")
        assert len(dataset.tasks) == 30
        assert len({t.id for t in dataset.tasks}) == 30
        assert set(Counter(t.category for t in dataset.tasks)) == set(CATEGORIES)
        assert set(Counter(t.spec_level for t in dataset.tasks)) == set(SPEC_LEVELS)
        assert Counter(t.split for t in dataset.tasks) == {"dev": 20, "heldout": 10}
        assert all(t.checks for t in dataset.tasks)

    def test_every_check_quotes_its_own_prompt(self):
        # Fairness: each requirement is visible to every condition through the prompt.
        for task in load_dataset(PILOT_DIR).tasks:
            for check in task.checks:
                assert check.requirement.casefold() in task.prompt.casefold(), task.id

    def test_pilot_hash_is_stable_across_loads(self):
        assert load_dataset(PILOT_DIR).sha256 == load_dataset(PILOT_DIR).sha256


class TestValidation:
    def test_valid_line_parses(self):
        (task,) = parse_tasks(line())
        assert task.id == "t-001"

    def test_duplicate_ids_are_rejected_with_line_numbers(self):
        with pytest.raises(ConfigurationError, match=r":3: duplicate task id 't-001' .*line 1"):
            parse_tasks(line() + "\n" + line(id="t-002") + "\n" + line())

    @pytest.mark.parametrize(
        "overrides, message",
        [
            ({"unknown": 1}, "Extra inputs"),
            ({"version": "1"}, "version"),
            ({"version": 1.0}, "version"),
            ({"id": "Bad ID"}, "id"),
            ({"category": "poetry"}, "category"),
            ({"split": "test"}, "split"),
            ({"checks": []}, "checks"),
            ({"prompt": ""}, "prompt"),
            (
                {"checks": [{"type": "word_count", "max": 5, "requirement": "not in prompt"}]},
                "not a verbatim phrase",
            ),
            (
                {"checks": [{"type": "word_count", "requirement": "under 10 words"}]},
                "set min, max",
            ),
            (
                {"checks": [{"type": "word_count", "min": 9, "max": 3, "requirement": "Answer"}]},
                "min must not exceed max",
            ),
            (
                {"checks": [{"type": "regex", "pattern": "(", "requirement": "Answer"}]},
                "does not compile",
            ),
            (
                {
                    "checks": [
                        {
                            "type": "json",
                            "kind": "array",
                            "required_keys": ["a"],
                            "requirement": "Answer",
                        }
                    ]
                },
                "objects only",
            ),
            (
                {
                    "checks": [
                        {
                            "type": "contains",
                            "text": "x",
                            "requirement": "Answer",
                            "case_sensitive": "yes",
                        }
                    ]
                },
                "case_sensitive",
            ),
            ({"checks": [{"type": "sentiment", "requirement": "Answer"}]}, "checks"),
        ],
    )
    def test_invalid_tasks_are_rejected(self, overrides, message):
        with pytest.raises(ConfigurationError, match=message):
            parse_tasks(line(**overrides))

    def test_duplicate_json_keys_and_bad_json_are_rejected(self):
        with pytest.raises(ConfigurationError, match="duplicate key"):
            parse_tasks('{"id": "t-001", "id": "t-002"}')
        with pytest.raises(ConfigurationError, match=":1: invalid JSON"):
            parse_tasks("{not json")

    def test_empty_file_is_rejected(self):
        with pytest.raises(ConfigurationError, match="no tasks"):
            parse_tasks("\n\n")

    def test_validation_errors_do_not_echo_values(self):
        with pytest.raises(ConfigurationError) as info:
            parse_tasks(line(category="SECRET-VALUE-123"))
        assert "SECRET-VALUE-123" not in str(info.value)

    def test_missing_dataset_files(self, tmp_path):
        with pytest.raises(ConfigurationError, match="metadata not found"):
            load_dataset(tmp_path)
        (tmp_path / "dataset.json").write_text(
            json.dumps(
                {"id": "x1", "version": "1.0.0", "description": "d", "tasks_file": "t.jsonl"}
            )
        )
        with pytest.raises(ConfigurationError, match="Task file not found"):
            load_dataset(tmp_path)


class TestHashing:
    def test_task_hash_is_stable_and_sensitive_to_every_field(self):
        base = make_task()
        assert base.sha256 == make_task().sha256
        changed = [
            make_task(prompt="List three fruits as bullet points, under 20 words!"),
            make_task(task_id="task-002"),
            make_task(version=2),
            make_task(split="heldout"),
            make_task(notes="note"),
            make_task(checks=[{"type": "word_count", "max": 21, "requirement": "under 20 words"}]),
        ]
        assert len({base.sha256, *(t.sha256 for t in changed)}) == len(changed) + 1

    def test_dataset_hash_ignores_file_order_but_not_content_or_version(self):
        a, b = make_task("task-001"), make_task("task-002")
        assert dataset_sha256("d", "1.0.0", [a, b]) == dataset_sha256("d", "1.0.0", [b, a])
        assert dataset_sha256("d", "1.0.0", [a, b]) != dataset_sha256("d", "1.0.1", [a, b])
        assert dataset_sha256("d", "1.0.0", [a, b]) != dataset_sha256("d", "1.0.0", [a])


class TestSelection:
    def test_select_orders_by_id_and_filters(self):
        tasks = (make_task("task-002"), make_task("task-001", split="heldout"))
        dataset = Dataset("d", "1.0.0", "d", tasks)
        assert [t.id for t in dataset.select()] == ["task-001", "task-002"]
        assert [t.id for t in dataset.select(splits=("dev",))] == ["task-002"]
        assert [t.id for t in dataset.select(task_ids=("task-001",))] == ["task-001"]

    def test_invalid_selections(self):
        dataset = Dataset("d", "1.0.0", "d", (make_task(),))
        with pytest.raises(ConfigurationError, match="Unknown task"):
            dataset.select(task_ids=("nope",))
        with pytest.raises(ConfigurationError, match="Unknown split"):
            dataset.select(splits=("test",))
        with pytest.raises(ConfigurationError, match="no tasks"):
            dataset.select(splits=("heldout",))
