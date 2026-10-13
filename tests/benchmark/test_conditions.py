"""B0 / B1 / F-legacy: same underlying task, distinct transforms, no hidden information."""

import json
from dataclasses import asdict

import pytest

from forge.app import create_app
from forge.benchmark import conditions
from forge.benchmark.conditions import (
    B1_TEMPLATE,
    CONDITIONS,
    TARGET_PARAMS,
    get_conditions,
    request_template_sha256,
)
from forge.legacy import enhance as legacy
from forge.providers.config import load_providers_config
from forge.providers.fake import FakeAdapter, FakeResponse
from forge.providers.router import ProviderRouter
from forge.settings import Settings
from tests.benchmark.helpers import (
    GOOD_ANSWER,
    REPO_ROOT,
    Responder,
    make_dataset,
    make_router,
    make_task,
    run,
    text_reply,
)

PROMPT = "  List three fruits as bullet points,\nunder 20 words.  "


def contents(adapter):
    return [
        (call.request.system, [m.content for m in call.request.messages]) for call in adapter.calls
    ]


def run_all(tmp_path, **task_fields):
    rewriter = Responder("rw", text_reply("  REWRITTEN PROMPT  "))
    target = Responder("tg", text_reply(GOOD_ANSWER))
    task = make_task(prompt=PROMPT, **task_fields)
    outcome = run(tmp_path, make_router(rewriter, target), dataset=make_dataset(task))
    return outcome, rewriter, target, task


def test_b0_sends_the_task_prompt_byte_for_byte(tmp_path):
    _, _, target, _ = run_all(tmp_path)
    b0_call = target.calls[0]  # protocol order: B0, B1, F-legacy
    assert [m.content for m in b0_call.request.messages] == [PROMPT]
    assert b0_call.request.system is None


def test_transforms_receive_only_the_task_prompt(tmp_path):
    _, rewriter, target, task = run_all(
        tmp_path, notes="HIDDEN-NOTE-MARKER", category="coding", task_id="task-hidden-id"
    )
    b1, forge_call = rewriter.calls
    assert b1.request.messages[0].content == B1_TEMPLATE.replace("<<TASK_PROMPT>>", PROMPT)
    assert forge_call.request == legacy.build_request(PROMPT)
    everything = repr(contents(rewriter) + contents(target))
    for hidden in ("HIDDEN-NOTE-MARKER", "task-hidden-id", "word_count", "list_items", "coding"):
        assert hidden not in everything


def test_target_is_called_identically_for_every_condition(tmp_path):
    _, _, target, _ = run_all(tmp_path)
    assert len(target.calls) == 3
    for call in target.calls:
        assert call.request.system is None
        assert call.request.params == TARGET_PARAMS
    # B1 output is stripped; F-legacy output is cleaned by the legacy cleaner.
    assert [m.content for m in target.calls[1].request.messages] == ["REWRITTEN PROMPT"]
    assert [m.content for m in target.calls[2].request.messages] == [
        legacy.clean_output("  REWRITTEN PROMPT  ")
    ]


def test_f_legacy_uses_the_unchanged_legacy_request_and_cleaner():
    request = CONDITIONS["F-legacy"].transform.build(PROMPT)
    assert request == legacy.build_request(PROMPT)
    assert request.params == legacy.LEGACY_PARAMS
    raw = "[ENHANCED PROMPT]:\nDo the thing\n━━━━━━\n"
    assert CONDITIONS["F-legacy"].transform.postprocess(raw) == legacy.clean_output(raw)


def test_b1_is_independent_of_the_forge_implementation(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("B1 must not use the FORGE legacy enhancer")

    monkeypatch.setattr(legacy, "build_request", forbidden)
    monkeypatch.setattr(legacy, "build_forge_prompt", forbidden)
    monkeypatch.setattr(legacy, "clean_output", forbidden)
    rewriter = Responder("rw", text_reply("B1 output"))
    outcome = run(tmp_path, make_router(rewriter), conditions=("B1",))
    assert outcome.status == "completed"
    request = rewriter.calls[0].request
    assert request.system is None
    assert "FORGE" not in request.messages[0].content
    assert legacy.build_forge_prompt.__name__ == "forbidden"  # the patch was in effect


def test_b1_does_not_reuse_f_legacy_output(tmp_path):
    rewriter = Responder(
        "rw",
        lambda _m, request: text_reply("FORGE-ENHANCED" if request.system else "GENERIC")(
            _m, request
        ),
    )
    target = Responder("tg", text_reply(GOOD_ANSWER))
    run(tmp_path, make_router(rewriter, target))
    prompts = [call.request.messages[0].content for call in target.calls]
    assert prompts[1:] == ["GENERIC", "FORGE-ENHANCED"]


def test_condition_descriptions_are_distinct_and_hashed():
    b1, forge = CONDITIONS["B1"].transform, CONDITIONS["F-legacy"].transform
    assert request_template_sha256(b1.build) != request_template_sha256(forge.build)
    assert request_template_sha256(b1.build) == request_template_sha256(conditions.b1_request)
    assert CONDITIONS["B0"].describe()["transform"] is None
    assert asdict(conditions.B1_PARAMS) == asdict(legacy.LEGACY_PARAMS)  # documented choice


def test_condition_selection_order_and_validation():
    assert [c.id for c in get_conditions(("F-legacy", "B0"))] == ["B0", "F-legacy"]
    with pytest.raises(ValueError, match="unknown"):
        get_conditions(("B2",))
    with pytest.raises(ValueError, match="repeat"):
        get_conditions(("B0", "B0"))


class TestFLegacyVersusEnhanceRoute:
    """F-legacy reproduces /enhance with stream=false, not the streaming path the web UI
    uses (which returns raw output without clean_output); the manifest says so."""

    RAW = "[ENHANCED PROMPT]:\nAct as a careful analyst.\n━━━━━━━━\n"

    def client(self):
        router = ProviderRouter(
            load_providers_config(),
            adapters={"gemini": FakeAdapter("gemini", default=FakeResponse((self.RAW,)))},
            sleep=lambda _s: None,
        )
        return create_app(Settings(), router=router).test_client()

    def test_benchmark_cleanup_matches_the_json_path_only(self):
        client = self.client()
        json_prompt = client.post("/enhance", json={"prompt": "p", "stream": False}).get_json()[
            "enhanced_prompt"
        ]
        streamed = "".join(
            json.loads(line[len("data: ") :]).get("chunk", "")
            for line in client.post("/enhance", json={"prompt": "p", "stream": True})
            .get_data(as_text=True)
            .splitlines()
            if line.startswith("data: ")
        )
        benchmark_prompt = CONDITIONS["F-legacy"].transform.postprocess(self.RAW)
        assert benchmark_prompt == json_prompt == "Act as a careful analyst."
        assert streamed == self.RAW != benchmark_prompt  # the UI path is not reproduced

    def test_web_ui_uses_the_streaming_path(self):
        page = (REPO_ROOT / "src" / "forge" / "templates" / "index.html").read_text(
            encoding="utf-8"
        )
        assert "stream: true" in page

    def test_manifest_records_the_deviations(self):
        details = CONDITIONS["F-legacy"].describe()["transform"]
        assert "stream=false" in details["matches"]
        assert "stream=true" in details["user_facing_path"]
        assert "without clean_output" in details["user_facing_path"]
        assert "transport" in details and "on_failure" in details
