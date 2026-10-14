# Step 7 — Real-model pilot: experimental protocol

| | |
|---|---|
| Protocol | `forge-step7-pilot` **1.1.0** (preregistered before any real output was seen) |
| Revision | 1.1.0 (2026-10-14, still before any real output): fail-closed cost and token checks, separate owner checks for account tier, rate limits, data use and thinking, the `run --experiment` gate, experiment identity checks in analysis, key stored outside the rater folder, provider facts from public sources (§6). Outcomes, conditions, rubric and analysis plan are unchanged from 1.0.0 |
| Experiment configs | [`step7-pilot-v1.json`](../../benchmarks/experiments/step7-pilot-v1.json) (pilot) and [`step7-smoke-v1.json`](../../benchmarks/experiments/step7-smoke-v1.json) (one-task smoke test), both `live_execution_approved: false` with every owner check unset |
| Dataset | `benchmarks/pilot-v1`, `forge-pilot` 1.0.0, SHA-256 `843226339e0d27417822e5ac0bf0b87ab8e54805165f98282af5d252baa578a2` |
| Harness | Step 6 benchmark (`docs/benchmark/pilot-protocol.md`), unchanged except optional pacing |
| Status | **Designed and validated offline. No real model has been called; nothing has been sent to any provider.** |
| Interpretation | **INCONCLUSIVE** until the rated pilot is complete — and, for a pilot of this size, afterwards as well (§5) |

**Authorization boundary.** Nothing in this document, the config, an API key in `.env`, or
the `--allow-real-providers` flag authorizes a real-provider call. A one-task smoke test and
the full pilot each require the owner's explicit approval naming the provider/model, the
dataset, the maximum request and token budget, and the cost ceiling (§10). The CLI
refuses real providers unless the run is made from an experiment config whose offline
preflight passes (§7).

## 1. Research question and outcomes

**Question.** Does FORGE's legacy prompt enhancement (F-legacy) lead to better downstream
answers from a target model than (1) sending the task prompt unchanged (B0) and (2) a
generic single-shot rewrite (B1)?

| Outcome | Definition | Role |
|---|---|---|
| **Primary** | Blinded human **task success** score, 0–3 (rubric §4.2), per task and condition | F-legacy vs B0 is the **primary comparison** |
| Secondary 1 | Same score, F-legacy vs B1 | secondary comparison |
| Secondary 2 | Instruction adherence 0–2; factual-error and unsupported-claim flags (per condition, rated items) | descriptive |
| Secondary 3 | L0 "all checks passed" (Step 6 deterministic checks), paired 2×2 per comparison | descriptive |
| Secondary 4 | Condition failures (no usable answer) and infrastructure failures per condition | descriptive |
| Secondary 5 | Provider-reported tokens (rewrite and target) and median target latency per condition | cost/overhead, descriptive |
| Exploratory | B1 vs B0 on the primary score | no claim |

These are fixed now. They will not be changed after outputs are seen; any later analysis is
labelled exploratory.

## 2. Design

### 2.1 Unit, dataset and conditions

- **Unit:** one task of `pilot-v1`, answered under all three conditions → 30 tasks × 3 =
  **90 condition results**; analysis is paired by task.
- **Dataset:** `pilot-v1` only (never mixed with `pilot-v0`). Suitability review:
  - 30 tasks, 8 categories, specification levels well 11 / partial 11 / vague 8, both
    splits used (no tuning is done, so held-out data is not at risk).
  - Prompts are synthetic, English, and contain no personal, confidential or proprietary
    data (the people and companies are fictional; the e-mail address uses the reserved
    `.example` domain).
  - 20 tasks have objective reference facts (rater notes, §4.3); 10 are open-ended.
  - Caveat: 1.0.0 added explicit checkable constraints to several "vague" tasks, so they are
    less underspecified than their label suggests; results by specification level are
    descriptive only.
  - Pilot-sized: it can show problems and rough magnitudes, not general effects.
- **Conditions** (Step 6 definitions, unchanged):
  - **B0** — the task prompt unchanged.
  - **B1** — one generic rewrite (benchmark template, temperature 0.5, top-p 0.85, 1280
    tokens), stripped.
  - **F-legacy** — `forge.legacy.enhance.build_request` + `clean_output`. This matches
    `/enhance` with `stream: false`; the web UI's streamed, uncleaned output is **not**
    reproduced (recorded in every manifest).
- **Equal information:** every condition receives only the task prompt; checks, notes,
  rater notes and labels are never sent.

### 2.2 Target-model control

All conditions call **one target profile** (`step7-target`) with identical request
parameters: temperature 0, no top-p override, no seed, 2048 output tokens, no system prompt,
no tools, no response-format constraint, the prompt as a single user message. The target
is never told which condition produced its input. The runner uses the same target profile
name for every target call; there is no per-condition routing, so B1/F-legacy cannot
silently use another model.
B1 and F-legacy share the rewriter profile (`step7-rewriter`). A run made with
`forge benchmark run --experiment` records the experiment ID, protocol, protocol version,
config hash and each role's effective endpoint (profile, provider, provider type, model and
`base_url`) in its manifest. Analysis refuses a run without that record, or whose record,
recorded endpoints, dataset ID/version/hash, conditions, target and rewriter profiles, the
provider, provider type and model behind each profile, any execution's role →
profile/model mapping, samples, cache or budget differ from the config and its providers
file.

**Endpoint identity.** A provider's endpoint is its `base_url` exactly as the providers
config stores it. That validator already rejects user info (credentials), query strings and
fragments and removes one trailing `/`; FORGE applies no other normalization, so scheme,
host-case, port or path differences count as different endpoints. `google_genai`
providers take no `base_url` (the google-genai SDK default endpoint) and are recorded as
`null` with their provider type. No credential, header or environment-variable value is
recorded; the providers config holds only the name of the key's environment variable.

### 2.3 Order, sampling, cache, retries

- **Order:** fixed and recorded — tasks by ID; within a task B0, then B1 (rewrite, target),
  then F-legacy (rewrite, target); sequential, one call at a time. Calls are stateless, so
  order cannot leak information; interleaving per task spreads any provider drift evenly
  across conditions.
- **Sampling:** one sample per task and condition, temperature 0 for the target. No output
  is ever re-run selectively. Repeated samples (e.g. 3 per task, 3× the cost) would estimate
  within-task variance; they are not proposed for this pilot.
- **Cache:** **disabled** (`cache: "disabled"` is the only value the config accepts). No
  cached output can enter the primary run; replay mode is not used.
- **Retries:** finite and uniform: `max_attempts` 2 per call (one retry, only for retryable
  errors: rate limit with a short Retry-After, 5xx, timeouts, connection errors), backoff
  2–30 s, Retry-After honoured up to 60 s. Every attempt is reserved through the Step 5
  budget; no condition is retried differently. The installed `google-genai` 1.2.0 SDK has
  no internal retry and `httpx` defaults to 0 transport retries, so FORGE's attempts are the
  attempts sent (the plan records SDK versions; `requirements.txt` allows newer
  `google-genai` versions, so pin it for the run — decision D7).
- **Pacing:** 5 s minimum between call starts (≤ 12 calls per minute) so that a free-tier
  rate limit does not become a recorded failure. The full run takes ≥ 745 s plus model time.
  The account's actual limits are not published and must be checked by the owner (§6 P5).
- **Thinking mode (not controlled):** Gemma 4 on the Gemini API can think before
  answering; the API switches this with `thinking_level`, whose default is not documented
  (§6 P8). The installed `google-genai` 1.2.0 does not offer that setting and the adapter
  sends none, so the provider default applies and is not pinned (no dependency change in
  this step). The adapter's token accounting uses the prompt and answer counts only, so
  thought tokens, if any, are not counted by the budget, and they may use up
  `max_output_tokens`, truncating an answer (an empty answer is a condition failure,
  §2.4). The smoke test records finish reasons and reported usage to observe this.

### 2.4 Failures (classified before outputs are seen)

| Outcome | Class | Primary score |
|---|---|---|
| Empty target answer, empty rewrite, provider `invalid_request` for the condition's own request | **condition failure** | **0** (counts against the condition) |
| Refusal or off-topic answer | rated by humans | 0 per rubric |
| Rate limit, timeout, unavailable, server error, malformed response, authentication, configuration, unsupported capability, unknown; pairs not run (budget exhausted, cancelled, persistence failure) | **infrastructure** | excluded, reported per condition |

A task with any infrastructure exclusion is dropped from **all** comparisons (one task set).
If more than **10%** of tasks (more than 3) are excluded, the run is invalid and is repeated
in full as a new run — never by re-running individual failures. An imbalance of
infrastructure failures between conditions is reported as a threat to validity.

## 3. Layer A — deterministic checks

The Step 6 L0 checks (`forge.l0` v1, 67 checks on `pilot-v1`) run on every target answer:
format, required content, length/structure, empty output. They are a secondary outcome.
Passing them does not mean the answer is correct; failing them can reflect a constraint
slip in an otherwise correct answer.

## 4. Layer B — blinded human evaluation (primary)

### 4.1 Procedure

1. After a verified, complete run: `forge benchmark export-blind RUN_DIR --experiment
   CONFIG --out RATER_DIR --key KEY_FILE` writes the rater folder — only `items.jsonl`
   (opaque 16-hex `item_id`, task ID, original task prompt, one answer) and
   `rating-template.jsonl` — and the key (item → condition, unrated outcomes) at a
   separate path. The key must lie outside the rater folder (refused otherwise) and is
   never overwritten.
2. Items are shuffled — tasks and the answers within each task — with the recorded seed
   (7301). Items contain no condition name, transformed prompt, model, profile, latency,
   usage or record order (tested).
3. **Never distribute the key to raters.** Give raters only the rater folder, the rubric
   and the rater notes — not the key, the run directory, the results or the config's
   seed. The key stays with the experimenter until all ratings are final. This is an
   access-separation safeguard, not cryptographic protection: anyone with the run
   directory, or the results and the seed, can recover the conditions.
4. Raters see the rubric (`benchmarks/evaluation/rubric-v1.json`) and the rater note for
   each task (`benchmarks/evaluation/pilot-v1-rater-notes.jsonl`, bound to each task's
   hash). Each answer is rated on an absolute scale, in the given order.
5. Ratings are JSON Lines matching `forge.benchmark.blinding.Rating`.

No LLM judge is used. An automated judge would be a separate instrument requiring its own
authorization, calibration against these human ratings, and validation; it is not part of
this protocol.

### 4.2 Rubric `forge-step7-answer-quality` 1.0.0 (summary; the JSON file is normative)

**task_success (primary, 0–3)** — does the answer accomplish what the task asks?

| Score | Anchor |
|---|---|
| 0 | Does not accomplish the task: wrong, off-topic, refused, or so incomplete or incorrect that the requester could not use it |
| 1 | Attempts it but has a major error or omission (incorrect key fact or result, central part missing); needs substantial correction |
| 2 | Accomplishes it with only minor problems (small inaccuracy that does not change the outcome, minor omission or constraint slip); usable with light editing |
| 3 | Fully accomplishes it: correct, complete for what was asked, within the stated constraints |

**instruction_adherence (0–2)**: 0 violates an explicit constraint in a way that matters,
1 minor slip, 2 follows every explicit constraint. **factual_error** (yes/no): a statement
false given the task's material or well-established knowledge. **unsupported_claim**
(yes/no): invented specifics, or outside information where the task restricts the source.

Anti-verbosity rules: length, headings, formatting and polish earn nothing by themselves;
unrequested content is neutral unless wrong or constraint-breaking; confident tone is not
evidence. Correctness is judged against the task's own material and the rater note.

### 4.3 Raters, disagreement, bias

- **Raters:** at least one; two independent raters are preferred (decision D5). A single
  rater is a stated limitation.
- **Disagreement:** task_success scores within 1 point → mean; 2+ points → adjudication
  (discussion or third rater), recorded as a rating with `"adjudicated": true`.
  instruction_adherence uses the same rule; factual/unsupported flags raised by any rater
  stand unless adjudicated. Unresolved disagreements leave the analysis incomplete.
- **Bias controls:** condition labels hidden; seeded shuffling of tasks and of answers
  within tasks; absolute anchors; rater notes fixed before outputs exist; no re-rating after
  unblinding. Residual risk: answers may carry stylistic traces of their prompt (F-legacy
  prompts ask for structure), which a rater could notice.
- **Missing outputs** are never shown to raters; they are scored by the §2.4 rules.

## 5. Statistical analysis plan (`forge benchmark analyze`, analysis v1)

- **Task set:** the tasks with a primary score under all three conditions; the same set for
  every comparison (tested).
- **Per comparison** (A − B, paired by task): number of tasks where A scored higher / tied /
  lower; mean scores; mean and median paired difference; a 95% percentile bootstrap
  interval for the mean difference (tasks resampled with replacement, 10,000 resamples,
  seed 7302).
- **Ties and missing data:** ties are counted, not split. Condition failures are 0;
  infrastructure exclusions are listed; unrated or unresolved items make the analysis
  incomplete (no estimates are reported).
- **No hypothesis tests or p-values.** Intervals are descriptive. ~30 tasks with one sample
  each are too few to separate modest differences from rater and model noise (no minimum
  detectable effect has been computed); the pilot cannot support claims of general
  superiority, effects per category or specification level, or effects on other models.
- **Multiplicity:** one primary comparison; the secondary comparison and all secondary
  outcomes are descriptive; B1 vs B0 is exploratory. No claim rests on a secondary or
  exploratory result.
- **Interpretation:** the report's interpretation is always `INCONCLUSIVE`. The pilot's
  purpose is to check the procedure and estimate effect size and variability for a
  properly sized follow-up.
- **Synthetic data:** `analyze` refuses runs made with fake providers; `--allow-synthetic`
  exists only to exercise the pipeline and labels the report SYNTHETIC (tested).

## 6. Provider and model selection (public sources only; no provider was contacted)

Sources were read on **2026-10-14** from public documentation. No account was logged in to,
no credential was read, and no account-specific quota or billing endpoint was queried. Each
item below is a **separate** check; published facts do not settle the account-specific
ones.

| # | Item | Published fact (source) | Status for this run |
|---|---|---|---|
| P1 | Model `gemma-4-31b-it` on the Gemini API | Listed as available, with `gemma-4-26b-a4b-it` [S1] | Published; whether the owner's key can use it is **not verified** (smoke test) |
| P2 | Limits and parameters | System instructions supported [S1]; 256K context stated for Gemma 4 generally; API output limits and sampling parameters not documented [S1] | Requests here use ≤ 2,048 output tokens and temperature 0 / 0.5: **not verified** until the smoke test |
| P3 | Pricing | Gemma 4: free of charge for input and output on the Free Tier; no Paid Tier offered [S2] | Published zero price recorded in the config with source, retrieval date, model and tier |
| P4 | Account tier and billing status | API access counts as a Paid Service only through a Cloud project with an active billing account [S4]; the pricing page does not say how Gemma is treated on a billing-enabled project [S2] | **Account-specific, not verified.** Published free-tier pricing does not show that the owner's API project qualifies. Owner confirms (`accounts[].tier_and_billing_status_confirmed`, one entry per real provider) |
| P5 | Rate limits (quota) | Not published for Gemma; limits are viewable in Google AI Studio, apply per project, and daily quotas reset at midnight Pacific [S3] | **Account-specific, not verified.** Owner checks the model's limits in the project's AI Studio page before execution (`accounts[].rate_limits_checked`) |
| P6 | Data use on the unpaid tier | Submitted content and responses may be used to provide, improve and develop Google products; human reviewers may read and annotate input and output (after disconnection from the account); the terms tell users not to submit sensitive, confidential or personal information; no retention period is stated [S4]. Paid Services: not used to improve products; logged for a limited period for abuse detection [S4]. In the EEA, Switzerland and the UK the Paid-Services data terms apply to all use [S4] | Owner accepts these terms for this run (`accounts[].data_use_terms_accepted`); the dataset rule in §8 applies |
| P7 | Subscriptions | Google AI plan benefits for developers apply only in the AI Studio web interface; direct API use is billed and managed separately; Antigravity agent access in AI Studio is not part of the plans [S5] | A Gemini/Google AI subscription or Antigravity entitlement gives **no** API quota or billing status |
| P8 | Thinking mode | Gemma 4 on the Gemini API has a thinking process toggled with `thinking_level` (`"high"` / `"minimal"`); the default is not documented [S1] | Installed `google-genai` 1.2.0 has no `thinking_level`; the adapter sends no thinking setting, so the provider default applies and **cannot be pinned** in this step (no dependency change). Thought tokens, if any, are not in the adapter's accounting (§2.3). Owner acknowledges (`thinking.accounting_risk_acknowledged`) |

Alternatives (published facts, same retrieval date):

| Option | Adapter | Published price | Published limits | Notes |
|---|---|---|---|---|
| **Gemini API `gemma-4-31b-it`** (proposed) | `google_genai` | Free Tier free of charge; no paid tier [S2] | Not published [S3] | FORGE's production model; unpaid-tier data terms (P6) |
| Groq `openai/gpt-oss-120b` | `openai_compatible` | $0.15 input / $0.60 output per 1M tokens [S6] | 30 RPM, 1K RPD, 8K TPM, 200K TPD (labelled base limits for the Developer plan; free-tier values not confirmed) [S7] | No inference data retained by default; reliability/abuse logs up to 30 days; Zero Data Retention available; training use not stated [S8]. Not FORGE's model; the daily token cap could stop a run |
| Gemini API `gemini-2.5-flash-lite` | `google_genai` | Free tier; paid $0.10 input / $0.40 output per 1M tokens [S2] | Not published [S3] | Not FORGE's model; a priced Gemini run is refused by the plan (thought tokens unbounded, §7) |

**Recommendation.** Gemini API `gemma-4-31b-it` for both rewriter and target
(`benchmarks/experiments/providers.step7-gemini.json`): existing adapter, FORGE's actual
production model, published as free of charge. It is **not cleared**: P1, P2 and P8 are
resolved only by an approved smoke test, and P4–P6 only by the owner. Using one model for
rewriting and answering matches how FORGE is used today; results may not transfer to other
target models.

Sources (retrieved 2026-10-14):
[S1] <https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api> (page updated 2026-07-02) ·
[S2] <https://ai.google.dev/gemini-api/docs/pricing> (updated 2026-10-13) ·
[S3] <https://ai.google.dev/gemini-api/docs/rate-limits> (updated 2026-10-13) ·
[S4] <https://ai.google.dev/gemini-api/terms> (updated 2026-04-28) ·
[S5] <https://ai.google.dev/gemini-api/docs/google-ai-plans> (updated 2026-10-13) ·
[S6] <https://console.groq.com/docs/models> ·
[S7] <https://console.groq.com/docs/rate-limits> ·
[S8] <https://console.groq.com/docs/your-data>

## 7. Budget, cost and the live execution gate (`forge benchmark plan`)

Normal path — every call succeeds on its first attempt, cache disabled:

| Condition | Calls per task | Calls (30 tasks) | Est. input tokens (chars/4) | Max output tokens |
|---|---:|---:|---:|---:|
| B0 | 1 target | 30 | 1,414 | 61,440 |
| B1 | 1 rewrite + 1 target | 60 | 3,441 rewrite + ≤ 38,400 target (bound) | 38,400 + 61,440 |
| F-legacy | 1 rewrite + 1 target | 60 | 8,861 rewrite + ≤ 38,400 target (bound) | 38,400 + 61,440 |
| **Total** | **5 per task** | **150 provider attempts** | ≈ 90,516 (bound) | ≤ 261,120 |

- **Retry ceiling:** 300 provider attempts (150 × `max_attempts` 2).
- **Budget:** `max_model_calls` 300, `max_estimated_tokens` 705,000 (≥ the 703,272-token
  worst-case reservation), `confirm_above_model_calls` 150 → the run needs `--confirm`.
- **Smoke test** (`step7-smoke-v1.json`, task `pilot-001`, all three conditions): 5
  attempts normally, ≤ 10 with retries (`max_model_calls` 10); worst-case reservation
  23,592 tokens, `max_estimated_tokens` 24,000.
- **Expected real usage** (assumption, not a measurement): rewrites of ~150–700 tokens and
  answers of ~100–700 tokens would mean roughly 60k–200k tokens in total — far below the
  reservation bound, which assumes every output reaches its maximum.
- **How the token budget works (a stop-before-the-next-call control, not a hard cap):**
  1. Before **each provider attempt** (retries included) the budget reserves an estimate:
     chars/4 of the actual prompt plus the request's `max_output_tokens`. If the tokens
     already used, plus those reserved, plus this estimate would exceed
     `max_estimated_tokens`, the attempt is refused **before anything is sent** and the run
     stops as `budget_exceeded`.
  2. Actual usage is known only after the response. The attempt is then settled with the
     provider-reported input + output tokens (or with the estimate if none are reported).
  3. Reported usage can exceed the reservation (the chars/4 estimate can undercount the
     provider's tokenizer). The total charged can then **exceed `max_estimated_tokens` by
     that final call's excess**; the next call is refused because the budget is exhausted.
  4. Thought tokens are not in the Gemini adapter's reported usage (§2.3), so they are
     neither reserved nor charged.

  The budget therefore guarantees that no further call is sent once the limit is reached;
  it does not guarantee that provider-reported (or billed) tokens never exceed the
  configured limit. Token limits and the cost figures derived from them are estimates, not
  hard cost ceilings. With 1,728 tokens of headroom over the 703,272-token worst case, an
  extreme run could also exhaust the budget before 300 attempts; it then stops as
  `budget_exceeded` (the run is invalid, §2.4).
- **Exhaustion:** the run stops before the refused call, remaining pairs are `not_run`, the
  run is `budget_exceeded`, and (as an infrastructure exclusion above 10%) invalid.
- **Failures before or during transport:** a call refused before dispatch (no slot,
  unsupported capability, budget) is not an attempt; anything handed to the adapter is one,
  even if it fails before reaching the network. Attempts are not billing records.

**Cost and authorization rules (fail closed).** For any real provider the plan fails —
and the run is refused — unless every one of these separate checks passes:

| Check | Passes only if |
|---|---|
| `token_budget_required` | `max_estimated_tokens` is set (zero, negative and non-integer values are rejected when the config is loaded) |
| `pricing_published` | every real provider/model pair has a recorded published price bound to that exact provider entry — provider name, provider type and (for OpenAI-compatible providers) endpoint URL, compared exactly with the providers file — and model ID, with tier, source URL and retrieval date. A pair without one has an **unknown** price, which is never treated as free; a price is never applied to another provider that exposes the same model name, and duplicate prices for one pair are rejected when the config is loaded |
| `cost_within_ceiling` | the cost at the token budget — `max_estimated_tokens` × the highest recorded price — is ≤ `cost.ceiling`. This is an estimate: the budget stops the next call once exhausted, but the final call's reported usage can exceed its reservation (above), so it is not a hard cap. A nonzero price on a Gemini (`google_genai`) model fails, because thought tokens are not counted and the bill could not be bounded |
| `account_tier_and_billing_confirmed` | for **every** real provider used, an `accounts` entry confirms that the project is on the priced tier (and its billing status), and that tier matches the provider's recorded price tier |
| `rate_limits_checked` | for every real provider, the owner checked the model's limits for the project in its console (AI Studio) |
| `data_use_terms_accepted` | for every real provider, the owner accepted the tier's data-use terms (§8) |
| `thinking_risk_acknowledged` | the owner acknowledged that thinking cannot be pinned and thought tokens may be uncounted (§2.3) |
| `live_execution_authorized` | `live_execution_approved` is true |

Owner confirmations are recorded statements (with `confirmed_by` and `confirmed_on`);
FORGE cannot verify them and never queries an account.

**Enforcement path.** `forge benchmark run` refuses real providers unless it is given
`--experiment FILE` (and `--allow-real-providers`). It then runs the same offline
preflight **before reading `.env` or credentials or building any adapter**, takes every
run setting from the config (conflicting flags are refused), and the runner re-checks that
the run matches the config (dataset, splits, tasks, profiles, providers, provider types,
models, endpoints and retry limits, conditions, budget, pacing, cache) before anything is
sent; a different endpoint is refused before any request. The run's manifest records the
experiment ID, protocol, protocol version, config hash and effective endpoints. For the proposed run the
recorded price is the published zero for provider `gemini` (type `google_genai`) and
model `gemma-4-31b-it` on the free tier, and the ceiling is 0: the check runs on the
supported path, but whether the owner's project is actually billed at that price is the
owner's confirmation (P4). Limitation: the Python API (`BenchmarkRunner` with
`allow_real_providers=True` and no experiment) remains available to tests that intercept
HTTP; it is not a supported live path.

## 8. Privacy and data handling

- **Sent externally (only after approval):** the 30 `pilot-v1` task prompts, the B1
  template and FORGE system prompt wrapped around them, and the rewritten prompts; the
  provider returns the rewrites and answers. No credentials, personal data or repository
  content beyond the dataset is sent.
- **No sensitive, confidential or personal data — ever.** On the unpaid tier Google may use
  prompts and outputs to improve its products and human reviewers may read them (§6 P6).
  Only the synthetic `pilot-v1` prompts may be sent; any change to the dataset must keep it
  free of personal, confidential or proprietary content. Provider-side retention follows the
  provider's terms (no period is stated for the unpaid tier).
- **Stored locally:** `benchmark-runs/<run-id>/` (git-ignored: manifest, run record,
  full prompts and outputs, summaries), the blinded export, the key and ratings; optionally
  rows in a local PostgreSQL (decision D6). Logs contain IDs and statuses only.
- **Deletion:** remove the run directory, export directory and key; with a database, the
  run's `executions`/`evaluations`/`runs` rows (history is `RESTRICT`ed, so delete
  evaluations, then executions, then the run).

## 9. Offline validation

| Check | Result |
|---|---|
| `forge benchmark plan` on the live and smoke configs | Ran offline (no adapter, router, socket, settings or `.env` access — tested). Fails, as intended, on exactly the owner gates: `account_tier_and_billing_confirmed`, `rate_limits_checked`, `data_use_terms_accepted`, `thinking_risk_acknowledged`, `live_execution_authorized`; budget, pricing and cost checks pass |
| `forge benchmark run --experiment` on the live and smoke configs | Refused before credentials, settings or adapters (tested) |
| Offline rehearsal with fake providers (`step7-offline-rehearsal.json`): plan → `run --experiment` → verify → export-blind (key outside the rater folder) → synthetic ratings → analyze | See `docs/implementation/phase-0-plan.md` §7, increment 7 |
| Tests (`tests/benchmark/test_step7.py`) | Config validation and price provenance; plan never contacts a provider or reads credentials; call counts and bounds; unknown price, documented zero price, unverified tier, each owner gate, ceiling violation, unboundable Gemini price; token budget missing/zero/negative/non-integer/valid; live-path refusal before credentials; cleared config reaches the runner with its own settings; runner gate; pacing; blinding (rater folder holds only items and template, key outside, no overwrite); analysis (synthetic refusal, one task set, failure scoring, exclusions, disputes and adjudication, each identity mismatch, missing identity, bootstrap); rubric and rater-note coverage |

## 10. Live execution procedure (requires approval at each step)

1. Owner resolves §6 P4–P6 and P8 for the project used: records the confirmations in
   `step7-smoke-v1.json` (the `accounts` entry for `gemini`, with `confirmed_by` and `confirmed_on`;
   `thinking.accounting_risk_acknowledged`), and approves a **smoke test** by setting
   `live_execution_approved: true` in that file only. `forge benchmark plan` must PASS.
2. Smoke test: `forge benchmark run --experiment benchmarks/experiments/step7-smoke-v1.json
   --allow-real-providers` — one task, all three conditions, ≤ 10 attempts, cost ceiling 0.
   It checks model availability, auth, SDK behaviour, token reporting, finish reasons and
   any sign of thinking (truncated or empty answers, usage). Its outputs are not part of the
   pilot and are reported separately.
3. Owner approves the **full run** with the same confirmations in `step7-pilot-v1.json`
   and `live_execution_approved: true`; `forge benchmark plan` must PASS. Any change to the
   config changes its hash; analysis accepts only runs made from the exact config.
4. Run the command printed by the plan (`forge benchmark run --experiment ... --confirm
   --allow-real-providers`), then `forge benchmark verify RUN_DIR --dataset
   benchmarks/pilot-v1`.
5. `export-blind` with `--key` outside the rater folder; rate; `analyze` with the config,
   key and ratings; publish the report with its INCONCLUSIVE interpretation and limitations.

## 11. Decisions requiring approval

| # | Decision | Proposal |
|---|---|---|
| D1 | Provider and model | Gemini API `gemma-4-31b-it` for rewriter and target |
| D2 | Account tier and billing status (P4) | Owner confirms the project is on the free tier (no paid billing for this model) |
| D3 | Rate limits (P5) | Owner checks the model's limits in the project's AI Studio page |
| D4 | Data-use terms (P6) | Owner accepts unpaid-tier terms for synthetic prompts only |
| D5 | Thinking (P8) | Accept the provider default for the smoke test and record what it shows; pinning needs a separate dependency decision |
| D6 | Budget | ≤ 300 provider attempts, ≤ 705,000 estimated tokens, 5 s pacing, cost ceiling 0 |
| D7 | Smoke test | One task, ≤ 10 attempts, ≤ 24,000 estimated tokens, separately approved |
| D8 | Raters | Two independent raters preferred; otherwise the owner alone (limitation) |
| D9 | Persistence | Files only, or also the local PostgreSQL (`--database`) |
| D10 | SDK version | Pin `google-genai` to the version used (installed: 1.2.0) for the run |

## 12. Limitations

- ~30 tasks, one sample each, one target model, one rewriter model: estimates are imprecise
  and model-specific; no general claim follows.
- Human ratings are subjective; one rater cannot measure reliability; blinding can be
  partly defeated by stylistic traces; FORGE cannot distinguish invented ratings from real
  ones (procedure, not software, guards this).
- F-legacy reproduces the `stream: false` path, not the web UI's streamed output.
- Several `pilot-v1` "vague" tasks gained explicit constraints; specification-level
  results are descriptive.
- Token figures before the run are planning bounds (chars/4 heuristic); real usage is known
  only from provider reports. Thought tokens are not counted by the current Gemini adapter,
  and thinking may truncate answers (scored as condition failures).
- Account tier, billing status, rate limits and model access on the owner's key are not
  verified by FORGE; they rest on the owner's recorded confirmations and the smoke test.
- Key separation is an access control, not cryptography: the run directory, or the results
  plus the blinding seed, reveal the conditions.
