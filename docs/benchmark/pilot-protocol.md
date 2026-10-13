# FORGE pilot benchmark — protocol `forge-pilot` v1

Status: **implemented and validated offline (fake providers only).** No real model has been
benchmarked. Every result produced under this protocol is interpreted as **INCONCLUSIVE**.

Code: `src/forge/benchmark/`. Datasets: `benchmarks/pilot-v1/` (`forge-pilot` 1.0.0, current)
and `benchmarks/pilot-v0/` (0.1.0, kept unchanged so runs made with it stay verifiable).
Command: `forge benchmark` (`python -m forge benchmark` without installing the console
script). Every run's manifest records the dataset id, version and hash it used.

## 1. Purpose and limitations

Purpose: a reproducible harness that runs the same tasks under three conditions, records
every call and output, and applies deterministic checks — to validate the evaluation
pipeline and surface implementation or evaluation problems before larger benchmarks.

It does **not** show that any condition (including FORGE) is better:

- 30 tasks is a pilot (spec §18); no statistical claim is attempted.
- L0 checks cover format, required content and length only. They do not judge correctness,
  usefulness, faithfulness, style or overall quality, and there is no LLM judge, human
  rating or semantic score. Several pilot tasks state this in their `notes`.
- In 0.1.0, six tasks had only upper-bound checks, so a one-word answer such as "ok" passed
  them completely. 1.0.0 revises them (§2); still, passing checks shows format, content and
  length adherence, not quality.
- One sample per task and condition; target temperature 0 where the provider honours it.
- Fake-provider runs produce fixture text: they test the harness and are labelled
  `measurement: offline_fixture` / "SYNTHETIC". They are never measurements.

## 2. Datasets

Both versions: 30 tasks with the same stable IDs, categories (coding 5, writing 5,
structured output 5, summarization 3, data analysis 3, reasoning 3, agent/tool use 3,
retrieval 3), specification levels (well 11 / partial 11 / vague 8) and splits (dev 20 /
held-out 10). Each directory has `dataset.json` (id, semantic version, description, task
file), `tasks.jsonl` (one task per line), `offline-providers.json` and a README.

| Version | Directory | Checks | Notes |
|---|---|---|---|
| 0.1.0 | `benchmarks/pilot-v0` | 50 | Preserved byte for byte. `pilot-003`, `-011`, `-013`, `-015`, `-019`, `-029` have only upper-bound checks and are fully passed by "ok"; `-004`, `-007`, `-012`, `-016`, `-017`, `-026`, `-027`, `-030` are fully passed by trivially structured answers (e.g. three `- ok` bullets); `-008` and `-010` by short keyword-only answers |
| 1.0.0 | `benchmarks/pilot-v1` | 67 | 16 tasks revised (task `version` 2): each prompt now states a checkable minimum or content requirement grounded in its original intent (e.g. "in 15 to 40 words and mention chlorophyll", "at least 3 possible causes as bullet points", "starting with 'Recommendation: Rust' or 'Recommendation: Go'"). The other 14 tasks are byte-identical to 0.1.0 |

**Trivial-answer rule (1.0.0).** No task may be fully passed by any of: the empty string,
`ok`, `OK.`, `x`, `- ok`, `1. ok`, three lines of `ok`, three `- ok` bullets, three numbered
`ok` items, or `Answer: ok` (enforced by a test). A task whose checks cannot meet this without
subjective grading must set `limited_reason`; it is then excluded — with its reason and a
separate count — from "all checks passed" metrics and paired comparisons. No 1.0.0 task
needed it. Passing the rule does not make the checks a test of semantic correctness.

Task fields (strictly validated; unknown fields, type coercion and duplicate JSON keys are
rejected): `id` (stable, `^[a-z0-9][a-z0-9-]{2,63}$`, unique), `version` (integer, bump on any
change), `category`, `spec_level`, `split`, `prompt`, `checks` (≥ 1), optional `notes` and
`limited_reason` (neither is ever sent to any condition; `limited_reason` is omitted from the
hashed definition when unset, so 0.1.0 hashes are unchanged).

**Fairness rule:** every check has a `requirement` that must appear verbatim
(case-insensitively) in the task's own prompt. A task whose check is not traceable to its
prompt is rejected at load time, so no condition can be scored against a requirement it was
not given.

Hashes (SHA-256 over canonical JSON — sorted keys, no insignificant whitespace, UTF-8, NaN
rejected; `forge.infrastructure.cache.canonical_json`):

| Hash | Input | Purpose |
|---|---|---|
| `task_sha256` | the validated task definition | identifies exactly what was asked and how it is checked |
| `dataset_sha256` | `{id, version, tasks: [{id, sha256}] sorted by id}` | identifies the dataset version's content |
| `manifest_sha256` | the canonical manifest (§6) | identifies the whole run configuration |
| `request_sha256` | the adapter's `cache_identity` (endpoint, model, messages, parameters — never credentials) | identifies each model request |
| `output_sha256`, `*_prompt_sha256` | UTF-8 text | detect edits to stored text |

## 3. Conditions

All three receive only the task's `prompt` string. The target model is then called the same
way for every condition: the resulting prompt as a single user message, no system prompt,
`temperature 0`, `max_output_tokens 2048`.

| ID | Prompt sent to the target |
|---|---|
| **B0** raw baseline | the task prompt, byte-for-byte unchanged |
| **B1** generic rewrite | output of one rewrite call using a benchmark-specific template (below), stripped of surrounding whitespace |
| **F-legacy** FORGE 1.x | output of `forge.legacy.enhance.build_request(prompt)` (unchanged FORGE system prompt, prompt builder and parameters), cleaned by `forge.legacy.enhance.clean_output` — as the `/enhance` JSON path (`stream: false`) does |

B1 template (version 1): *"Rewrite the prompt below so that it is clear, specific and
effective for a large language model. Keep its intent, its language and every requirement or
constraint it states, and do not add new requirements. Return only the rewritten prompt, with
no commentary."* followed by the prompt. B1 uses the same generation parameters as F-legacy
(temperature 0.5, top-p 0.85, 1280 output tokens) so the comparison isolates the
instruction. B1 does not call or import-use the FORGE enhancer (tested). It is a simple
single-shot baseline, not a tuned competitor.

B1 and F-legacy use the same rewriter model profile.

**F-legacy is not the path web-UI users get.** `/enhance` has two response paths:

| Path | Used by | Output |
|---|---|---|
| `stream: true` (default) | the web UI (`index.html` sends `stream: true`) | raw model output, streamed; **no `clean_output`** |
| `stream: false` | JSON clients | `clean_output` applied (`enhanced_prompt`) |

F-legacy reproduces the `stream: false` request and cleanup only. It also differs from both
paths in transport and failure handling: it calls `router.generate` (non-streaming; the
route streams internally on both paths) so budget and cache apply to every condition alike,
and a failed enhancement is a failed record rather than `"Error: ..."` text passed on as a
prompt. The manifest records all of this (`matches`, `user_facing_path`, `transport`,
`on_failure`). Results therefore say nothing direct about the streamed output users see.

An empty rewrite (after post-processing) is a `failed` record (`empty_transform_output`); the
target is not called with an empty prompt.

## 4. Records (`results.jsonl`)

Exactly one record per selected task × condition, in protocol order (tasks by ID; B0, B1,
F-legacy):

| Field | Meaning |
|---|---|
| `status` | `evaluated` (target output obtained, checks ran), `failed` (a call failed or the rewrite was empty; no checks), `not_run` (the run stopped first) |
| `reason` | null, or `provider_error`, `empty_transform_output` (failed); `budget_exceeded`, `cancelled`, `run_not_active`, `database_error`, `persistence_failed`, `internal_error` (not_run) |
| `task_sha256`, `task_prompt_sha256` | the task as asked |
| `target_prompt`, `target_prompt_sha256` | the transformed prompt (null for B0, whose target prompt is the task prompt) |
| `executions[]` | each `router.generate` call: role (`generator` = rewrite, `target`), profile, provider, provider type, requested/reported model, effective parameters, `request_sha256`, status, raw output text + hash, finish reason, latency, `cache_hit`, error category, `attempts`, `usage`, `replayed_usage`, `budget_tokens` (see §6) |
| `evaluation` | evaluator `forge.l0` v1: per-check `passed`, `observed` value, `detail`; `checks_passed`, `checks_total`, `passed_all`, `empty_output` |

Calls that happened before a run stopped are kept in the `not_run` record. Record format 2
(`record_version: 2`) adds `attempts`, `replayed_usage` and `budget_tokens`; format-1 records
(runs made before the Step 6 acceptance fixes) parse without them.

## 5. Deterministic evaluation (`forge.l0` v1)

Rules (`src/forge/benchmark/checks.py`) on `text = output.strip()`:

| Check | Passes when |
|---|---|
| empty output | never: if `text == ""` every check fails with `empty_output` |
| `word_count` | `len(re.findall(r"\S+", text))` is within [min, max] |
| `char_count` | `len(text)` (code points) is within [min, max] |
| `line_count` | the number of lines containing a non-whitespace character is within [min, max] |
| `list_items` | lines matching a bullet `^\s*[-*•]\s+\S` and/or numbered item `^\s*\d+[.)]\s+\S` (`style` any/bullet/numbered) are within [min, max] |
| `contains` / `not_contains` | the text is (not) a substring, case-folded unless `case_sensitive` |
| `regex` | `re.search(pattern, text, flags)` matches (`IGNORECASE`, `MULTILINE`, `DOTALL`) |
| `json` | `json.loads` succeeds (NaN/Infinity rejected); object with `required_keys`, or array with length in [min_items, max_items]; one surrounding code fence is removed only if `allow_fence` |
| `code_block` | at least `min_blocks` fenced blocks; with `language`, the fence's first info word matches case-insensitively |

Bounds are inclusive. Counts include text inside code blocks. Recomputing an evaluation from
the stored output always gives the stored result (`verify` checks this).

## 6. Metrics, accounting and interpretation

Computed only from the records (`records.aggregate`), per condition, always with the number
of selected tasks (`N`) or defined checks as denominator:

- records `evaluated` / `failed` / `not_run` / `missing` (of N), failure reasons;
- empty outputs (of N);
- tasks with all checks passed — of the tasks **not** marked limited, also per
  specification level; limited tasks are counted separately and listed with their reasons;
- checks `passed` / `failed` / `not_evaluated` (of all defined checks; checks of failed or
  not-run records count as not evaluated), also per check type.

Accounting terms, kept distinct:

| Term | Meaning | Where |
|---|---|---|
| condition result | one record per task × condition (the logical evaluation unit) | `accounting.condition_results`; 90 for a full 30-task run |
| execution | one `router.generate` call (a rewrite or a target call) | `accounting.executions` |
| provider attempt | a request handed to the provider adapter after the run budget reserved a unit for it; each retry is one; cache hits and refusals before dispatch (unsupported capability, no concurrency slot, budget refused) are 0 | per execution `attempts`; `accounting.provider_attempts`; run-level `run_accounting.provider_attempts_recorded` vs `provider_attempts_budget` (the budget counter; a difference means attempts by calls interrupted before they could be recorded) |
| cache hit | an execution served from the response cache: no attempt, no budget unit | `accounting.cache_hits` |
| provider-reported tokens | usage the provider reported for a fresh execution | `tokens.provider_reported_input` / `_output` |
| budget tokens | what the run budget charged per attempt: provider-reported or locally estimated | per execution `budget_tokens`; `tokens.budget_charged_provider_reported` / `_estimated` |

A cache hit's `usage` is `{"source": "cache"}` with no counts; the original response's usage
is kept in `replayed_usage` and never added to totals. Provider attempts are not billing
records: whether an attempt is billed (e.g. a rate-limited or timed-out request) depends on
the provider and is not known to FORGE. Format-1 runs did not record attempts; their
accounting is "unavailable", never estimated from execution counts.

On the normal path (every call succeeds on its first attempt, cache disabled) a task needs 5
provider attempts — B0: 1 target call; B1 and F-legacy: 1 rewrite + 1 target call each — so
a full 30-task run is 90 condition results, 150 executions and 150 provider attempts. Retries
add attempts (at most `retry.max_attempts` per execution); a failed or empty rewrite skips
its target call; cache hits (only with a shared `--cache-scope`) make no attempts.

Paired L0 check counts (A vs B: tasks where A passed more checks / equal / B more; tasks not
evaluated under both, and limited tasks, are excluded and counted) are diagnostics, not
preferences.

`interpretation` is the constant `INCONCLUSIVE` in `run.json`, `summary.json` and
`summary.md`; `verify` rejects any other value. Read it as: the harness ran and these
deterministic diagnostics were observed; nothing follows about which condition is better.

## 7. Run artefacts and persistence

`<output-dir>/<run-id>/` (default `benchmark-runs/`, git-ignored):

| File | Content |
|---|---|
| `manifest.json` | canonical manifest bytes (hash = `manifest_sha256`): protocol, FORGE version, dataset id/version/hash, selected tasks with hashes, conditions (template hashes, parameters, recorded deviations), target/rewriter profiles (provider, type, model, parameters), samples per case, evaluator. No run ID, timestamps, budget, cache settings, credentials, environment variable names or base URLs |
| `run.json` | run ID, status (`running`, `finalizing`, then a terminal status), interpretation, measurement (`offline_fixture` if any fake provider), manifest hash, created/finished timestamps (ISO 8601 UTC, milliseconds, `Z`), budget limits and usage, cache settings, persistence status per store, expected/written record counts, `results_sha256`, stop reason, failure |
| `results.jsonl` | records (§4), appended and fsynced one by one |
| `summary.json` / `summary.md` | `summary_version` 2: terminal status, run accounting and aggregates (§6); Markdown rendered from it with the INCONCLUSIVE (and SYNTHETIC) banners |

With `--database` (PostgreSQL at the migration head), the run also uses existing tables — no
schema change: one `runs` row (manifest JSONB, `manifest_hash`, status, budget limits and
counters), one `executions` row per model call (`system` = condition, `role`, raw output,
usage, latency, `cache_hit`, error category), and one `evaluations` row per evaluated target
output (`forge.l0` / `1`, check results, `passed`). `not_run`/`failed` pairs without calls
have no rows; they are derivable from the manifest and are present in `results.jsonl`.
Cache-hit `executions` rows store no token counts and `usage_source = 'unknown'` (the column
allows only provider/estimated/unknown), so summing `input_tokens`/`output_tokens` over
executions counts only fresh provider-reported usage; `cache_hit` identifies replays.

**Completion and failure semantics.** A run is `completed` only when every task × condition
has an `evaluated` or `failed` record **and** every persistence step succeeded. Otherwise:
`budget_exceeded`, `cancelled`, or `failed` (database error, persistence failure, internal
error). If writing a record to one store fails, the run stops, the remaining pairs become
`not_run` (`persistence_failed`), and the affected record is kept in the files as `not_run`.

Finalization never writes `completed` before every earlier step succeeded, and the file
commit comes last:

1. `run.json` → `finalizing` (records are final; the run is explicitly not complete);
2. database run → terminal status (failure makes the run `failed`);
3. `summary.json` / `summary.md` with that same status;
4. `run.json` → terminal status (the commit point).

If a file step fails after the database recorded `completed`, the database is set to
`failed`; if the summary already stated a status that is no longer true, it is rewritten.
These corrections are best effort: **filesystem and database are not updated atomically.** If
a correction fails, the run is returned with `consistent: false`, logged as
`benchmark.finalization_inconsistent`, and the CLI exits non-zero; `run.json` then stays
`finalizing` or `failed` and never says `completed`. The database alone may in that case
still say `completed` — `forge benchmark verify --database` detects it. A process crash
leaves `running` or `finalizing`.

`forge benchmark verify` reports any run that is not provably complete — `run.json` not
`completed`, missing or `not_run` records, hash mismatches, inconsistent records,
evaluations that do not recompute from the stored outputs, a summary that does not match the
records or states a different status, or (format 2) cache hits with attempts or usage and
recorded attempts that disagree with the budget. With `--database` it also compares the run
row's status, manifest hash and execution count with the files. Format-1 runs are verified
with the frozen v1 aggregation (`forge.benchmark.legacy_formats`); verify a run against the
dataset version recorded in its manifest. Recovery: keep the directory for audit and start a
new run; runs are never resumed or overwritten.

**Retention.** Task prompts are public dataset content. Transformed prompts and model
outputs are stored in full in `results.jsonl` and `executions.output_text` so a run can be
audited; nothing is deleted automatically. Logs (`benchmark.started`, `benchmark.record`,
`benchmark.finished`) contain IDs, statuses and reasons only — never prompts, outputs or
credentials.

## 8. Budget, cache, cancellation

- Every run needs `--max-model-calls`. Before anything runs, the plan
  (tasks × calls per task: B0 1, B1 2, F-legacy 2) is checked: a budget below the minimum is
  rejected, and a worst case (× retry attempts) above `--confirm-above-model-calls` needs
  `--confirm`. During the run every attempt is reserved through the Step 5 budget guard
  (PostgreSQL with `--database`, in memory otherwise); exhaustion stops the run as
  `budget_exceeded` with the remaining pairs `not_run`.
- Cache (`--cache`, PostgreSQL only): the namespace is
  `{benchmark, protocol_version, cache_scope, condition, task_id, task_sha256, role,
  sample_index}`, so entries are never shared between conditions, tasks or roles even when
  the requests are identical. `cache_scope` defaults to the run ID (no reuse across runs);
  passing the same `--cache-scope` to several runs replays outputs, flagged `cache_hit` and
  counted separately — never as provider attempts or new usage.
- Cancellation: before each task × condition the runner checks the caller's stop signal
  (`BenchmarkRunner(should_stop=...)`) and, with a database, the run row's status; a run set
  to `cancelled` (or any status other than `pending`/`running`) stops scheduling work, and
  the budget guard refuses further calls for it. Ctrl-C while a task is executing finalizes
  the run as `cancelled` (exit code 130). Cancellation takes effect between tasks; a call
  already in flight completes.

## 9. Running the pilot offline (safe)

```bash
forge benchmark validate-dataset benchmarks/pilot-v1
forge benchmark run --dataset benchmarks/pilot-v1 --providers benchmarks/pilot-v1/offline-providers.json --target-model offline-target --rewriter-model offline-rewriter --max-model-calls 150
forge benchmark verify benchmark-runs/<run-id> --dataset benchmarks/pilot-v1
```

A run made with `pilot-v0` is verified with `--dataset benchmarks/pilot-v0`; verifying a run
against a different dataset version fails (task hashes differ).

`offline-providers.json` defines only `fake` providers returning fixed fixture text, so every
condition gets the same synthetic output: the numbers validate the harness, not FORGE. Add
`--database` (with `DATABASE_URL` at the migration head) to persist to PostgreSQL.

Providers of any other type are refused unless `--allow-real-providers` is given. Running
the pilot against a real model is increment 7 and requires the owner's explicit approval.

## 10. Verification status

See [`feature-status.md`](../implementation/feature-status.md) and the Phase 0 plan's
increment 6 log (including the acceptance fixes) for what was run (offline suite, PostgreSQL 18.6 integration tests) and what
was not (real providers, PostgreSQL 17 after Step 6, Docker/Gunicorn, GitHub Actions).
