# Pilot dataset `forge-pilot` 0.1.0

30 hand-written tasks for the FORGE 2.0 Phase 0 pilot benchmark. Protocol, conditions,
metrics and run format: [`docs/benchmark/pilot-protocol.md`](../../docs/benchmark/pilot-protocol.md).

| File | Content |
|---|---|
| `dataset.json` | id, version, description, task file name |
| `tasks.jsonl` | one task per line (schema: `forge.benchmark.dataset.Task`) |
| `offline-providers.json` | fake providers with fixed fixture text, for offline runs only |

Distribution: coding 5, writing 5, structured output 5, summarization 3, data analysis 3,
reasoning 3, agent/tool use 3, retrieval 3 · well-specified 11, partially specified 11, vague 8
· dev 20, held-out 10 · 50 deterministic checks.

## Authoring rules

- IDs are stable; never reuse one for a different task. Any change to a task bumps its
  `version` and the dataset's version.
- Every check's `requirement` is a verbatim phrase of the task's own prompt (enforced at
  load time). Checks test what the prompt explicitly asks for — format, required content,
  length — never answer correctness or quality.
- `notes` are for humans and are never sent to any condition.
- Do not tune tasks or prompts on the `heldout` split.

## Use

```bash
forge benchmark validate-dataset benchmarks/pilot-v0
```

Results from fake providers are synthetic and validate only the harness. No real model has
been benchmarked on this dataset yet.
