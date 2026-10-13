"""verify_run must reject tampered, fabricated or falsely-complete runs."""

import hashlib
import json

import pytest

from forge.benchmark.verify import verify_run
from forge.infrastructure.cache import canonical_json
from tests.benchmark.helpers import (
    GOOD_ANSWER,
    Responder,
    make_dataset,
    make_router,
    make_task,
    read_records,
    read_run,
    run,
    text_reply,
)


def rewrite_results(directory, records, *, fix_hash=True):
    raw = b"".join(canonical_json(r) + b"\n" for r in records)
    (directory / "results.jsonl").write_bytes(raw)
    if fix_hash:  # a careful forger also updates the recorded hash
        run_doc = read_run(directory)
        run_doc["results_sha256"] = hashlib.sha256(raw).hexdigest()
        run_doc["records_written"] = len(records)
        (directory / "run.json").write_bytes(canonical_json(run_doc))


def set_run(directory, **changes):
    run_doc = read_run(directory)
    run_doc.update(changes)
    (directory / "run.json").write_bytes(canonical_json(run_doc))


@pytest.fixture
def completed(tmp_path):
    return run(tmp_path).directory


@pytest.fixture
def failing_target_run(tmp_path):
    target = Responder("tg", text_reply("no list here"))
    return run(tmp_path, make_router(target=target)).directory


def problems(directory, dataset=None):
    return " | ".join(verify_run(directory, dataset or make_dataset()).problems)


def test_untouched_run_is_valid_and_complete(completed):
    report = verify_run(completed, make_dataset())
    assert report.valid and report.complete and report.evaluations_recomputed


def test_fabricated_passing_evaluation_is_detected(failing_target_run):
    records = read_records(failing_target_run)
    for record in records:  # claim every check passed although the output fails them
        record["evaluation"]["passed_all"] = True
        record["evaluation"]["checks_passed"] = record["evaluation"]["checks_total"]
        for check in record["evaluation"]["checks"]:
            check["passed"] = True
    rewrite_results(failing_target_run, records)
    assert "differs from a recomputation" in problems(failing_target_run)
    assert not verify_run(failing_target_run, make_dataset()).complete


def test_edited_output_breaks_its_hash(completed):
    records = read_records(completed)
    records[0]["executions"][-1]["output_text"] = "- edited\n- list\n- here"
    rewrite_results(completed, records)
    assert "output hash mismatch" in problems(completed)


def test_unrecorded_edit_breaks_the_results_hash(completed):
    records = read_records(completed)
    records[0]["status"] = "failed"
    rewrite_results(completed, records, fix_hash=False)
    assert "does not match results_sha256" in problems(completed)


def test_incomplete_run_marked_completed_is_detected(tmp_path):
    outcome = run(tmp_path, should_stop=iter([False, True, True, True]).__next__)
    assert outcome.status == "cancelled"
    set_run(outcome.directory, status="completed")
    text = problems(outcome.directory)
    assert "marked completed but has not_run records" in text
    assert not verify_run(outcome.directory, make_dataset()).complete


def test_missing_record_in_completed_run_is_detected(completed):
    rewrite_results(completed, read_records(completed)[:-1])
    assert "marked completed but 1 record(s) are missing" in problems(completed)


def test_evaluated_record_without_target_execution_is_rejected(completed):
    records = read_records(completed)
    records[0]["executions"] = []
    rewrite_results(completed, records)
    assert "evaluated without a target execution" in problems(completed)


def test_not_run_record_cannot_carry_an_evaluation(tmp_path):
    outcome = run(tmp_path, should_stop=iter([False, True, True]).__next__)
    records = read_records(outcome.directory)
    records[1]["evaluation"] = records[0]["evaluation"]
    rewrite_results(outcome.directory, records)
    assert "not_run record carries an evaluation" in problems(outcome.directory)


def test_fixture_run_relabelled_as_measurement_is_detected(completed):
    set_run(completed, measurement="model_outputs")
    assert "measurement is 'model_outputs'" in problems(completed)


def test_interpretation_cannot_be_changed(completed):
    set_run(completed, interpretation="FORGE_IS_BETTER")
    assert "not INCONCLUSIVE" in problems(completed)


def test_manifest_and_summary_tampering(completed):
    manifest = json.loads((completed / "manifest.json").read_bytes())
    manifest["samples_per_case"] = 3
    (completed / "manifest.json").write_bytes(canonical_json(manifest))
    assert "does not match manifest_sha256" in problems(completed)


def test_summary_must_match_the_records(completed):
    summary = json.loads((completed / "summary.json").read_bytes())
    summary["conditions"]["B0"]["tasks_all_checks_passed"]["count"] = 0
    (completed / "summary.json").write_bytes(canonical_json(summary))
    assert "summary.json does not match" in problems(completed)


def test_changed_dataset_is_detected(completed):
    changed = make_dataset(make_task(prompt="List three fruits as bullet points, under 20 words!"))
    assert "differs from the manifest" in problems(completed, changed)


def test_unfinished_run_is_reported_incomplete(completed):
    set_run(completed, status="running")
    report = verify_run(completed, make_dataset())
    assert not report.complete and "incomplete" in " ".join(report.problems)


def test_missing_files(tmp_path):
    assert verify_run(tmp_path).problems == ["run.json is missing"]


def test_recomputation_needs_the_dataset(completed):
    report = verify_run(completed)
    assert report.valid and not report.evaluations_recomputed


def test_good_answer_constant_passes_default_task():
    # Guard for the fixtures above: the default task's checks pass on GOOD_ANSWER.
    from forge.benchmark.checks import evaluate

    assert evaluate(make_task(), GOOD_ANSWER).passed_all
