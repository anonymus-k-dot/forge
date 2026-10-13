"""Budget limits, plan checks, and router enforcement with the in-memory guard."""

import threading

import pytest

from forge.errors import ConfigurationError
from forge.infrastructure.budgets import (
    BudgetConfirmationRequiredError,
    BudgetExceededError,
    BudgetLimits,
    InvalidBudgetError,
    MemoryRunBudget,
    RunPlan,
    check_plan,
    estimate_reservation_tokens,
)
from forge.providers import errors
from forge.providers.base import GenerationParams, GenerationRequest, Usage
from forge.providers.fake import FakeAdapter, FakeResponse
from forge.providers.router import ProviderRouter
from tests.providers.helpers import RecordingSleep, make_config

REQUEST = GenerationRequest.from_prompt(
    "x" * 40, system="y" * 40, params=GenerationParams(max_output_tokens=100)
)  # estimate: ceil(80 / 4) + 100 = 120 tokens


def router_with(adapter, **overrides):
    return ProviderRouter(make_config(**overrides), adapters={"p": adapter}, sleep=RecordingSleep())


class TestLimits:
    def test_max_model_calls_is_required(self):
        with pytest.raises(InvalidBudgetError, match="max_model_calls"):
            BudgetLimits.parse({})

    @pytest.mark.parametrize(
        "limits",
        [
            {"max_model_calls": 0},
            {"max_model_calls": -1},
            {"max_model_calls": "10"},
            {"max_model_calls": 10.0},
            {"max_model_calls": True},
            {"max_model_calls": 10**7},
            {"max_model_calls": 5, "max_estimated_tokens": 0},
            {"max_model_calls": 5, "surprise": 1},
            {"max_model_calls": 5, "max_samples_per_case": 0},
            "not-a-dict",
        ],
    )
    def test_invalid_limits_are_rejected(self, limits):
        with pytest.raises(InvalidBudgetError) as info:
            BudgetLimits.parse(limits)
        assert isinstance(info.value, ConfigurationError)
        assert info.value.code == "invalid_budget"

    def test_valid_limits_round_trip(self):
        limits = BudgetLimits.parse({"max_model_calls": 5, "max_estimated_tokens": 1000})
        assert limits.to_json() == {"max_model_calls": 5, "max_estimated_tokens": 1000}


class TestPlan:
    LIMITS = BudgetLimits(
        max_model_calls=100,
        max_cases=10,
        max_samples_per_case=3,
        max_candidates=4,
        confirm_above_model_calls=50,
    )

    def test_estimate(self):
        estimate = check_plan(
            self.LIMITS,
            RunPlan(cases=5, systems=3, samples_per_case=1),
            max_attempts=3,
            confirmed=True,
        )
        assert (estimate.min_model_calls, estimate.max_model_calls) == (15, 45)

    @pytest.mark.parametrize(
        ("plan", "dimension"),
        [
            (RunPlan(cases=11, systems=1), "cases"),
            (RunPlan(cases=1, systems=1, samples_per_case=4), "samples_per_case"),
            (RunPlan(cases=1, systems=1, candidates=5), "candidates"),
            (RunPlan(cases=10, systems=11), "model_calls"),
        ],
    )
    def test_plans_exceeding_limits_are_rejected_before_running(self, plan, dimension):
        with pytest.raises(BudgetExceededError) as info:
            check_plan(self.LIMITS, plan, max_attempts=1, confirmed=True)
        assert info.value.dimension == dimension and info.value.code == "budget_exceeded"

    def test_confirmation_required_above_threshold(self):
        plan = RunPlan(cases=10, systems=2)  # 20 calls, 60 worst case with 3 attempts
        with pytest.raises(BudgetConfirmationRequiredError) as info:
            check_plan(self.LIMITS, plan, max_attempts=3)
        assert (info.value.estimated_calls, info.value.threshold) == (60, 50)
        assert check_plan(self.LIMITS, plan, max_attempts=3, confirmed=True).max_model_calls == 60

    @pytest.mark.parametrize("bad", [0, -1, True, 2.5])
    def test_invalid_plan_values(self, bad):
        with pytest.raises(InvalidBudgetError):
            check_plan(self.LIMITS, RunPlan(cases=bad, systems=1), max_attempts=1)

    def test_token_estimate(self):
        assert estimate_reservation_tokens(REQUEST) == 120
        assert estimate_reservation_tokens(GenerationRequest.from_prompt("x")) is None


class TestCallAccounting:
    def test_within_budget_succeeds(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=2))
        adapter = FakeAdapter("p", default=FakeResponse(("ok",)))
        router = router_with(adapter)
        router.generate(REQUEST, budget=budget)
        router.generate(REQUEST, budget=budget)
        assert budget.model_calls_used == 2

    def test_exhausted_budget_rejects_before_the_provider_is_called(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=1))
        adapter = FakeAdapter("p", default=FakeResponse(("ok",)))
        router = router_with(adapter)
        router.generate(REQUEST, budget=budget)
        with pytest.raises(BudgetExceededError, match="model_calls"):
            router.generate(REQUEST, budget=budget)
        assert len(adapter.calls) == 1

    def test_every_retry_attempt_consumes_a_call(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=10))
        adapter = FakeAdapter(
            "p",
            [
                errors.UpstreamServerError("a"),
                errors.UpstreamServerError("b"),
                FakeResponse(("ok",)),
            ],
        )
        router_with(adapter).generate(REQUEST, budget=budget)
        assert budget.model_calls_used == 3

    def test_budget_stops_retries_midway(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=2))
        adapter = FakeAdapter(
            "p",
            [
                errors.UpstreamServerError("a"),
                errors.UpstreamServerError("b"),
                FakeResponse(("never",)),
            ],
        )
        with pytest.raises(BudgetExceededError):
            router_with(adapter).generate(REQUEST, budget=budget)
        assert len(adapter.calls) == 2 and budget.model_calls_used == 2

    def test_failed_attempts_are_not_refunded(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=5))
        adapter = FakeAdapter("p", [errors.AuthenticationError("401")])
        with pytest.raises(errors.AuthenticationError):
            router_with(adapter).generate(REQUEST, budget=budget)
        assert budget.model_calls_used == 1

    def test_concurrency_limit_rejection_consumes_nothing(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=5))
        adapter = FakeAdapter("p", default=FakeResponse(("a", "b")))
        router = router_with(adapter, max_concurrency=1, acquire_timeout_seconds=0)
        holder = router.stream(REQUEST)
        next(holder)
        with pytest.raises(errors.ConcurrencyLimitError):
            router.generate(REQUEST, budget=budget)
        holder.close()
        assert budget.model_calls_used == 0

    def test_concurrent_requests_cannot_overspend(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=5))
        adapter = FakeAdapter("p", default=FakeResponse(("ok",)))
        router = router_with(adapter, max_concurrency=20, acquire_timeout_seconds=5)
        outcomes, start = [], threading.Barrier(20)

        def call():
            start.wait()
            try:
                router.generate(REQUEST, budget=budget)
                outcomes.append("ok")
            except BudgetExceededError:
                outcomes.append("exceeded")

        threads = [threading.Thread(target=call) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert outcomes.count("ok") == 5 and outcomes.count("exceeded") == 15
        assert budget.model_calls_used == 5 and len(adapter.calls) == 5


class TestTokenAccounting:
    def test_reserve_then_reconcile_to_provider_usage(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=10, max_estimated_tokens=1000))
        adapter = FakeAdapter("p", [FakeResponse(("ok",), usage=Usage(30, 12))])
        router_with(adapter).generate(REQUEST, budget=budget)
        assert (budget.tokens_used, budget.tokens_reserved) == (42, 0)

    def test_estimate_kept_without_provider_usage_or_on_failure(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=10, max_estimated_tokens=1000))
        adapter = FakeAdapter("p", [FakeResponse(("ok",)), errors.AuthenticationError("401")])
        router = router_with(adapter)
        router.generate(REQUEST, budget=budget)
        with pytest.raises(errors.AuthenticationError):
            router.generate(REQUEST, budget=budget)
        assert (budget.tokens_used, budget.tokens_reserved) == (240, 0)

    def test_reservation_that_does_not_fit_is_rejected_before_calling(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=10, max_estimated_tokens=200))
        adapter = FakeAdapter("p", default=FakeResponse(("ok",), usage=Usage(60, 40)))
        router = router_with(adapter)
        router.generate(REQUEST, budget=budget)  # reserves 120 (fits), then charges 100
        with pytest.raises(BudgetExceededError, match="tokens"):  # 100 used + 120 > 200
            router.generate(REQUEST, budget=budget)
        assert len(adapter.calls) == 1
        assert (budget.tokens_used, budget.tokens_reserved, budget.model_calls_used) == (100, 0, 1)

    def test_token_budget_requires_bounded_output(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=10, max_estimated_tokens=1000))
        adapter = FakeAdapter("p", default=FakeResponse(("ok",)))
        with pytest.raises(InvalidBudgetError, match="max_output_tokens"):
            router_with(adapter).generate(GenerationRequest.from_prompt("x"), budget=budget)
        assert adapter.calls == []


class TestStreamingAccounting:
    def test_stream_attempts_are_charged_and_settled(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=5, max_estimated_tokens=1000))
        adapter = FakeAdapter("p", [FakeResponse(("a", "b"), usage=Usage(5, 2))])
        list(router_with(adapter).stream(REQUEST, budget=budget))
        assert (budget.model_calls_used, budget.tokens_used, budget.tokens_reserved) == (1, 7, 0)

    def test_abandoned_stream_keeps_the_estimate(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=5, max_estimated_tokens=1000))
        adapter = FakeAdapter("p", [FakeResponse(("a", "b", "c"), usage=Usage(5, 2))])
        stream = router_with(adapter).stream(REQUEST, budget=budget)
        next(stream)
        stream.close()  # client disconnected
        assert (budget.tokens_used, budget.tokens_reserved) == (120, 0)

    def test_exhausted_budget_stops_stream_before_calling(self):
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=1))
        adapter = FakeAdapter("p", default=FakeResponse(("a",)))
        router = router_with(adapter)
        list(router.stream(REQUEST, budget=budget))
        with pytest.raises(BudgetExceededError):
            list(router.stream(REQUEST, budget=budget))
        assert len(adapter.calls) == 1


class TestCompatibility:
    def test_enhance_contract_unchanged_without_budget_or_cache(self):
        from forge.app import create_app
        from forge.providers.config import load_providers_config
        from forge.settings import Settings

        adapter = FakeAdapter("gemini", default=FakeResponse(("ok",)))
        router = ProviderRouter(load_providers_config(), adapters={"gemini": adapter})
        client = create_app(Settings(), router=router).test_client()
        assert client.post("/enhance", json={"prompt": "p"}).get_data(as_text=True) == (
            'data: {"chunk": "ok"}\n\ndata: {"done": true}\n\n'
        )
        client.post("/enhance", json={"prompt": "p", "stream": False})
        client.post("/enhance", json={"prompt": "p", "stream": False})
        assert len(adapter.calls) == 3  # /enhance never uses the response cache
