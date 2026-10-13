"""verify_run across record formats, and the v2 accounting and status checks."""

import hashlib
import json

from forge.benchmark.legacy_formats import aggregate_v1
from forge.benchmark.records import ResultRecord
from forge.benchmark.verify import verify_run
from forge.infrastructure.cache import MemoryCacheStore, canonical_json
from tests.benchmark.helpers import make_dataset, read_records, read_run, run


def write_results(directory, records):
    raw = b"".join(canonical_json(r) + b"\n" for r in records)
    (directory / "results.jsonl").write_bytes(raw)
    run_doc = read_run(directory)
    run_doc["results_sha256"] = hashlib.sha256(raw).hexdigest()
    (directory / "run.json").write_bytes(canonical_json(run_doc))


def set_run(directory, **changes):
    run_doc = read_run(directory)
    run_doc.update(changes)
    (directory / "run.json").write_bytes(canonical_json(run_doc))


def to_format_v1(directory, dataset):
    """Rewrite a run directory exactly as the format-v1 runner wrote it."""
    records = read_records(directory)
    for record in records:
        record["record_version"] = 1
        for execution in record["executions"]:
            for key in ("attempts", "replayed_usage", "budget_tokens"):
                execution.pop(key)
    write_results(directory, records)
    set_run(directory, run_record_version=1)
    run_doc = read_run(directory)
    parsed = [ResultRecord.model_validate(r) for r in records]
    summary = aggregate_v1(parsed, dataset.tasks, run_doc["conditions"])
    (directory / "summary.json").write_bytes(canonical_json(summary))


def test_format_v1_runs_still_verify_with_the_frozen_aggregator(tmp_path):
    dataset = make_dataset()
    outcome = run(tmp_path, dataset=dataset)
    to_format_v1(outcome.directory, dataset)
    report = verify_run(outcome.directory, dataset)
    assert report.valid and report.complete and report.evaluations_recomputed
    # ...and the frozen v1 aggregate still rejects a tampered v1 summary.
    summary = json.loads((outcome.directory / "summary.json").read_bytes())
    summary["conditions"]["B0"]["tasks_all_checks_passed"]["count"] = 0
    (outcome.directory / "summary.json").write_bytes(canonical_json(summary))
    assert (
        "summary.json does not match the recorded results"
        in verify_run(outcome.directory, dataset).problems
    )


def test_v2_run_with_v1_records_is_rejected(tmp_path):
    outcome = run(tmp_path)
    records = read_records(outcome.directory)
    records[0]["record_version"] = 1
    write_results(outcome.directory, records)
    assert any("record format" in p for p in verify_run(outcome.directory).problems)


def test_cache_hit_claiming_attempts_or_usage_is_rejected(tmp_path):
    store = MemoryCacheStore()
    run(tmp_path / "a", cache_store=store, cache=True, cache_scope="s", conditions=("B0",))
    replay = run(tmp_path / "b", cache_store=store, cache=True, cache_scope="s", conditions=("B0",))
    records = read_records(replay.directory)
    records[0]["executions"][0]["attempts"] = 1
    write_results(replay.directory, records)
    assert any("cache hit with attempts" in p for p in verify_run(replay.directory).problems)


def test_attempt_totals_must_match_the_budget(tmp_path):
    outcome = run(tmp_path)
    usage = read_run(outcome.directory)["budget_usage"]
    set_run(outcome.directory, budget_usage={**usage, "model_calls_used": 4})
    assert (
        "more provider attempts recorded than the budget counted"
        in verify_run(outcome.directory).problems
    )
    set_run(outcome.directory, budget_usage={**usage, "model_calls_used": 6})
    assert (
        "completed run with unrecorded provider attempts" in verify_run(outcome.directory).problems
    )


def test_summary_markdown_status_must_match_run_json(tmp_path):
    outcome = run(tmp_path)
    path = outcome.directory / "summary.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("`completed`", "`failed`"), encoding="utf-8"
    )
    assert "summary.md status differs from run.json" in verify_run(outcome.directory).problems


def test_summary_json_status_must_match_run_json(tmp_path):
    outcome = run(tmp_path)
    summary = json.loads((outcome.directory / "summary.json").read_bytes())
    summary["status"] = "failed"
    (outcome.directory / "summary.json").write_bytes(canonical_json(summary))
    problems = verify_run(outcome.directory, make_dataset()).problems
    assert "summary.json status differs from run.json" in problems
