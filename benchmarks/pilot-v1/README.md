# Pilot dataset `forge-pilot` 1.0.0

Current dataset for the FORGE 2.0 Phase 0 pilot benchmark. Protocol, conditions, metrics
and run format: [`docs/benchmark/pilot-protocol.md`](../../docs/benchmark/pilot-protocol.md).
The previous version, 0.1.0 (`../pilot-v0`), is kept unchanged so runs made with it remain
verifiable; verify a run against the dataset version recorded in its manifest.

| File | Content |
|---|---|
| `dataset.json` | id, version, description, task file name |
| `tasks.jsonl` | one task per line (schema: `forge.benchmark.dataset.Task`) |
| `offline-providers.json` | fake providers with fixed fixture text, for offline runs only (identical to 0.1.0's) |

Distribution (unchanged from 0.1.0): coding 5, writing 5, structured output 5,
summarization 3, data analysis 3, reasoning 3, agent/tool use 3, retrieval 3 ·
well-specified 11, partially specified 11, vague 8 · dev 20, held-out 10 · 67 checks.

## Changes from 0.1.0

0.1.0 let a one-word answer ("ok") fully pass six tasks whose checks were all upper bounds,
and let trivially structured answers ("- ok" bullets, numbered "ok" items, three "ok" lines)
pass several more. 1.0.0 revises 16 tasks (task `version` 2) by stating a checkable minimum or
content requirement in the prompt itself, grounded in the original intent. The other 14
tasks are byte-identical to 0.1.0.

| Task | Change |
|---|---|
| `pilot-003` | at least 3 possible causes as bullet points; mention of the config file |
| `pilot-004` | the answer names both "list" and "tuple" (from "a list and a tuple") |
| `pilot-007` | the haiku uses the word "rain" |
| `pilot-008` | 40 to 120 words, starting with a "Subject:" line |
| `pilot-010` | 40 to 100 words |
| `pilot-011` | 15 to 40 words, mentions chlorophyll |
| `pilot-012` | at least 3 bullets, keeping the names and days mentioned (Maria, Thursday) |
| `pilot-013` | at least 10 words in at most two lines, mentions the sample size |
| `pilot-015` | 15 to 50 words, refers to at least two different years |
| `pilot-016` | at least 2 bullets, citing the numbers |
| `pilot-017` | 2 or 3 numbered steps (was "at most 3", which zero steps satisfied) |
| `pilot-019` | 30 to 80 words, starting with "Recommendation: Rust" or "Recommendation: Go" |
| `pilot-026` | a numbered list of 3 to 6 steps that mentions Friday |
| `pilot-027` | each tool as "Tool: what it does" |
| `pilot-029` | quotes the relevant sentence from the notes in double quotes |
| `pilot-030` | the 3 bullets include the prices |

A test enforces that no task (unless marked `limited_reason`, which none is) is fully passed
by any trivial answer from a fixed list, and that each revised task accepts a plausible
answer. These checks still test format, required content and length — not correctness or
quality. Results remain INCONCLUSIVE.

## Authoring rules

- IDs are stable; never reuse one for a different task. Any change to a task bumps its
  `version` and the dataset's version.
- Every check's `requirement` is a verbatim phrase of the task's own prompt (enforced at
  load time). Checks test what the prompt explicitly asks for, never answer correctness.
- A task whose checks cannot separate a substantive answer from a trivial one without
  subjective grading sets `limited_reason`; it is then excluded from "all checks passed".
- `notes` and `limited_reason` are for humans and are never sent to any condition.
- Do not tune tasks or prompts on the `heldout` split.

```bash
forge benchmark validate-dataset benchmarks/pilot-v1
```

No real model has been benchmarked on this dataset.
