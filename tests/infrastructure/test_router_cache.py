"""Router + response cache (memory store, fake provider): reuse, expiry, isolation, failures."""

import io
import threading

import pytest

from forge.infrastructure.budgets import BudgetLimits, MemoryRunBudget
from forge.infrastructure.cache import CachePolicy, MemoryCacheStore
from forge.logging import configure_logging
from forge.providers import errors
from forge.providers.base import GenerationParams, GenerationRequest, TextDelta, Usage
from forge.providers.fake import FakeAdapter, FakeResponse
from forge.providers.router import ProviderRouter
from tests.providers.helpers import RecordingSleep, make_config

REQUEST = GenerationRequest.from_prompt(
    "hello", system="sys", params=GenerationParams(temperature=0.5, max_output_tokens=50)
)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def router_with(adapter, **overrides):
    return ProviderRouter(make_config(**overrides), adapters={"p": adapter}, sleep=RecordingSleep())


def policy(store, ttl=60, **namespace):
    return CachePolicy(store, ttl_seconds=ttl, namespace=namespace)


class TestReuse:
    def test_success_is_stored_and_reused_without_a_call(self):
        adapter = FakeAdapter(
            "p", [FakeResponse(("cached text",), usage=Usage(3, 2), reported_model="m-001")]
        )
        store = MemoryCacheStore()
        router = router_with(adapter)
        first = router.generate(REQUEST, cache=policy(store))
        second = router.generate(REQUEST, cache=policy(store))
        assert (first.cache_hit, second.cache_hit) == (False, True)
        assert second.text == first.text == "cached text"
        assert (second.usage, second.reported_model) == (Usage(3, 2), "m-001")
        assert len(adapter.calls) == 1

    def test_no_cache_policy_means_no_caching(self):
        adapter = FakeAdapter("p", default=FakeResponse(("x",)))
        router = router_with(adapter)
        router.generate(REQUEST)
        router.generate(REQUEST)
        assert len(adapter.calls) == 2

    def test_expired_entry_is_a_miss_and_is_replaced(self):
        clock = Clock()
        store = MemoryCacheStore(clock)
        adapter = FakeAdapter("p", [FakeResponse(("old",)), FakeResponse(("new",))])
        router = router_with(adapter)
        router.generate(REQUEST, cache=policy(store, ttl=60))
        clock.now += 59
        assert router.generate(REQUEST, cache=policy(store, ttl=60)).text == "old"
        clock.now += 2  # past expiry
        refreshed = router.generate(REQUEST, cache=policy(store, ttl=60))
        assert (refreshed.text, refreshed.cache_hit) == ("new", False)
        assert router.generate(REQUEST, cache=policy(store, ttl=60)).text == "new"
        assert len(adapter.calls) == 2


class TestIsolation:
    def test_different_effective_requests_never_share_entries(self):
        adapter = FakeAdapter("p", default=FakeResponse(("x",)))
        store = MemoryCacheStore()
        router = router_with(adapter)
        variants = [
            REQUEST,
            GenerationRequest.from_prompt("hello!", system="sys", params=REQUEST.params),
            GenerationRequest.from_prompt("hello", system="other", params=REQUEST.params),
            GenerationRequest.from_prompt(
                "hello",
                system="sys",
                params=GenerationParams(temperature=0.6, max_output_tokens=50),
            ),
        ]
        for request in variants:
            assert router.generate(request, cache=policy(store)).cache_hit is False
        assert (
            router.generate(REQUEST, cache=policy(store, evaluator_version="2")).cache_hit is False
        )
        assert len(store) == 5 and len(adapter.calls) == 5

    def test_profile_default_params_are_part_of_the_key(self):
        # Params merged from the model profile change the effective request.
        adapter = FakeAdapter("p", default=FakeResponse(("x",)))
        store = MemoryCacheStore()
        router = router_with(adapter)
        bare = GenerationRequest.from_prompt("hello")
        router.generate(bare, cache=policy(store))
        assert (
            router.generate(
                GenerationRequest.from_prompt("hello", params=GenerationParams(temperature=0.1)),
                cache=policy(store),
            ).cache_hit
            is False
        )


class TestNotCached:
    @pytest.mark.parametrize(
        "failure",
        [
            errors.AuthenticationError("401"),
            errors.MalformedResponseError("bad"),
            errors.UnknownProviderError("?"),
        ],
    )
    def test_failures_are_not_cached(self, failure):
        adapter = FakeAdapter("p", [failure, FakeResponse(("ok",))])
        store = MemoryCacheStore()
        router = router_with(adapter)
        with pytest.raises(type(failure)):
            router.generate(REQUEST, cache=policy(store))
        assert len(store) == 0
        assert router.generate(REQUEST, cache=policy(store)).cache_hit is False

    def test_retry_exhaustion_is_not_cached(self):
        adapter = FakeAdapter("p", [errors.UpstreamServerError("x")] * 3)
        store = MemoryCacheStore()
        with pytest.raises(errors.UpstreamServerError):
            router_with(adapter).generate(REQUEST, cache=policy(store))
        assert len(store) == 0

    def test_streams_bypass_the_cache(self):
        store = MemoryCacheStore()
        adapter = FakeAdapter("p", default=FakeResponse(("a", "b")))
        router = router_with(adapter)
        router.generate(REQUEST, cache=policy(store))  # populate
        events = list(router.stream(REQUEST))  # stream() has no cache parameter at all
        assert [e.text for e in events if isinstance(e, TextDelta)] == ["a", "b"]
        assert len(adapter.calls) == 2  # the stream made a fresh call

    @pytest.mark.parametrize(
        "chunks, finish_reason",
        [
            ((), "stop"),  # empty output (e.g. a Gemini prompt block has no candidates)
            ((), None),
            (("partial",), "SAFETY"),
            (("x",), "RECITATION"),
            (("x",), "OTHER"),
            (("x",), "FINISH_REASON_UNSPECIFIED"),
            (("x",), "content_filter"),
            (("x",), "tool_calls"),
        ],
    )
    def test_blocked_empty_or_abnormal_results_are_returned_but_not_stored(
        self, chunks, finish_reason
    ):
        adapter = FakeAdapter("p", default=FakeResponse(chunks, finish_reason=finish_reason))
        store = MemoryCacheStore()
        router = router_with(adapter)
        result = router.generate(REQUEST, cache=policy(store))
        assert (result.text, result.finish_reason, result.cache_hit) == (
            "".join(chunks),
            finish_reason,
            False,
        )
        assert len(store) == 0
        assert router.generate(REQUEST, cache=policy(store)).cache_hit is False
        assert len(adapter.calls) == 2

    @pytest.mark.parametrize("finish_reason", ["stop", "STOP", "length", "MAX_TOKENS", None])
    def test_normal_completions_are_stored(self, finish_reason):
        # Truncation at max_output_tokens is the request's own deterministic outcome.
        adapter = FakeAdapter("p", default=FakeResponse(("x",), finish_reason=finish_reason))
        store = MemoryCacheStore()
        router_with(adapter).generate(REQUEST, cache=policy(store))
        assert len(store) == 1

    def test_partial_stream_is_never_stored(self):
        store = MemoryCacheStore()
        adapter = FakeAdapter(
            "p", [FakeResponse(("partial",), error_after_chunks=errors.UpstreamServerError("x"))]
        )
        with pytest.raises(errors.UpstreamServerError):
            list(router_with(adapter).stream(REQUEST))
        assert len(store) == 0


class TestCacheAndBudget:
    def test_hits_consume_no_budget_and_are_counted(self):
        adapter = FakeAdapter("p", default=FakeResponse(("x",)))
        store = MemoryCacheStore()
        budget = MemoryRunBudget(BudgetLimits(max_model_calls=1))
        router = router_with(adapter)
        router.generate(REQUEST, cache=policy(store), budget=budget)
        for _ in range(3):
            assert router.generate(REQUEST, cache=policy(store), budget=budget).cache_hit
        assert (budget.model_calls_used, budget.cache_hits) == (1, 3)


class TestLogging:
    def test_cache_logs_carry_no_prompt_response_or_full_key(self):
        request = GenerationRequest.from_prompt(
            "PROMPT-MARKER", system="SYSTEM-MARKER", params=REQUEST.params
        )
        adapter = FakeAdapter("p", default=FakeResponse(("RESPONSE-MARKER",)))
        store = MemoryCacheStore()
        router = router_with(adapter)
        stream = io.StringIO()
        configure_logging("INFO", stream=stream)
        try:
            router.generate(request, cache=policy(store, run="NAMESPACE-MARKER"))
            router.generate(request, cache=policy(store, run="NAMESPACE-MARKER"))
        finally:
            configure_logging("INFO")
        logged = stream.getvalue()
        (full_key,) = store._entries
        for event in ('"cache.miss"', '"cache.store"', '"cache.hit"'):
            assert event in logged
        assert full_key[:12] in logged and full_key not in logged
        for marker in ("PROMPT-MARKER", "SYSTEM-MARKER", "RESPONSE-MARKER", "NAMESPACE-MARKER"):
            assert marker not in logged


class TestConcurrency:
    def test_concurrent_identical_requests_store_one_consistent_entry(self):
        adapter = FakeAdapter("p", default=FakeResponse(("same",)))
        store = MemoryCacheStore()
        router = router_with(adapter, max_concurrency=8, acquire_timeout_seconds=5)
        results, start = [], threading.Barrier(8)

        def call():
            start.wait()
            results.append(router.generate(REQUEST, cache=policy(store)).text)

        threads = [threading.Thread(target=call) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert results == ["same"] * 8
        assert len(store) == 1
        assert 1 <= len(adapter.calls) <= 8  # no single-flight: concurrent misses may each call
