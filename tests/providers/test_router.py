import copy
import json
import threading

import pytest

from forge.providers import errors
from forge.providers.base import (
    Capabilities,
    GenerationParams,
    GenerationRequest,
    StreamEnd,
    TextDelta,
    Usage,
)
from forge.providers.config import parse_providers_config
from forge.providers.fake import FakeAdapter, FakeResponse
from forge.providers.router import ProviderRouter

from .helpers import BASE_CONFIG, MaxRng, RecordingSleep, make_config

REQUEST = GenerationRequest.from_prompt("hello", system="be brief")


def make_router(adapter, sleep=None, **provider_overrides):
    return ProviderRouter(
        make_config(**provider_overrides),
        adapters={"p": adapter},
        sleep=sleep or RecordingSleep(),
        rng=MaxRng(),
    )


def texts(events):
    return [e.text for e in events if isinstance(e, TextDelta)]


class TestGenerateAndStream:
    def test_generate_success_and_identity(self):
        usage = Usage(input_tokens=3, output_tokens=2)
        adapter = FakeAdapter(
            "p", [FakeResponse(("ab", "c"), usage=usage, reported_model="model-x-001")]
        )
        result = make_router(adapter).generate(REQUEST)
        assert (result.provider, result.model, result.text) == ("p", "model-x", "abc")
        assert result.reported_model == "model-x-001"
        assert result.usage == usage
        assert adapter.calls[0].model == "model-x"
        assert adapter.calls[0].request.system == "be brief"

    def test_stream_success(self):
        adapter = FakeAdapter("p", [FakeResponse(("a", "b"), finish_reason="stop")])
        events = list(make_router(adapter).stream(REQUEST))
        assert texts(events) == ["a", "b"]
        assert events[-1] == StreamEnd(finish_reason="stop")

    def test_usage_absent_when_not_reported(self):
        adapter = FakeAdapter("p", [FakeResponse(("x",))])
        assert make_router(adapter).generate(REQUEST).usage is None

    def test_empty_response(self):
        adapter = FakeAdapter("p", [FakeResponse(())])
        assert make_router(adapter).generate(REQUEST).text == ""

    def test_profile_params_fill_unset_request_params(self):
        data = copy.deepcopy(BASE_CONFIG)
        data["models"]["main"]["params"] = {"temperature": 0.1, "max_output_tokens": 99}
        config = parse_providers_config(json.dumps(data))
        adapter = FakeAdapter("p", [FakeResponse(("x",))])
        router = ProviderRouter(config, adapters={"p": adapter})
        request = GenerationRequest.from_prompt("q", params=GenerationParams(temperature=0.7))
        router.generate(request)
        assert adapter.calls[0].request.params == GenerationParams(
            temperature=0.7, max_output_tokens=99
        )

    def test_unknown_profile(self):
        with pytest.raises(errors.ProviderConfigurationError, match="Unknown model profile"):
            make_router(FakeAdapter("p")).generate(REQUEST, model="missing")

    def test_adapters_are_created_lazily(self):
        router = ProviderRouter(make_config(fake_response="hi"))
        assert router._adapters == {}
        assert router.generate(REQUEST).text == "hi"
        assert set(router._adapters) == {"p"}

    def test_unexpected_adapter_exception_is_normalized(self):
        class Broken(FakeAdapter):
            def generate(self, model, request):
                raise KeyError("boom")

        with pytest.raises(errors.UnknownProviderError) as info:
            make_router(Broken("p")).generate(REQUEST)
        assert isinstance(info.value.__cause__, KeyError)


class TestCapabilities:
    @pytest.mark.parametrize(
        ("caps", "request_", "stream", "feature"),
        [
            (Capabilities(streaming=False), REQUEST, True, "streaming"),
            (Capabilities(system_instruction=False), REQUEST, False, "system_instruction"),
            (
                Capabilities(seed=False),
                GenerationRequest.from_prompt("q", params=GenerationParams(seed=1)),
                False,
                "seed",
            ),
        ],
    )
    def test_unsupported_features_are_rejected(self, caps, request_, stream, feature):
        adapter = FakeAdapter("p", [FakeResponse(("x",))], capabilities=caps)
        router = make_router(adapter)
        with pytest.raises(errors.UnsupportedCapabilityError, match=feature):
            list(router.stream(request_)) if stream else router.generate(request_)
        assert adapter.calls == []

    def test_supported_seed_is_passed(self):
        adapter = FakeAdapter("p", [FakeResponse(("x",))], capabilities=Capabilities(seed=True))
        make_router(adapter).generate(
            GenerationRequest.from_prompt("q", params=GenerationParams(seed=7))
        )
        assert adapter.calls[0].request.params.seed == 7


class TestRetries:
    @pytest.mark.parametrize(
        "transient",
        [
            errors.UpstreamServerError("5xx"),
            errors.ProviderUnavailableError("conn"),
            errors.ProviderTimeoutError("t"),
            errors.RateLimitError("429"),
        ],
    )
    def test_transient_failure_then_success(self, transient):
        sleep = RecordingSleep()
        adapter = FakeAdapter("p", [transient, FakeResponse(("ok",))])
        assert make_router(adapter, sleep).generate(REQUEST).text == "ok"
        assert len(adapter.calls) == 2
        assert sleep.delays == [1.0]

    @pytest.mark.parametrize(
        "permanent",
        [
            errors.AuthenticationError("401"),
            errors.InvalidRequestError("400"),
            errors.MalformedResponseError("bad"),
            errors.ProviderConfigurationError("no key"),
            errors.UnknownProviderError("?"),
        ],
    )
    def test_permanent_failure_is_not_retried(self, permanent):
        sleep = RecordingSleep()
        adapter = FakeAdapter("p", [permanent, FakeResponse(("never",))])
        with pytest.raises(type(permanent)):
            make_router(adapter, sleep).generate(REQUEST)
        assert len(adapter.calls) == 1
        assert sleep.delays == []

    def test_retry_exhaustion_raises_last_error(self):
        sleep = RecordingSleep()
        adapter = FakeAdapter(
            "p",
            [
                errors.UpstreamServerError("a"),
                errors.UpstreamServerError("b"),
                errors.UpstreamServerError("c"),
                FakeResponse(("never",)),
            ],
        )
        with pytest.raises(errors.UpstreamServerError, match="c"):
            make_router(adapter, sleep).generate(REQUEST)
        assert len(adapter.calls) == 3
        assert sleep.delays == [1.0, 2.0]  # deterministic: MaxRng picks the jitter ceiling

    def test_retry_after_is_honored(self):
        sleep = RecordingSleep()
        adapter = FakeAdapter(
            "p", [errors.RateLimitError("429", retry_after=4.5), FakeResponse(("ok",))]
        )
        make_router(adapter, sleep).generate(REQUEST)
        assert sleep.delays == [4.5]

    def test_unreasonable_retry_after_is_not_waited_for(self):
        sleep = RecordingSleep()
        adapter = FakeAdapter(
            "p", [errors.RateLimitError("429", retry_after=600), FakeResponse(("ok",))]
        )
        with pytest.raises(errors.RateLimitError):
            make_router(adapter, sleep).generate(REQUEST)
        assert sleep.delays == []

    def test_stream_retries_before_any_output(self):
        sleep = RecordingSleep()
        adapter = FakeAdapter(
            "p",
            [
                FakeResponse((), error_after_chunks=errors.UpstreamServerError("early")),
                FakeResponse(("ok",)),
            ],
        )
        assert texts(make_router(adapter, sleep).stream(REQUEST)) == ["ok"]
        assert len(adapter.calls) == 2

    def test_stream_is_not_retried_after_output_was_delivered(self):
        sleep = RecordingSleep()
        adapter = FakeAdapter(
            "p",
            [
                FakeResponse(
                    ("partial",), error_after_chunks=errors.UpstreamServerError("mid-stream")
                ),
                FakeResponse(("never",)),
            ],
        )
        received = []
        with pytest.raises(errors.UpstreamServerError):
            for event in make_router(adapter, sleep).stream(REQUEST):
                received.append(event)
        assert texts(received) == ["partial"]
        assert len(adapter.calls) == 1
        assert sleep.delays == []


class TestConcurrency:
    def test_limit_is_enforced_and_slot_released(self):
        adapter = FakeAdapter("p", default=FakeResponse(("a", "b")))
        router = make_router(adapter, max_concurrency=1, acquire_timeout_seconds=0)
        first = router.stream(REQUEST)
        next(first)  # holds the only slot
        with pytest.raises(errors.ConcurrencyLimitError):
            router.generate(REQUEST)
        list(first)  # completes; slot released
        assert router.generate(REQUEST).text == "ab"

    def test_concurrency_error_is_not_retried(self):
        sleep = RecordingSleep()
        adapter = FakeAdapter("p", default=FakeResponse(("a",)))
        router = make_router(adapter, sleep, max_concurrency=1, acquire_timeout_seconds=0)
        holder = router.stream(REQUEST)
        next(holder)
        with pytest.raises(errors.ConcurrencyLimitError):
            router.generate(REQUEST)
        assert sleep.delays == []
        holder.close()

    def test_slot_released_after_exception(self):
        adapter = FakeAdapter(
            "p", [errors.AuthenticationError("401")], default=FakeResponse(("ok",))
        )
        router = make_router(adapter, max_concurrency=1, acquire_timeout_seconds=0)
        with pytest.raises(errors.AuthenticationError):
            router.generate(REQUEST)
        assert router.generate(REQUEST).text == "ok"

    def test_slot_and_stream_released_when_consumer_closes_early(self):
        adapter = FakeAdapter("p", default=FakeResponse(("a", "b", "c")))
        router = make_router(adapter, max_concurrency=1, acquire_timeout_seconds=0)
        stream = router.stream(REQUEST)
        assert next(stream) == TextDelta("a")
        assert adapter.open_streams == 1
        stream.close()  # e.g. the HTTP client disconnected
        assert adapter.open_streams == 0
        assert router.generate(REQUEST).text == "abc"

    def test_slot_is_free_while_backing_off(self):
        router_ref = {}
        free_during_sleep = []

        def on_sleep(_seconds):
            semaphore = router_ref["router"]._slots["p"]
            acquired = semaphore.acquire(blocking=False)
            free_during_sleep.append(acquired)
            if acquired:
                semaphore.release()

        adapter = FakeAdapter("p", [errors.UpstreamServerError("x"), FakeResponse(("ok",))])
        router = make_router(adapter, RecordingSleep(on_sleep), max_concurrency=1)
        router_ref["router"] = router
        router.generate(REQUEST)
        assert free_during_sleep == [True]

    def test_concurrent_threads_never_exceed_limit(self):
        limit = 2
        gate = threading.Event()
        lock = threading.Lock()
        state = {"active": 0, "peak": 0}

        class Slow(FakeAdapter):
            def generate(self, model, request):
                with lock:
                    state["active"] += 1
                    state["peak"] = max(state["peak"], state["active"])
                gate.wait(timeout=5)
                with lock:
                    state["active"] -= 1
                return super().generate(model, request)

        adapter = Slow("p", default=FakeResponse(("ok",)))
        router = make_router(adapter, max_concurrency=limit, acquire_timeout_seconds=5)
        results = []
        threads = [
            threading.Thread(target=lambda: results.append(router.generate(REQUEST).text))
            for _ in range(6)
        ]
        for t in threads:
            t.start()
        threading.Timer(0.2, gate.set).start()
        for t in threads:
            t.join(timeout=10)
        assert results == ["ok"] * 6
        assert state["peak"] == limit
