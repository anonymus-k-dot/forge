"""Dataset pilot-v1 (forge-pilot 1.0.0): trivial answers cannot pass, pilot-v0 is preserved,
and limited tasks are excluded from "all checks passed" metrics."""

import json

import pytest

from forge.benchmark.checks import evaluate
from forge.benchmark.dataset import load_dataset
from forge.benchmark.records import aggregate
from forge.benchmark.runner import BenchmarkRunner
from forge.benchmark.verify import verify_run
from forge.providers.config import load_providers_config
from forge.providers.router import ProviderRouter
from tests.benchmark.helpers import (
    GOOD_ANSWER,
    REPO_ROOT,
    make_dataset,
    make_task,
    options,
    read_records,
    run,
)
from tests.providers.helpers import RecordingSleep

V0_DIR = REPO_ROOT / "benchmarks" / "pilot-v0"
V1_DIR = REPO_ROOT / "benchmarks" / "pilot-v1"
V0_SHA256 = "7f6d2ffab6cf1abce2a92109843326db57c687bc2f9995c2c39c8d14b40a2618"
V1_SHA256 = "843226339e0d27417822e5ac0bf0b87ab8e54805165f98282af5d252baa578a2"
UPPER_BOUND_ONLY_IN_V0 = (
    "pilot-003",
    "pilot-011",
    "pilot-013",
    "pilot-015",
    "pilot-019",
    "pilot-029",
)
REVISED = (
    "pilot-003", "pilot-004", "pilot-007", "pilot-008", "pilot-010", "pilot-011", "pilot-012",
    "pilot-013", "pilot-015", "pilot-016", "pilot-017", "pilot-019", "pilot-026", "pilot-027",
    "pilot-029", "pilot-030",
)  # fmt: skip
TRIVIAL_ANSWERS = (
    "",
    "ok",
    "OK.",
    "x",
    "- ok",
    "1. ok",
    "ok\nok\nok",
    "- ok\n- ok\n- ok",
    "1. ok\n2. ok\n3. ok",
    "Answer: ok",
)
# Plausible answers: each revised task's checks must be satisfiable.
GOOD = {
    "pilot-003": "- The config path may be relative to the working directory.\n- Another process "
    "may be writing the config file.\n- The file may contain invalid syntax.",
    "pilot-007": "Grey autumn rain falls\nleaves drift down the quiet street\npuddles hold the sky",
    "pilot-011": "Plants, algae and some bacteria use chlorophyll to capture light, turning carbon "
    "dioxide and water into glucose and releasing oxygen, sustaining food chains.",
    "pilot-013": "Among 1,200 employees, remote staff were happier but collaborated less than "
    "office staff.\nHybrid teams fell in between; results may not generalise.",
    "pilot-015": "The value fell from 4.1 in 2019 to 3.2 in 2020, then rose steadily to 5.6 by "
    "2022, ending above its starting level.",
    "pilot-017": "1. 14:10 to 16:10 is 2 hours.\n2. 16:10 to 16:45 is 35 minutes.\nAnswer: 2 h 35 min",
    "pilot-019": "Recommendation: Rust. If you want deep control over memory and performance and "
    "enjoy a strong type system, Rust rewards the effort. Go is simpler and great for services, "
    "but Rust broadens your skills more.",
    "pilot-026": "1. Check rooms free on Friday afternoon.\n2. Pick one that fits everyone.\n"
    "3. Book it and send the invitation.",
    "pilot-027": "- Google Sheets: collects the numbers\n- Zapier: triggers the report weekly",
    "pilot-029": 'Unused items can be returned within 30 days: "Customers may return unused items '
    'within 30 days of delivery for a full refund."',
    "pilot-030": "- Starter: $9 per month\n- Team: $29 per seat per month\n- Annual: two months free",
}


@pytest.fixture(scope="module")
def v0():
    return load_dataset(V0_DIR)


@pytest.fixture(scope="module")
def v1():
    return load_dataset(V1_DIR)


def test_versions_and_hashes(v0, v1):
    assert (v0.version, v0.sha256) == ("0.1.0", V0_SHA256)  # pilot-v0 unchanged
    assert (v1.id, v1.version, v1.sha256) == ("forge-pilot", "1.0.0", V1_SHA256)
    assert len(v1.tasks) == 30 and sum(len(t.checks) for t in v1.tasks) == 67


def test_v1_keeps_ids_and_stratification_and_versions_every_change(v0, v1):
    shape = [(t.id, t.category, t.spec_level, t.split) for t in v0.tasks]
    assert shape == [(t.id, t.category, t.spec_level, t.split) for t in v1.tasks]
    changed = tuple(new.id for old, new in zip(v0.tasks, v1.tasks) if old.sha256 != new.sha256)
    assert changed == REVISED
    for old, new in zip(v0.tasks, v1.tasks):
        assert new.version == (2 if new.id in REVISED else old.version)


@pytest.mark.parametrize("task_id", UPPER_BOUND_ONLY_IN_V0)
def test_ok_fully_passed_these_tasks_in_v0_but_not_in_v1(v0, v1, task_id):
    by_id_v0 = {t.id: t for t in v0.tasks}
    by_id_v1 = {t.id: t for t in v1.tasks}
    assert evaluate(by_id_v0[task_id], "ok").passed_all  # the defect, preserved in v0
    assert not evaluate(by_id_v1[task_id], "ok").passed_all


def test_no_unlimited_v1_task_is_fully_passed_by_a_trivial_answer(v1):
    loopholes = {
        task.id: answer
        for task in v1.tasks
        if not task.limited_reason
        for answer in TRIVIAL_ANSWERS
        if evaluate(task, answer).passed_all
    }
    assert loopholes == {}


@pytest.mark.parametrize("task_id", sorted(GOOD))
def test_revised_checks_are_satisfiable(v1, task_id):
    task = {t.id: t for t in v1.tasks}[task_id]
    result = evaluate(task, GOOD[task_id])
    assert result.passed_all, [(c.type, c.observed) for c in result.checks if not c.passed]


def test_offline_v1_pilot_runs_and_verifies(tmp_path, v1):
    router = ProviderRouter(
        load_providers_config(V1_DIR / "offline-providers.json"), sleep=RecordingSleep()
    )
    outcome = BenchmarkRunner(router).run(
        options(
            tmp_path,
            dataset=v1,
            target_profile="offline-target",
            rewriter_profile="offline-rewriter",
            budget_limits={"max_model_calls": 150},
        )
    )
    assert outcome.status == "completed"
    assert outcome.summary["conditions"]["B0"]["checks"]["defined"] == 67  # v1 checks
    manifest = json.loads((outcome.directory / "manifest.json").read_bytes())
    assert (manifest["dataset"]["version"], manifest["dataset"]["sha256"]) == ("1.0.0", V1_SHA256)
    assert len(read_records(outcome.directory)) == 90
    assert verify_run(outcome.directory, v1).complete
    # A run is bound to its dataset version: verifying against v0 is rejected.
    assert not verify_run(outcome.directory, load_dataset(V0_DIR)).valid


class TestLimitedTasks:
    def limited_task(self):
        return make_task(
            "task-002",
            limited_reason="format-only: any three bullets pass",
        )

    def test_definition_omits_unset_reason_and_hashes_a_set_one(self):
        assert "limited_reason" not in make_task().definition()
        assert self.limited_task().definition()["limited_reason"].startswith("format-only")
        assert self.limited_task().sha256 != make_task("task-002").sha256

    def test_limited_tasks_are_excluded_and_reported(self, tmp_path):
        dataset = make_dataset(make_task("task-001"), self.limited_task())
        outcome = run(tmp_path, dataset=dataset, conditions=("B0",))
        b0 = outcome.summary["conditions"]["B0"]
        assert b0["tasks"] == 2
        assert b0["tasks_all_checks_passed"] == {"count": 1, "of": 1}
        assert b0["tasks_all_checks_passed_limited_tasks"] == {"count": 1, "of": 1}
        assert outcome.summary["limited_tasks"] == {
            "task-002": "format-only: any three bullets pass"
        }
        assert b0["checks"]["defined"] == 4  # check diagnostics still cover every task
        summary_md = (outcome.directory / "summary.md").read_text(encoding="utf-8")
        assert "Limited tasks" in summary_md and "task-002" in summary_md
        assert verify_run(outcome.directory, dataset).complete

    def test_paired_counts_exclude_limited_tasks(self):
        dataset = make_dataset(make_task("task-001"), self.limited_task())
        (pair,) = aggregate([], dataset.tasks, ["B0", "B1"])["paired_check_counts"]
        assert (pair["excluded_limited_tasks"], pair["compared"]) == (1, 0)

    def test_good_answer_constant_still_passes(self):
        assert evaluate(make_task(), GOOD_ANSWER).passed_all
