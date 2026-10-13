"""Offline runner behaviour: integrity, honest partial runs, budgets, cache isolation, safety."""

import io
import json

import httpx
import pytest

from forge.benchmark import runner as runner_module
from forge.benchmark.dataset import load_dataset
from forge.benchmark.manifest import manifest_sha256
from forge.benchmark.runner import BenchmarkRunner, RunFiles
from forge.benchmark.verify import verify_run
from forge.errors import ConfigurationError
from forge.infrastructure.budgets import BudgetConfirmationRequiredError, BudgetExceededError
from forge.infrastructure.cache import MemoryCacheStore
from forge.logging import configure_logging
from forge.providers import errors
from forge.providers.config import load_providers_config, parse_providers_config
from forge.providers.fake import FakeResponse
from forge.providers.openai_compatible import OpenAICompatibleAdapter
from forge.providers.router import ProviderRouter
from tests.benchmark.helpers import (
    GOOD_ANSWER,
    OFFLINE_PROVIDERS,
    PILOT_DIR,
    Responder,
    make_dataset,
    make_router,
    make_task,
    options,
    read_records,
    read_run,
    run,
    text_reply,
)
from tests.providers.helpers import RecordingSleep

VOLATILE = {"run_id", "latency_ms"}


def stable(value):
    """Records without run-specific fields, for reproducibility comparisons."""
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def tasks(n):
    return make_dataset(*(make_task(f"task-{i:03d}") for i in range(1, n + 1)))


def offline_pilot(tmp_path, **overrides):
    router = ProviderRouter(load_providers_config(OFFLINE_PROVIDERS), sleep=RecordingSleep())
    return BenchmarkRunner(router).run(
        options(
            tmp_path,
            dataset=load_dataset(PILOT_DIR),
            target_profile="offline-target",
            rewriter_profile="offline-rewriter",
            budget_limits={"max_model_calls": 150},
            **overrides,
        )
    )


class TestEndToEnd:
    def test_offline_pilot_completes_and_verifies(self, tmp_path):
        outcome = offline_pilot(tmp_path)
        assert outcome.status == "completed"
        report = verify_run(outcome.directory, load_dataset(PILOT_DIR))
        assert report.valid and report.complete and report.evaluations_recomputed
        records = read_records(outcome.directory)
        assert len(records) == 90
        run_doc = read_run(outcome.directory)
        assert run_doc["measurement"] == "offline_fixture"
        assert run_doc["interpretation"] == "INCONCLUSIVE"
        assert run_doc["budget_usage"]["model_calls_used"] == 150
        assert "SYNTHETIC" in (outcome.directory / "summary.md").read_text(encoding="utf-8")
        assert outcome.summary["interpretation"] == "INCONCLUSIVE"

    def test_offline_execution_is_reproducible(self, tmp_path):
        first = offline_pilot(tmp_path / "a")
        second = offline_pilot(tmp_path / "b")
        assert first.run_id != second.run_id
        assert first.manifest_sha256 == second.manifest_sha256
        assert (first.directory / "manifest.json").read_bytes() == (
            second.directory / "manifest.json"
        ).read_bytes()
        assert stable(read_records(first.directory)) == stable(read_records(second.directory))
        assert first.summary == second.summary

    def test_manifest_hash_changes_with_every_input(self, tmp_path):
        runner = BenchmarkRunner(make_router())
        base_opts = options(tmp_path)
        base = manifest_sha256(runner.prepare(base_opts)[2])
        assert base == manifest_sha256(runner.prepare(options(tmp_path))[2])
        variants = [
            options(
                tmp_path,
                dataset=make_dataset(
                    make_task(prompt="List three fruits as bullet points, under 20 words!!")
                ),
            ),
            options(tmp_path, dataset=make_dataset(make_task(), version="0.0.2")),
            options(tmp_path, conditions=("B0", "B1")),
            options(tmp_path, target_profile="rewriter"),
        ]
        hashes = {manifest_sha256(runner.prepare(v)[2]) for v in variants}
        assert base not in hashes and len(hashes) == len(variants)
        other_router = make_router(
            models={
                "rewriter": {"provider": "rw", "model": "rewriter-model"},
                "target": {"provider": "tg", "model": "target-model-2"},
            }
        )
        assert manifest_sha256(BenchmarkRunner(other_router).prepare(base_opts)[2]) != base

    def test_manifest_excludes_run_specific_settings(self, tmp_path):
        runner = BenchmarkRunner(make_router())
        a = runner.prepare(options(tmp_path, budget_limits={"max_model_calls": 10}))[2]
        b = runner.prepare(options(tmp_path / "x", budget_limits={"max_model_calls": 99}))[2]
        assert a == b


class TestFailuresAndDenominators:
    def test_failed_empty_and_evaluated_records_are_all_visible(self, tmp_path):
        def rewrite(_model, request):
            prompt = request.messages[0].content
            if "task-002" in prompt:
                return errors.AuthenticationError("401")  # transform fails (not retried)
            if "task-003" in prompt:
                return FakeResponse(("   ",))  # empty rewrite
            return FakeResponse((prompt,))

        def answer(_model, request):
            prompt = request.messages[0].content
            if "task-004" in prompt:
                return FakeResponse(())  # empty output
            if "task-005" in prompt:
                return errors.InvalidRequestError("400")
            return FakeResponse((GOOD_ANSWER,))

        dataset = make_dataset(
            *(
                make_task(
                    f"task-{i:03d}",
                    prompt=f"task-{i:03d}: List three fruits as bullet points, under 20 words.",
                )
                for i in range(1, 6)
            )
        )
        outcome = run(
            tmp_path,
            make_router(Responder("rw", rewrite), Responder("tg", answer)),
            dataset=dataset,
        )
        assert outcome.status == "completed"  # every pair was attempted; failures stay visible
        by_key = {(r["task_id"], r["condition"]): r for r in read_records(outcome.directory)}
        assert by_key[("task-002", "B1")]["status"] == "failed"
        assert by_key[("task-002", "B1")]["reason"] == "provider_error"
        assert by_key[("task-002", "B0")]["status"] == "evaluated"
        assert by_key[("task-003", "F-legacy")]["reason"] == "empty_transform_output"
        assert by_key[("task-004", "B0")]["evaluation"]["empty_output"] is True
        assert by_key[("task-005", "B0")]["reason"] == "provider_error"
        b0 = outcome.summary["conditions"]["B0"]
        assert b0["records"] == {"evaluated": 4, "failed": 1, "not_run": 0, "missing": 0}
        assert b0["empty_outputs"] == {"count": 1, "of": 5}
        assert b0["tasks_all_checks_passed"] == {"count": 3, "of": 5}
        assert b0["checks"] == {"defined": 10, "passed": 6, "failed": 2, "not_evaluated": 2}
        b1 = outcome.summary["conditions"]["B1"]
        assert b1["records"] == {"evaluated": 2, "failed": 3, "not_run": 0, "missing": 0}
        assert b1["failure_reasons"] == {"empty_transform_output": 1, "provider_error": 2}
        assert b1["checks"]["not_evaluated"] == 6
        # task-004's rewritten prompt still names task-004, so its target output is empty too.
        assert b1["tasks_all_checks_passed"] == {"count": 1, "of": 5}
        pair = outcome.summary["paired_check_counts"][0]
        assert (pair["a"], pair["b"], pair["compared"], pair["excluded_not_evaluated_in_both"]) == (
            "B0",
            "B1",
            2,
            3,
        )
        assert verify_run(outcome.directory, dataset).complete

    def test_retries_are_charged_and_failures_are_not_cached_as_success(self, tmp_path):
        target = Responder("tg", lambda _m, _r: errors.UpstreamServerError("503"))
        outcome = run(tmp_path, make_router(target=target), conditions=("B0",))
        (record,) = read_records(outcome.directory)
        assert record["status"] == "failed"
        assert record["executions"][0]["error_category"] == "server_error"
        assert len(target.calls) == 2  # max_attempts = 2
        assert read_run(outcome.directory)["budget_usage"]["model_calls_used"] == 2


class TestPartialRuns:
    def test_budget_exhaustion_mid_run_stops_and_records_every_pair(self, tmp_path):
        # The plan (3 tasks x 5 calls = 15) fits a budget of 15, but one retry consumes an
        # extra unit, so the last call is refused at run time.
        attempts = {"n": 0}

        def flaky_once(_model, _request):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return errors.UpstreamServerError("503")
            return FakeResponse((GOOD_ANSWER,))

        target = Responder("tg", flaky_once)
        rewriter = Responder("rw", text_reply("Rewritten"))
        outcome = run(
            tmp_path,
            make_router(rewriter, target),
            dataset=tasks(3),
            budget_limits={"max_model_calls": 15},
        )
        assert outcome.status == "budget_exceeded"
        records = read_records(outcome.directory)
        assert len(records) == 9  # every pair is still represented
        assert len(rewriter.calls) + len(target.calls) == 15  # never more than the budget
        assert [r["status"] for r in records[:8]] == ["evaluated"] * 8
        last = records[8]
        assert (last["task_id"], last["condition"], last["status"], last["reason"]) == (
            "task-003",
            "F-legacy",
            "not_run",
            "budget_exceeded",
        )
        # Its rewrite call happened and is recorded; the refused target call is not.
        assert [e["role"] for e in last["executions"]] == ["generator"]
        assert outcome.summary["conditions"]["F-legacy"]["records"]["not_run"] == 1
        report = verify_run(outcome.directory, tasks(3))
        assert report.valid and not report.complete
        assert read_run(outcome.directory)["budget_usage"]["model_calls_used"] == 15

    def test_plan_exceeding_the_budget_is_rejected_before_any_call(self, tmp_path):
        target = Responder("tg", text_reply(GOOD_ANSWER))
        with pytest.raises(BudgetExceededError):
            run(tmp_path, make_router(target=target), budget_limits={"max_model_calls": 4})
        assert target.calls == [] and not (tmp_path / "runs").exists()

    def test_confirmation_threshold(self, tmp_path):
        limits = {"max_model_calls": 100, "confirm_above_model_calls": 5}
        with pytest.raises(BudgetConfirmationRequiredError):
            run(tmp_path, budget_limits=limits)
        assert run(tmp_path, budget_limits=limits, confirmed=True).status == "completed"

    def test_cancellation_stops_scheduling(self, tmp_path):
        target = Responder("tg", text_reply(GOOD_ANSWER))
        checks = iter([False, False, True])
        outcome = run(
            tmp_path,
            make_router(target=target),
            dataset=tasks(2),
            should_stop=lambda: next(checks, True),
        )
        assert outcome.status == "cancelled"
        records = read_records(outcome.directory)
        assert [r["status"] for r in records] == ["evaluated", "evaluated"] + ["not_run"] * 4
        assert {r["reason"] for r in records[2:]} == {"cancelled"}
        assert len(target.calls) == 2  # nothing scheduled after cancellation
        assert not verify_run(outcome.directory).complete

    def test_keyboard_interrupt_finalizes_as_cancelled(self, tmp_path):
        def interrupt(_m, _r):
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            run(tmp_path, make_router(target=Responder("tg", interrupt)), conditions=("B0",))
        (directory,) = (tmp_path / "runs").iterdir()
        assert read_run(directory)["status"] == "cancelled"
        assert read_records(directory)[0]["reason"] == "cancelled"

    def test_interrupted_pair_keeps_the_calls_already_made(self, tmp_path):
        def interrupt(_m, _r):
            raise KeyboardInterrupt

        rewriter = Responder("rw", text_reply("Rewritten"))
        with pytest.raises(KeyboardInterrupt):
            run(
                tmp_path,
                make_router(rewriter, Responder("tg", interrupt)),
                conditions=("B1",),
            )
        (directory,) = (tmp_path / "runs").iterdir()
        (record,) = read_records(directory)
        assert (record["status"], record["reason"]) == ("not_run", "cancelled")
        assert [e["role"] for e in record["executions"]] == ["generator"]  # not lost
        assert len(rewriter.calls) == 1

    def test_internal_error_is_finalized_as_failed_and_reraised(self, tmp_path, monkeypatch):
        def broken(*_args):
            raise RuntimeError("bug")

        monkeypatch.setattr(runner_module, "evaluate", broken)
        with pytest.raises(RuntimeError):
            run(tmp_path, conditions=("B0",))
        (directory,) = (tmp_path / "runs").iterdir()
        run_doc = read_run(directory)
        assert run_doc["status"] == "failed"
        assert run_doc["failure"] == {"reason": "internal_error", "error_type": "RuntimeError"}


class TestPersistenceFailures:
    def test_results_write_failure_never_reports_completion(self, tmp_path, monkeypatch):
        original = RunFiles.append_record
        writes = {"n": 0}

        def flaky(self, record):
            writes["n"] += 1
            if writes["n"] == 2:
                raise OSError("disk full")
            original(self, record)

        monkeypatch.setattr(RunFiles, "append_record", flaky)
        outcome = run(tmp_path, dataset=tasks(2))
        assert outcome.status == "failed"
        assert outcome.persistence == {"files": "failed", "database": "disabled"}
        assert outcome.stop_reason == "persistence_failed"
        assert read_run(outcome.directory)["status"] == "running"  # never finalized on disk
        report = verify_run(outcome.directory)
        assert not report.complete and "incomplete" in " ".join(report.problems)

    def test_final_run_document_failure(self, tmp_path, monkeypatch):
        original = RunFiles.write_run

        def fail_final(self, document):
            if document["finished_at"] is not None:
                raise OSError("read-only")
            original(self, document)

        monkeypatch.setattr(RunFiles, "write_run", fail_final)
        outcome = run(tmp_path)
        assert outcome.status == "failed"
        assert read_run(outcome.directory)["status"] == "running"
        assert not verify_run(outcome.directory).complete

    def test_existing_run_directory_is_never_overwritten(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner_module.uuid, "uuid4", lambda: "fixed-id")
        run(tmp_path)
        with pytest.raises(FileExistsError):
            run(tmp_path)


class TestCacheIsolation:
    def same_text_router(self):
        # B1 and F-legacy rewrites return identical text, so their target requests are
        # identical: only the namespace keeps their cache entries apart.
        return make_router(
            Responder("rw", text_reply("IDENTICAL REWRITE")),
            Responder("tg", text_reply(GOOD_ANSWER)),
        )

    def test_conditions_never_share_entries_within_a_run(self, tmp_path):
        store = MemoryCacheStore()
        router = self.same_text_router()
        outcome = run(tmp_path, router, cache_store=store, cache=True)
        records = read_records(outcome.directory)
        assert not any(e["cache_hit"] for r in records for e in r["executions"])
        assert len(store) == 5  # B0 target, B1 gen+target, F-legacy gen+target

    def test_runs_are_isolated_by_default_and_replay_only_with_a_shared_scope(self, tmp_path):
        store = MemoryCacheStore()
        first = run(tmp_path / "1", self.same_text_router(), cache_store=store, cache=True)
        second = run(tmp_path / "2", self.same_text_router(), cache_store=store, cache=True)
        assert second.summary["conditions"]["B1"]["accounting"]["cache_hits"] == 0
        assert read_run(first.directory)["cache"]["scope"] == first.run_id

        router = self.same_text_router()
        scoped = run(tmp_path / "3", router, cache_store=store, cache=True, cache_scope="s1")
        assert scoped.summary["conditions"]["B0"]["accounting"]["cache_hits"] == 0
        replay_router = self.same_text_router()
        replay = run(tmp_path / "4", replay_router, cache_store=store, cache=True, cache_scope="s1")
        calls = replay.summary["conditions"]
        assert [calls[c]["accounting"] for c in ("B0", "B1", "F-legacy")] == [
            {
                "condition_results": 1,
                "executions": n,
                "provider_attempts": 0,
                "cache_hits": n,
                "executions_refused_before_dispatch": 0,
                "execution_errors": 0,
            }
            for n in (1, 2, 2)
        ]
        replayed = [e for r in read_records(replay.directory) for e in r["executions"]]
        assert all(e["usage"]["source"] == "cache" and e["attempts"] == 0 for e in replayed)
        assert replay.summary["run_accounting"]["provider_attempts_recorded"] == 0
        assert replay_router.adapter("tg").calls == []
        run_doc = read_run(replay.directory)
        assert run_doc["budget_usage"]["model_calls_used"] == 0  # hits are not new calls
        assert run_doc["budget_usage"]["cache_hits"] == 5
        assert stable(read_records(replay.directory)) != stable(read_records(scoped.directory))
        assert verify_run(replay.directory, make_dataset()).complete

    def test_cache_without_a_store_or_database_is_refused(self, tmp_path):
        with pytest.raises(ConfigurationError, match="requires --database"):
            run(tmp_path, cache=True)


class TestSafety:
    def test_real_providers_are_refused_by_default(self, tmp_path):
        config = parse_providers_config(
            json.dumps(
                {
                    "default_model": "real",
                    "providers": {
                        "remote": {
                            "type": "openai_compatible",
                            "base_url": "https://api.example.invalid/v1",
                            "api_key_env": "SOME_KEY",
                        }
                    },
                    "models": {"real": {"provider": "remote", "model": "m"}},
                }
            )
        )
        with pytest.raises(ConfigurationError, match="not authorized"):
            BenchmarkRunner(ProviderRouter(config)).run(
                options(tmp_path, target_profile="real", conditions=("B0",))
            )
        assert not (tmp_path / "runs").exists()

    def test_no_credentials_or_prompts_in_artifacts_or_logs(self, tmp_path):
        secret, env_name = "sk-test-SECRET-VALUE-9f8e7d6c5b4a", "BENCH_TEST_API_KEY"
        seen_auth = []

        def server(request: httpx.Request) -> httpx.Response:
            seen_auth.append(request.headers.get("authorization"))
            return httpx.Response(
                200,
                json={
                    "model": "m-remote",
                    "choices": [{"message": {"content": GOOD_ANSWER}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 5},
                },
            )

        config = parse_providers_config(
            json.dumps(
                {
                    "default_model": "real",
                    "providers": {
                        "loc": {
                            "type": "openai_compatible",
                            "base_url": "http://127.0.0.1:9/v1",
                            "api_key_env": env_name,
                        }
                    },
                    "models": {"real": {"provider": "loc", "model": "m"}},
                }
            )
        )
        adapter = OpenAICompatibleAdapter(
            "loc",
            base_url="http://127.0.0.1:9/v1",
            auth="bearer",
            api_key_env=env_name,
            get_secret=lambda name: secret if name == env_name else None,
            timeout_seconds=5,
            transport=httpx.MockTransport(server),
        )
        router = ProviderRouter(config, adapters={"loc": adapter}, sleep=RecordingSleep())
        task = make_task(
            prompt="PROMPT-MARKER: List three fruits as bullet points, under 20 words."
        )
        stream = io.StringIO()
        configure_logging("INFO", stream=stream)
        try:
            outcome = BenchmarkRunner(router).run(
                options(
                    tmp_path,
                    dataset=make_dataset(task),
                    target_profile="real",
                    rewriter_profile="real",
                    allow_real_providers=True,
                )
            )
        finally:
            configure_logging("INFO")
        assert seen_auth and all(a == f"Bearer {secret}" for a in seen_auth)  # secret was used
        assert outcome.status == "completed"
        assert read_run(outcome.directory)["measurement"] == "model_outputs"
        b0 = read_records(outcome.directory)[0]["executions"][0]
        assert b0["usage"] == {"input_tokens": 7, "output_tokens": 5, "source": "provider"}
        artifacts = b"".join(p.read_bytes() for p in outcome.directory.iterdir())
        logged = stream.getvalue()
        for forbidden in (secret, env_name, "Bearer", "127.0.0.1:9"):
            assert forbidden.encode() not in artifacts
            assert forbidden not in logged
        assert "PROMPT-MARKER" not in logged and GOOD_ANSWER not in logged
        assert '"benchmark.record"' in logged
