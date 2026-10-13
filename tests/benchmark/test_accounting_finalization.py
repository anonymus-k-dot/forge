"""Provider-attempt and token accounting, cache-hit usage, and finalization semantics."""

import json

import pytest

from forge.benchmark.runner import RunFiles
from forge.benchmark.verify import verify_run
from forge.infrastructure.cache import MemoryCacheStore
from forge.providers import errors
from forge.providers.base import Capabilities, Usage
from forge.providers.fake import FakeResponse
from tests.benchmark.helpers import (
    GOOD_ANSWER,
    Responder,
    make_dataset,
    make_router,
    read_records,
    read_run,
    run,
)


def with_usage(_model, _request):
    return FakeResponse((GOOD_ANSWER,), usage=Usage(7, 5))


class TestAccounting:
    def test_retries_are_provider_attempts_of_one_execution(self, tmp_path):
        attempts = {"n": 0}

        def flaky_once(_model, _request):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return errors.UpstreamServerError("503")
            return FakeResponse((GOOD_ANSWER,))

        outcome = run(tmp_path, make_router(target=Responder("tg", flaky_once)), conditions=("B0",))
        (record,) = read_records(outcome.directory)
        assert record["executions"][0]["attempts"] == 2
        accounting = outcome.summary["conditions"]["B0"]["accounting"]
        assert (accounting["executions"], accounting["provider_attempts"]) == (1, 2)
        totals = outcome.summary["run_accounting"]
        assert (
            totals["provider_attempts_recorded"],
            totals["provider_attempts_budget"],
            totals["provider_attempts_unrecorded"],
        ) == (2, 2, 0)

    def test_refusal_before_dispatch_is_not_an_attempt(self, tmp_path):
        # F-legacy needs a system instruction; this rewriter provider does not support one,
        # so the router refuses before reserving budget or calling the adapter.
        rewriter = Responder("rw", lambda _m, _r: FakeResponse(("unused",)))
        rewriter.capabilities = Capabilities(
            streaming=True, system_instruction=False, seed=True, usage_reporting=True
        )
        router = make_router(rewriter)
        outcome = run(tmp_path, router, conditions=("F-legacy",))
        (record,) = read_records(outcome.directory)
        assert record["status"] == "failed"
        (execution,) = record["executions"]
        assert (execution["error_category"], execution["attempts"]) == (
            "unsupported_capability",
            0,
        )
        accounting = outcome.summary["conditions"]["F-legacy"]["accounting"]
        assert accounting["provider_attempts"] == 0
        assert accounting["executions_refused_before_dispatch"] == 1
        assert router.adapter("rw").calls == []
        assert outcome.summary["run_accounting"]["provider_attempts_budget"] == 0

    def test_token_bases_are_kept_apart(self, tmp_path):
        outcome = run(
            tmp_path, make_router(target=Responder("tg", with_usage)), conditions=("B0", "B1")
        )
        b0, b1 = (outcome.summary["conditions"][c]["tokens"] for c in ("B0", "B1"))
        assert (b0["provider_reported_input"], b0["provider_reported_output"]) == (7, 5)
        assert (b0["budget_charged_provider_reported"], b0["budget_charged_estimated"]) == (12, 0)
        # B1's rewrite reports no usage: it is charged the estimate and counted as such.
        assert b1["fresh_executions_without_provider_usage"] == 1
        assert b1["budget_charged_estimated"] > 0
        assert b1["budget_charged_provider_reported"] == 12

    def test_interrupted_call_attempt_is_visible_as_unrecorded(self, tmp_path):
        def interrupt(_m, _r):
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            run(tmp_path, make_router(target=Responder("tg", interrupt)), conditions=("B0",))
        (directory,) = (tmp_path / "runs").iterdir()
        totals = json.loads((directory / "summary.json").read_bytes())["run_accounting"]
        assert (
            totals["provider_attempts_recorded"],
            totals["provider_attempts_budget"],
            totals["provider_attempts_unrecorded"],
        ) == (0, 1, 1)
        report = verify_run(directory, make_dataset())
        assert report.valid and not report.complete  # allowed for a cancelled run

    def test_cache_hits_carry_replayed_usage_separately(self, tmp_path):
        store = MemoryCacheStore()

        def scoped_run(path):
            return run(
                path,
                make_router(target=Responder("tg", with_usage)),
                cache_store=store,
                cache=True,
                cache_scope="s",
                conditions=("B0",),
            )

        scoped_run(tmp_path / "a")
        replay = scoped_run(tmp_path / "b")
        (execution,) = read_records(replay.directory)[0]["executions"]
        assert execution["cache_hit"] is True and execution["attempts"] == 0
        assert execution["usage"] == {
            "input_tokens": None,
            "output_tokens": None,
            "source": "cache",
        }
        assert execution["replayed_usage"] == {
            "input_tokens": 7,
            "output_tokens": 5,
            "source": "provider",
        }
        tokens = replay.summary["conditions"]["B0"]["tokens"]
        assert (tokens["provider_reported_input"], tokens["provider_reported_output"]) == (0, 0)
        assert tokens["budget_charged_provider_reported"] == 0
        assert verify_run(replay.directory, make_dataset()).complete


class TestFinalization:
    def fail_writes(self, monkeypatch, *, run_statuses=(), summary_calls=()):
        """Make RunFiles.write_run fail for documents with these statuses, and
        RunFiles.write_summary fail on these call numbers (1-based)."""
        original_run, original_summary = RunFiles.write_run, RunFiles.write_summary
        calls = {"summary": 0}

        def write_run(self, document):
            if document["status"] in run_statuses:
                raise OSError("disk full")
            original_run(self, document)

        def write_summary(self, summary, markdown):
            calls["summary"] += 1
            if calls["summary"] in summary_calls:
                raise OSError("disk full")
            original_summary(self, summary, markdown)

        monkeypatch.setattr(RunFiles, "write_run", write_run)
        monkeypatch.setattr(RunFiles, "write_summary", write_summary)

    def test_successful_run_artifacts_agree(self, tmp_path):
        outcome = run(tmp_path)
        assert outcome.consistent
        assert read_run(outcome.directory)["status"] == "completed"
        assert json.loads((outcome.directory / "summary.json").read_bytes())["status"] == (
            "completed"
        )
        markdown = (outcome.directory / "summary.md").read_text(encoding="utf-8")
        assert "- Status: `completed`" in markdown

    def test_commit_failure_after_the_summary_never_claims_completion(self, tmp_path, monkeypatch):
        # Fails after the summary was written — where the summary used to be left stale.
        self.fail_writes(monkeypatch, run_statuses=("completed", "failed"))
        outcome = run(tmp_path)
        assert outcome.status == "failed" and outcome.consistent
        assert read_run(outcome.directory)["status"] == "finalizing"
        summary = json.loads((outcome.directory / "summary.json").read_bytes())
        markdown = (outcome.directory / "summary.md").read_text(encoding="utf-8")
        assert summary["status"] == "failed" and "- Status: `failed`" in markdown
        assert "`completed`" not in markdown
        report = verify_run(outcome.directory, make_dataset())
        assert not report.complete
        assert "run did not finish (status finalizing): incomplete" in report.problems

    def test_summary_failure_leaves_an_explicitly_incomplete_run(self, tmp_path, monkeypatch):
        self.fail_writes(monkeypatch, summary_calls=(1,))
        outcome = run(tmp_path)
        assert outcome.status == "failed"
        assert read_run(outcome.directory)["status"] == "finalizing"
        assert not verify_run(outcome.directory, make_dataset()).complete

    def test_double_failure_is_reported_and_never_completed(self, tmp_path, monkeypatch):
        # The commit fails, and so does rewriting the now-stale summary.
        self.fail_writes(monkeypatch, run_statuses=("completed", "failed"), summary_calls=(2,))
        outcome = run(tmp_path)
        assert outcome.status == "failed" and outcome.consistent is False
        assert read_run(outcome.directory)["status"] == "finalizing"
        report = verify_run(outcome.directory, make_dataset())
        assert not report.complete
        assert "summary.json status differs from run.json" in report.problems
