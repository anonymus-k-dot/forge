"""The three pilot conditions. Each receives only the task's ``prompt`` string — never its
checks, notes, category or other metadata — and produces the prompt sent to the target
model, which is called identically (``target_request``) for every condition.

    B0        raw baseline: the task prompt, byte-for-byte unchanged
    B1        generic rewrite: one call with ``B1_TEMPLATE`` (written for this benchmark,
              independent of FORGE), output stripped of surrounding whitespace
    F-legacy  FORGE 1.x enhancement: ``forge.legacy.enhance.build_request`` (unchanged system
              prompt, builder and parameters) followed by ``clean_output``. This matches the
              ``/enhance`` *non-streaming* JSON path (``stream: false``). It is not the path
              users of the web UI get: the UI calls ``/enhance`` with ``stream: true``,
              which returns the raw model output with no ``clean_output`` step. Further
              differences from ``/enhance``: the call goes through ``router.generate``
              (non-streaming) so budget and cache apply uniformly, and a failure is
              recorded as a failure instead of being returned as ``"Error: ..."`` text. All
              three differences are recorded in the manifest (``user_facing_path``,
              ``transport``, ``on_failure``).

B1 deliberately uses the same generation parameters as F-legacy so the comparison isolates
the rewriting instruction. It is a simple single-shot baseline, not a tuned competitor.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from forge.infrastructure.cache import canonical_json
from forge.legacy import enhance as legacy
from forge.providers.base import GenerationParams, GenerationRequest

CONDITION_IDS = ("B0", "B1", "F-legacy")
TEMPLATE_PLACEHOLDER = "<<TASK_PROMPT>>"

B1_TEMPLATE_VERSION = 1
B1_TEMPLATE = (
    "Rewrite the prompt below so that it is clear, specific and effective for a large "
    "language model. Keep its intent, its language and every requirement or constraint it "
    "states, and do not add new requirements. Return only the rewritten prompt, with no "
    "commentary.\n\nPrompt:\n" + TEMPLATE_PLACEHOLDER
)
B1_PARAMS = GenerationParams(temperature=0.5, top_p=0.85, max_output_tokens=1280)

# The target model sees only the (possibly transformed) prompt as a single user message.
TARGET_PARAMS = GenerationParams(temperature=0.0, max_output_tokens=2048)


def b1_request(task_prompt: str) -> GenerationRequest:
    return GenerationRequest.from_prompt(
        B1_TEMPLATE.replace(TEMPLATE_PLACEHOLDER, task_prompt), params=B1_PARAMS
    )


def b1_postprocess(output: str) -> str:
    return output.strip()


def f_legacy_request(task_prompt: str) -> GenerationRequest:
    return legacy.build_request(task_prompt)


def f_legacy_postprocess(output: str) -> str:
    return legacy.clean_output(output)


def target_request(prompt: str) -> GenerationRequest:
    return GenerationRequest.from_prompt(prompt, params=TARGET_PARAMS)


@dataclass(frozen=True)
class Transform:
    kind: str
    build: Callable[[str], GenerationRequest]
    postprocess: Callable[[str], str]
    details: dict[str, Any]

    def describe(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "request_template_sha256": request_template_sha256(self.build),
            **self.details,
        }


@dataclass(frozen=True)
class Condition:
    id: str
    description: str
    transform: Transform | None  # None: the task prompt goes to the target unchanged

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "transform": None if self.transform is None else self.transform.describe(),
        }


def request_document(request: GenerationRequest) -> dict[str, Any]:
    return {
        "system": request.system,
        "messages": [asdict(m) for m in request.messages],
        "params": asdict(request.params),
    }


def request_template_sha256(build: Callable[[str], GenerationRequest]) -> str:
    """Hash of the request a transform builds around a placeholder task prompt: changes
    whenever its instructions, system prompt or parameters change."""
    document = request_document(build(TEMPLATE_PLACEHOLDER))
    return hashlib.sha256(canonical_json(document)).hexdigest()


CONDITIONS: dict[str, Condition] = {
    "B0": Condition("B0", "Raw task prompt, unchanged.", None),
    "B1": Condition(
        "B1",
        "Generic single-shot rewrite with a benchmark-specific template (not FORGE).",
        Transform(
            "generic_rewrite",
            b1_request,
            b1_postprocess,
            {"template_version": B1_TEMPLATE_VERSION, "postprocess": "strip"},
        ),
    ),
    "F-legacy": Condition(
        "F-legacy",
        "FORGE 1.x enhancement: forge.legacy.enhance request builder and output cleaner.",
        Transform(
            "forge_legacy",
            f_legacy_request,
            f_legacy_postprocess,
            {
                "source": "forge.legacy.enhance.build_request",
                "postprocess": "forge.legacy.enhance.clean_output",
                "matches": "/enhance with stream=false (JSON response, cleaned output)",
                "user_facing_path": (
                    "the web UI calls /enhance with stream=true, which returns raw model "
                    "output without clean_output; this benchmark does not reproduce it"
                ),
                "transport": "non-streaming router.generate (the /enhance route streams "
                "internally on both paths)",
                "on_failure": "recorded as a failed execution (the /enhance route returns "
                '"Error: ..." text)',
            },
        ),
    ),
}


def get_conditions(ids: tuple[str, ...]) -> tuple[Condition, ...]:
    unknown = [c for c in ids if c not in CONDITIONS]
    if unknown:
        raise ValueError(f"unknown condition(s): {unknown}")
    if len(set(ids)) != len(ids):
        raise ValueError("conditions must not repeat")
    # Fixed protocol order, independent of how they were requested.
    return tuple(CONDITIONS[c] for c in CONDITION_IDS if c in ids)
