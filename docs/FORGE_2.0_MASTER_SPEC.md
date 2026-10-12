# FORGE 2.0 --- Master Engineering Specification

**Project:** FORGE 2.0\
**Type:** AI Prompt Engineering IDE, Evaluation Platform, and Developer
Tool\
**Implementation mode:** Existing-repository audit followed by phased
implementation\
**Primary goal:** Build a technically rigorous, evidence-driven prompt
engineering platform.\
**Database:** PostgreSQL from Phase 0, using Supabase or Neon as a free
hosted provider.\
**Backend:** Python, Flask, SQLAlchemy 2.x, Alembic.\
**Frontend:** React, TypeScript, Vite.\
**Model support:** Open-weight models, hosted open-model inference,
local models, and compatible external providers.

------------------------------------------------------------------------

## 1. Your role and engineering responsibilities

Act as the principal software architect, senior Python engineer, AI/ML
evaluation engineer, frontend engineer, database engineer, and technical
reviewer responsible for evolving the existing FORGE repository into
FORGE 2.0.

This is not a request to create a superficial UI around an LLM API.

Build a maintainable, testable, modular, evidence-driven software
product that solves a real developer problem: making prompt changes
reproducible, testable, measurable, explainable, and safer to deploy.

Use professional engineering practices throughout:

-   Audit before modifying.
-   Establish explicit requirements and acceptance criteria.
-   Prefer small, reversible changes.
-   Maintain a single source of truth for configuration and domain
    logic.
-   Separate business logic from API routes and UI components.
-   Use type hints, structured errors, logging, migrations, and tests.
-   Keep costly model calls bounded and observable.
-   Preserve reproducibility and provenance.
-   Document decisions and trade-offs.
-   Never claim a feature works unless it has been implemented and
    tested.
-   Never fabricate evaluation results, benchmark results, model
    capabilities, latency numbers, cost savings, or quality scores.
-   Never report a command, migration, test, or deployment as successful
    unless its actual result confirms success.

Do not blindly replace the existing repository. First inspect it,
identify what should be retained, identify what should be refactored,
and identify what can safely be removed.

Do not assume the current implementation matches old documentation.
Treat the actual repository, its tests, configuration, and runtime
behavior as the source of truth for its current state.

If the repository contains an existing working FORGE prompt-enhancement
flow, preserve it as a compatibility path until the replacement is
verified.

Do not introduce paid dependencies or require paid model APIs for the
core development workflow. The application must support free-tier hosted
services and locally hosted models, subject to their actual quotas,
availability, performance, and licensing.

## 2. Product identity: what FORGE is becoming

The previous FORGE product primarily transforms a raw user prompt into a
clearer, more structured instruction.

FORGE 2.0 must evolve into an **AI Prompt Engineering IDE and Evaluation
Platform**.

Its central principle is:

> Prompt changes are code changes.

A developer should be able to:

1.  Create and edit prompts.
2.  Organize prompts into projects and workspaces.
3.  Analyze prompt structure and potential problems.
4.  Preserve the original task intent and constraints.
5.  Improve prompts through controlled optimization.
6.  Create test cases and reusable test suites.
7.  Execute prompts against target models.
8.  Compare raw, rewritten, and optimized prompts.
9.  Measure task success, instruction adherence, robustness, latency,
    token usage, and estimated cost.
10. Determine whether improvements are supported by evidence.
11. Detect regressions when prompts change.
12. Save immutable prompt versions and compare their differences.
13. Reproduce experiments from stored configurations and results.
14. Run repeatable benchmarks.
15. Access the core functionality through an API and eventually a
    CLI/SDK.

The product must not assume that a longer or more structured prompt is
automatically better.

It must not assume every prompt needs improvement.

A prompt optimizer must be allowed to recommend **NO CHANGE**.

FORGE's primary differentiator is not that it can generate a
better-looking prompt. Its differentiator is that it can test whether a
proposed change actually helps on a specified task distribution, whether
it preserves intent, and whether the measured improvement justifies the
additional cost.

**Primary audience:**

-   Developers building applications with LLMs.
-   Engineers maintaining production prompts.
-   Builders using open-weight, hosted, or self-hosted models.
-   Researchers conducting reproducible prompt experiments.

Do not prioritize casual chat users or generic prompt-template browsing
over these users.

## 3. Mandatory initial repository audit

Before changing code, inspect the entire relevant repository.

Examine at minimum:

-   Project tree and package structure.
-   README and architecture documentation.
-   `pyproject.toml`, requirements files, and lockfiles.
-   Flask application factory and route registration.
-   Existing prompt-enhancement implementation.
-   Model provider integration and system instructions.
-   Streaming behavior, including SSE if currently implemented.
-   Configuration and environment-variable handling.
-   Database code and migrations, if any.
-   Frontend components, state, routing, and build configuration.
-   Existing Dockerfiles and Docker Compose.
-   Gunicorn and Nginx configuration.
-   CI workflows.
-   Unit, integration, and frontend tests.
-   Existing deployments and health-check behavior, if documented.
-   Mock implementations, hardcoded values, unused dependencies, dead
    code, and misleading metrics.

Do not reread every file indiscriminately if focused inspection is
sufficient. Use targeted searches, dependency analysis, and test
execution.

Create these documents before substantial implementation:

-   `docs/architecture/current-state.md`
-   `docs/architecture/target-architecture.md`
-   `docs/architecture/architecture-decisions.md`
-   `docs/implementation/phase-0-plan.md`
-   `docs/implementation/feature-status.md`

The current-state document must distinguish verified facts from
assumptions.

Record:

-   What currently works.
-   What currently fails.
-   Existing API contracts.
-   Existing data formats.
-   Existing tests and their results.
-   Existing deployment constraints.
-   Functionality that must remain backward compatible.
-   Functionality that can be removed after verification.

Run the existing test suite before making changes. Record failures
separately from failures introduced by subsequent work.

Do not delete or rewrite working functionality simply because a
different architecture is proposed.

Do not claim that the old architecture is obsolete without identifying
which concrete limitations justify each change.

After the audit, produce a concise implementation plan with:

-   Findings.
-   Architecture decisions.
-   Files to add, change, or remove.
-   Risks.
-   Dependencies.
-   Phase 0 acceptance criteria.

Then begin Phase 0. Do not stop after generating a plan unless a genuine
blocker requires a decision from the user.

## 4. Architectural principles

Use a **modular monolith**, not microservices.

The application should have one deployable backend codebase, a separate
React frontend, and a worker process that runs the same Python package
with a different entry point.

Keep the core domain logic usable independently of Flask.

### Target architecture

``` text
Browser
  |
  v
React + TypeScript + Vite
  |
  v
Flask API / Gunicorn
  |
  +--> API and validation layer
  |
  +--> Application services
  |
  +--> Prompt analysis
  |
  +--> Intent preservation
  |
  +--> Optimization engine
  |
  +--> Evaluation engine
  |
  +--> Benchmark engine
  |
  +--> ProviderRouter
  |      +--> Google GenAI adapter, if retained
  |      +--> OpenAI-compatible API adapter
  |      +--> Ollama adapter, where needed
  |      +--> llama.cpp adapter, where needed
  |      +--> Other compatible providers through configuration
  |
  +--> Repository interfaces / SQLAlchemy
  |
  v
PostgreSQL
  |
  +--> Prompts and immutable versions
  +--> Test suites and suite revisions
  +--> Runs, executions, and evaluations
  +--> Optimization sessions and change records
  +--> Jobs, experiments, and benchmark manifests
  +--> Cache metadata and provider/model configuration

Worker process:
  |
  +--> Claims bounded evaluation/optimization jobs
  +--> Executes model calls
  +--> Persists raw outputs and structured results
  +--> Publishes progress events
  +--> Supports cancellation and failure recovery
```

Shared infrastructure:

-   Configuration management.
-   Structured logging.
-   Request/job identifiers.
-   Budget guards.
-   Timeouts and bounded retries.
-   Rate limiting and provider concurrency controls.
-   Cache.
-   Database migrations.
-   Health/readiness checks.
-   Test fixtures.

The React frontend must not call model providers directly or expose
provider API keys.

All expensive model traffic must pass through the ProviderRouter so
FORGE can consistently apply limits, logging, caching, timeouts, and
accounting.

Avoid premature abstraction. Introduce interfaces where they support
testability, provider portability, or independently testable domain
logic.

Do not add Redis, Celery, Kafka, Kubernetes, or microservices in the
initial implementation. Reassess them only when measured workload
requires them.

## 5. Database: PostgreSQL from Phase 0

**Important architectural change:** Do not use SQLite as the primary
database and postpone PostgreSQL until later. Use PostgreSQL from Phase
0.

Hosted development/deployment options:

-   Supabase PostgreSQL free tier.
-   Neon PostgreSQL free tier.
-   Local PostgreSQL in Docker for development and integration testing.

Choose one primary hosted provider for the initial setup. Keep the
application provider-independent so that switching between Supabase,
Neon, and local PostgreSQL requires configuration changes rather than
application rewrites.

Before documenting free-tier limits, verify current provider terms and
quotas from official documentation. Never promise permanent free hosting
or availability.

Database access:

-   SQLAlchemy 2.x.
-   Alembic migrations.
-   psycopg 3 or another explicitly selected, maintained PostgreSQL
    driver.
-   Typed SQLAlchemy models where appropriate.
-   Repository/service separation.
-   Explicit transaction boundaries.
-   Connection pooling configured for the selected hosting environment.
-   Environment-driven connection configuration.
-   PostgreSQL-compatible SQL throughout the production application.

Do not scatter Supabase SDK calls throughout the codebase. Use standard
PostgreSQL connections through SQLAlchemy.

Supabase may optionally be used for future authentication or other
platform services, but these must not become mandatory dependencies of
the domain logic. Do not add Supabase Auth merely because the database
is hosted there.

Configuration variables should include appropriate equivalents of:

``` dotenv
DATABASE_URL=
DATABASE_POOL_SIZE=
DATABASE_MAX_OVERFLOW=
DATABASE_POOL_TIMEOUT=
DATABASE_CONNECT_TIMEOUT=
DATABASE_SSLMODE=
```

Use the minimum necessary variables; avoid duplicate configuration that
creates conflicting sources of truth.

Handle Supabase connection options carefully:

-   Use the correct connection endpoint and credentials.
-   Use SSL as required by the provider.
-   Select direct or pooled connections based on the deployment
    environment.
-   Do not hardcode a database hostname or password.
-   Do not commit `.env` files or credentials.
-   Provide a safe `.env.example` containing placeholders only.

Do not use SQLite-specific SQL, implicit SQLite type behavior, or
SQLite-only features in application code.

SQLite may be used for isolated unit tests only if it accurately
exercises the relevant behavior. Use PostgreSQL integration tests for
constraints, JSON behavior, indexes, migrations, transactions, and
concurrency semantics.

The project must start without database credentials in a clearly
documented local setup mode, using a local PostgreSQL container or a
test database. It must fail with a clear configuration error if the
selected runtime requires a database but none is configured.

Database operations must not happen at module import time.

Do not automatically run destructive migrations or erase existing data.
Provide explicit migration and upgrade instructions.

## 6. Data model and immutable experiment history

Design the database from the domain model rather than creating tables
independently for every feature.

At minimum, evaluate the need for these entities:

1.  Workspace
2.  Project, if distinct from workspace
3.  Provider configuration
4.  Model profile
5.  Prompt
6.  PromptVersion
7.  PromptTag
8.  IntentSpec
9.  TestSuite
10. TestCase
11. SuiteRevision
12. Job
13. Run
14. Execution
15. Evaluation
16. OptimizationSession
17. ChangeRecord
18. Experiment
19. ExperimentRun
20. LLM cache entry
21. Benchmark manifest/result

Deployment and trace tables may be introduced later when those features
are implemented.

Do not create every future table in Phase 0 merely to make the schema
appear complete. Build a minimal coherent schema and expand it with
migrations.

`PromptVersion` must be immutable once saved. Editing a prompt creates a
new version or a new draft, rather than overwriting historical
experiment input.

`SuiteRevision` must identify the exact test cases and their versions
used in an experiment.

A `Run` must reference immutable identifiers or content hashes for:

-   Prompt version(s).
-   Test suite revision.
-   Target model and provider.
-   Generation parameters.
-   Evaluator/rubric configuration.
-   Optimization configuration where applicable.
-   Random seeds where supported.
-   FORGE code/package version.
-   Relevant environment/configuration version.

Store raw model output separately from derived evaluation results.

Do not silently recompute historical scores when evaluator code changes.
Store evaluator version and configuration, and explicitly create a new
evaluation when re-scoring old outputs.

Persist enough information to reproduce the experiment as closely as the
provider allows. Explain that exact bit-for-bit reproduction is not
guaranteed when a remote model is nondeterministic or changes
server-side.

Add appropriate foreign keys, unique constraints, check constraints,
indexes, and cascade rules. Avoid cascading deletion of critical
historical records.

Support deletion and privacy requirements without destroying the
integrity of experiment history. Define the distinction between deleting
a workspace, deleting user-provided content, and retaining anonymized
aggregate results.

Use Alembic for all schema changes.

## 7. Core domain object: IntentSpec

Create a structured representation of the user's intended task.

`IntentSpec` should contain fields such as:

-   `goal`
-   `task_type`
-   `explicit_requirements`
-   `hard_constraints`
-   `soft_preferences`
-   `output_format`
-   `audience/context`
-   `assumptions`
-   `open_questions`
-   `non_goals`
-   `source/provenance` of each requirement
-   schema version

Only explicit user-sourced requirements are binding by default. Inferred
assumptions must be clearly marked as assumptions, not silently
converted into requirements.

A requirement should preserve:

-   Its content.
-   Whether it is hard or soft.
-   Its source.
-   Whether the user confirmed it.
-   Any relevant structured metadata.

IntentSpec is the anchor for prompt improvement.

The system must detect when a proposed prompt:

-   Removes a requirement.
-   Adds an unsupported requirement.
-   Changes the intended task.
-   Changes scope.
-   Weakens a hard constraint.
-   Introduces conflicting instructions.
-   Changes the required output format.
-   Makes assumptions without disclosing them.

Do not claim perfect semantic intent preservation. Intent extraction and
comparison can be imperfect. Record uncertainty and make material
changes visible to the user.

## 8. ProviderRouter and model orchestration

Implement a centralized provider abstraction.

A provider adapter should support, where genuinely available:

-   Provider identity.
-   Model identity.
-   Capability discovery.
-   Health checks.
-   Non-streaming completion.
-   Streaming completion.
-   Token counting or documented estimation.
-   Structured output where supported.
-   Model limits and context window metadata.
-   Seed support where available.
-   Timeout and cancellation behavior.
-   Usage metadata.
-   Error normalization.

Do not pretend all providers implement the same capabilities. Represent
unsupported features explicitly.

Support these logical model roles:

**Generator:** Creates candidate prompt revisions.\
**Critic:** Identifies weaknesses, contradictions, and missing
requirements.\
**Judge:** Evaluates outputs against a defined rubric.\
**Target:** Executes the actual task using the prompt under test.

These roles are logical configuration, not separate autonomous agents.
Multiple roles may use the same model when necessary, but configuration
must make this explicit.

Prefer a judge from a different model family than the target when
feasible. This is a bias-reduction strategy, not a guarantee of unbiased
evaluation.

The first-class provider strategy should support open-weight models and
self-hosted inference.

Implement the OpenAI-compatible adapter so compatible endpoints can be
configured without changing domain logic. Support local Ollama or
llama.cpp through the appropriate adapter/configuration rather than
assuming that every endpoint supports identical APIs.

Retain the existing Google GenAI adapter if the repository already
depends on it and it remains useful. Do not make Google GenAI the only
viable path.

Support hosted open-model endpoints only when their endpoint, model ID,
authentication, and actual capabilities are configured and verified.

Do not hardcode a list of models that becomes stale. Model IDs, provider
endpoints, limits, and pricing must be configurable. Record the exact
model identifier reported or configured for every run.

Normalize provider errors into categories:

-   Authentication/configuration.
-   Rate limit.
-   Transient server/network failure.
-   Timeout.
-   Context overflow.
-   Invalid request.
-   Malformed structured output.
-   Unsupported capability.
-   Cancelled.
-   Unknown provider failure.

Retry only retryable errors, with bounded exponential backoff and
jitter. Respect `Retry-After` where provided.

Generator, critic, and judge fallbacks must be recorded in run metadata.
A failed target-model execution must not silently switch to another
model and pretend the same experiment was completed.

Do not expose provider secrets in responses, traces, logs, frontend
state, or persisted prompt content.

## 9. Feature priorities: what to build

Implement features according to the following priority tiers.

### MUST BUILD

-   Prompt workspace and editor.
-   Prompt versions and semantic/textual diffs.
-   Playground and target-model execution.
-   Prompt analysis.
-   Intent extraction and requirement elicitation.
-   Prompt optimization.
-   Test cases and test suites.
-   Evaluation engine.
-   A/B comparison and regression testing.
-   Evidence-gated optimization selection.
-   Provider abstraction and model configuration.
-   PostgreSQL persistence.
-   Experiment/run history.
-   Reproducible benchmark CLI or equivalent reproducible runner.
-   Versioned API.
-   Local-model compatibility.
-   Automated testing and CI.
-   Security, budgets, and cost controls.

### SHOULD BUILD

-   Heuristic prompt linting.
-   Instruction-conflict detection.
-   Prompt-injection risk analysis as a heuristic, not a security
    guarantee.
-   Robustness testing with controlled perturbations.
-   Prompt compression under a specified context budget.
-   Token/latency/cost reporting.
-   Experiment comparison.
-   Export/import of prompts, test suites, and benchmark manifests.
-   Clear explanation of accepted/rejected optimization changes.
-   A lightweight model capability registry.

### LATER, ONLY WHEN JUSTIFIED

-   Public or packaged developer SDK.
-   Deployments and runtime tracing.
-   Human feedback collection and analysis.
-   Model-specific optimization based on measured evidence.
-   Multi-agent optimization if ablations demonstrate a benefit.
-   Sandboxed execution of generated code.
-   Team-level authentication and collaboration beyond the initial
    scope.
-   Advanced observability integrations.
-   A large static template library.

### DO NOT BUILD AS CORE FEATURES

-   An unvalidated composite "prompt quality score" presented as ground
    truth.
-   A standalone score with arbitrary weights and no validation.
-   A static prompt-template catalog as the primary product.
-   A mutation laboratory before evaluation works.
-   Multi-agent orchestration merely to claim agentic AI.
-   WebSockets when SSE is sufficient.
-   Microservices before there is a demonstrated need.
-   A self-learning feedback loop without evidence and safeguards.
-   Model-specific optimization claims without controlled tests.
-   Live production observability before the underlying evaluation and
    reproducibility capabilities exist.
-   Artificial confidence numbers that do not correspond to calibrated
    probabilities.
-   Mock results displayed as real model evaluations.

Merge prompt compression, context-budget optimization, and cost
optimization into one constrained optimization capability instead of
creating separate, duplicative systems.

## 10. Prompt workspace and playground

Create a developer-oriented prompt workspace.

Core capabilities:

-   Create, edit, save, duplicate, and archive prompts.
-   Organize prompts by workspace/project.
-   Display version history.
-   Compare versions.
-   Restore an earlier version by creating a new version from it.
-   Configure prompt variables.
-   Validate required variables and types.
-   Preview variable substitution safely.
-   Configure system/developer/user prompt components when the provider
    supports them.
-   Select target provider and model.
-   Configure generation parameters.
-   Run a prompt against the selected model.
-   Stream output when supported.
-   Display normalized errors and usage metadata.
-   Save executions to history.
-   Link executions to the exact prompt version and model configuration.

Do not interpolate untrusted values into executable code. Treat template
rendering as data substitution, not code evaluation.

Preserve the original FORGE enhancement capability as an entry point
where practical. Existing users should not lose the original core
workflow.

The playground must distinguish:

-   Draft prompt.
-   Saved immutable version.
-   Executed prompt.
-   Tested prompt.
-   Benchmark-validated prompt.

Never display an untested prompt as benchmark-validated.

## 11. Prompt analyzer

The analyzer must combine deterministic checks with optional model
assistance.

Deterministic checks should cover, where applicable:

-   Empty or ambiguous objective.
-   Missing required output format.
-   Contradictory constraints.
-   Duplicated instructions.
-   Undefined variables.
-   Excessive length relative to a configured context budget.
-   Missing required sections for a declared prompt schema.
-   Suspicious instruction conflicts.
-   Unsupported assumptions.
-   Missing task-specific constraints.
-   Potentially dangerous trust-boundary mistakes.

Do not assume every prompt requires a role, numbered steps, examples, or
a fixed template. Analysis should be task-aware.

LLM-assisted analysis may identify:

-   Ambiguity.
-   Missing context.
-   Competing objectives.
-   Implicit assumptions.
-   Weakly specified acceptance criteria.
-   Potential intent drift.

Separate findings into:

-   Deterministic rule violation.
-   Model-generated suggestion.
-   User-confirmed requirement.
-   Unverified hypothesis.

Each finding must include:

-   Description.
-   Severity.
-   Evidence or excerpt.
-   Why it matters.
-   Suggested action.
-   Whether the user must decide.

Do not represent heuristic injection detection as a complete security
defense.

## 12. Intelligent requirement elicitation

When a prompt is underspecified, FORGE should determine whether
clarification would materially improve the result.

Process:

1.  Extract the likely goal and explicit constraints.
2.  Identify important missing information.
3.  Distinguish essential missing information from optional preferences.
4.  Estimate whether each question changes the output materially.
5.  Ask only high-value clarification questions.
6.  Allow users to skip optional questions.
7.  Preserve the answers and their provenance in IntentSpec.
8.  Continue with explicit assumptions when appropriate.

Do not create long questionnaires for simple tasks.

Do not repeatedly ask for information already provided.

The user must be able to review the extracted intent before
optimization.

Support at least two paths:

-   **Quick mode:** minimal clarification, explicitly unverified
    improvement.
-   **Tested mode:** use a test suite and measured outcomes to select a
    revision.

## 13. Optimization engine

Build an optimization pipeline that is explicit, bounded, and auditable.

### Required pipeline

1.  **Stage 0:** Input validation and deterministic linting.
2.  **Stage 1:** Extract or update IntentSpec.
3.  **Stage 2:** Identify missing requirements and contradictions.
4.  **Stage 3:** Request material clarifications when necessary.
5.  **Stage 4:** Generate a small configurable set of candidate prompts.
6.  **Stage 5:** Apply deterministic hard-constraint filters.
7.  **Stage 6:** Evaluate intent preservation and scope changes.
8.  **Stage 7:** Optionally critique and refine candidates within a
    strict budget.
9.  **Stage 8:** Execute surviving candidates against the target model
    and test suite.
10. **Stage 9:** Evaluate outputs using the configured evaluation
    policy.
11. **Stage 10:** Compare candidates with the baseline.
12. **Stage 11:** Apply evidence-gated selection rules.
13. **Stage 12:** Record a change report.
14. **Stage 13:** Present the recommendation for user review.
15. **Stage 14:** Save an accepted result as a new immutable prompt
    version.

Candidate generation may use different strategies, such as:

-   Clarify objective and acceptance criteria.
-   Improve task-specific constraints.
-   Improve output schema and formatting.
-   Add context organization.
-   Remove redundancy.
-   Compress while preserving requirements.

Do not force every strategy onto every task.

Candidate generation must be configurable, with a default small
candidate count. Do not generate dozens of candidates by default.

The unchanged original prompt **must always remain a candidate and the
baseline**.

### Hard constraints

-   Reject candidates that violate a confirmed hard requirement.
-   Reject candidates that change task scope without authorization.
-   Reject malformed or invalid candidates.
-   Reject candidates that exceed explicit token/context limits.
-   Never accept a candidate solely because an LLM judge prefers its
    wording.

Intent-preservation checks must report uncertainty. If a candidate makes
a material change, show the difference and require user approval where
appropriate.

### Selection policy

1.  Apply hard safety, intent, and format gates.
2.  Compare task-success outcomes on matched test cases.
3.  Calculate uncertainty for the primary metric.
4.  Prefer the baseline when improvement is not sufficiently supported.
5.  Among candidates with practically equivalent measured outcomes,
    prefer the simpler/shorter candidate when it reduces latency,
    tokens, or cost.
6.  Consider secondary metrics only under a declared policy.
7.  Report trade-offs rather than hiding them in one score.

Support two modes:

**LITE MODE**

-   Produces suggestions without a test suite.
-   May use heuristics and model critique.
-   Must be labeled **UNVERIFIED**.
-   Must not claim empirical superiority.

**TESTED MODE**

-   Requires a valid test suite.
-   Evaluates baseline and candidates.
-   Stores outputs, configuration, and metrics.
-   Selects only according to the configured evidence policy.
-   Must be labeled **TESTED ON N CASES**, with uncertainty and
    limitations visible.

If the baseline wins, return the baseline and explain why. If results
are inconclusive, say so. Do not invent an improvement simply to satisfy
the user.

## 14. Evaluation engine: the product's core

The evaluation engine is the most important technical subsystem in FORGE
2.0. Build it before attempting advanced optimization.

Evaluation must use real model outputs, versioned evaluators, recorded
configuration, and reproducible experiment manifests.

Use a layered evaluation system:

-   **L0: Deterministic checks.**
-   **L1: Rubric-based evaluation.**
-   **L2: Pairwise model judging.**
-   **L3: Reference-based evaluation when trustworthy expected answers
    exist.**
-   **L4: Human calibration/verification where practical.**

Not every task supports every layer. Select evaluation methods by task
type.

### L0: Deterministic checks

May include:

-   Exact or normalized string matching.
-   Required-field validation.
-   JSON/schema validation.
-   Regex and format validation.
-   Length and token limits.
-   Required phrase/section checks.
-   Programmatic assertions.
-   Domain-specific checks registered for a task.

### L1: Rubric evaluation

-   Evaluate outputs against explicit criteria.
-   Use structured judge output with a validated schema.
-   Record criterion-level judgments and explanations.
-   Store judge model, prompt, version, and parameters.
-   Reject malformed judge output and apply at most one bounded repair
    attempt.

### L2: Pairwise comparison

-   Compare outputs for the same test case.
-   Use a fixed, explicit rubric.
-   Randomize or swap presentation order to detect position bias.
-   Record preference, tie, invalid judgment, and reasoning.
-   Aggregate results rather than relying on one judgment.

### L3: Reference-based evaluation

-   Use reference answers only when meaningful.
-   Do not assume lexical similarity is equivalent to correctness.
-   Allow task-specific evaluators and reference-free evaluation.

### L4: Human calibration

-   Provide an exportable sample of cases and outputs for human review.
-   Compare judge decisions against human judgments.
-   Record agreement and disagreements.
-   Treat human judgments as imperfect measurements, not unquestionable
    truth.

### Metrics

Measure appropriate dimensions:

-   Task success.
-   Instruction adherence.
-   Hard-constraint adherence.
-   Output-format correctness.
-   Intent preservation.
-   Robustness under controlled perturbations.
-   Latency.
-   Input/output token usage.
-   Estimated cost where trustworthy pricing data is available.
-   Failure rate.
-   Missing/invalid evaluation rate.

Do not collapse these dimensions into a composite score by default.

If an optional composite score is introduced later, document its
formula, validate its relationship with task success, expose the
component metrics, and avoid presenting it as universal ground truth.

### Judge bias and validity

-   Prefer a judge model family different from the target where
    feasible.
-   Use structured rubrics.
-   Blind candidate identities where practical.
-   Swap answer order in pairwise comparisons.
-   Track invalid judgments.
-   Track judge-human agreement on a calibration sample.
-   Report disagreement and limitations.
-   Do not equate model-generated evaluation with objective truth.

### Statistics

-   Use paired comparisons because candidates share test cases.
-   Resample at the test-case level for bootstrap intervals.
-   Account for repeated stochastic samples within a case.
-   Use exact McNemar or an appropriate paired test for binary outcomes.
-   Use paired bootstrap confidence intervals for suitable continuous
    metrics.
-   Apply an appropriate multiple-comparison correction when comparing
    many candidates or hypotheses.
-   Report sample size, failed cases, missing judgments, uncertainty,
    and practical effect size.
-   Distinguish statistical significance from practical significance.
-   Mark very small suites as **INCONCLUSIVE**.
-   Do not claim universal thresholds are scientific laws.
-   Choose statistical methods according to the metric and study design.

For stochastic target models, allow repeated samples. Start with a
configurable default such as three samples per case when budget permits.
Document when deterministic settings or seeds are unsupported.

Do not run expensive statistics on invalid or silently substituted
outputs.

All evaluation code must be testable independently of provider calls.

## 15. Test cases and test suites

Developers must be able to create reusable prompt test suites.

Each test case may contain:

-   Stable identifier.
-   Name.
-   Task category.
-   Input variables.
-   Expected output or reference, when appropriate.
-   Required constraints.
-   Deterministic assertions.
-   Rubric.
-   Tags.
-   Difficulty/specification level.
-   Optional perturbation configuration.
-   Enabled/disabled state.

Suite revisions must be immutable once used in a completed experiment.

Support:

-   Manual case creation.
-   Editing before a suite revision is frozen.
-   Import/export using a documented schema.
-   Validation before execution.
-   Duplication and suite revision history.
-   Tags and category filters.
-   Small local test runs.
-   Full evaluation runs.
-   Reuse across prompt versions.

Avoid treating LLM-generated test cases as authoritative. Allow
generated suggestions, but label them and require review before they
become trusted benchmark cases.

A test suite should be capable of detecting:

-   Quality regressions.
-   Constraint violations.
-   Formatting regressions.
-   Intent drift.
-   Robustness regressions.

## 16. A/B testing and regression testing

A/B testing must compare prompt versions under a matched evaluation
setup.

At minimum:

-   Baseline and candidate prompts.
-   Same test suite revision.
-   Same target model configuration.
-   Same generation parameters where applicable.
-   Matched inputs.
-   Repeated samples where configured.
-   Recorded failures.
-   Comparable evaluators.
-   Paired results and uncertainty.

Regression testing must let the developer define gates such as:

-   No regression in hard-constraint adherence.
-   No regression in required output schema.
-   Minimum task-success threshold.
-   Maximum latency.
-   Maximum token usage.
-   Maximum estimated cost.
-   Minimum robustness retention.

Gates must be explicit and versioned.

If a prompt fails a gate, report the failing cases and the severity. Do
not silently accept it because the average score improved.

Support:

-   Compare two versions.
-   Compare multiple candidates.
-   Re-run a saved configuration.
-   Inspect individual examples.
-   View aggregate metrics.
-   Export results.
-   Mark a version as approved only through an explicit action.

Do not implement a deployment system before these comparison and
regression primitives work.

## 17. Robustness and prompt security

Implement robustness evaluation as an optional, controlled test mode.

Potential perturbations:

-   Minor typos.
-   Harmless wording variations.
-   Reordering noncritical context sections.
-   Distractor context.
-   Truncation within a declared policy.
-   Contradictory or adversarial instructions in test fixtures.
-   Missing optional context.
-   Boundary-length inputs.

Each perturbation must be recorded with its seed/configuration where
supported.

Do not combine arbitrary perturbations and call the result a
standardized benchmark without validation.

Prompt injection analysis must distinguish:

-   Untrusted user input.
-   Untrusted retrieved/context content.
-   Trusted application instructions.
-   Model-generated content.

Use deterministic heuristics to flag suspicious patterns and explain
limitations. Do not promise that a prompt analyzer can guarantee
protection against injection.

Never execute generated code on the host. If code execution is
considered in a future phase, require an isolated sandbox with explicit
resource and network restrictions.

## 18. Benchmark program: test whether FORGE adds value

FORGE must evaluate its own claims.

Create a version-controlled benchmark program.

Start with approximately 30 carefully authored task cases during Phase
0. Use them for a pilot, not as proof of universal performance.

Expand to an initial benchmark of around 80 tasks and then approximately
160 only when the first evaluation process is reliable and the budget
permits.

Potential categories:

-   Coding.
-   Research and summarization.
-   Data analysis.
-   Writing.
-   Reasoning.
-   Retrieval-augmented generation.
-   Agent/tool-selection instructions.
-   Structured output.

These are proposed categories, not mandatory equal-sized strata. Select
the final task distribution based on the intended use cases.

Stratify task specification:

-   Well-specified.
-   Partially specified.
-   Vague or underspecified.

Use separate development and held-out test sets. Avoid tuning the
optimizer on the held-out set.

Compare these systems where applicable:

-   **B0:** Original raw prompt.
-   **B1:** Generic single-shot prompt rewrite.
-   **B2:** Human-written expert prompt on a smaller carefully selected
    subset.
-   **B3:** Iterative self-critique rewrite.
-   **F-Lite:** FORGE without test-based selection.
-   **F-Full:** FORGE with intent gates and test-based selection.

Ablations should measure the contribution of:

-   Requirement elicitation.
-   Multiple candidate generation.
-   Intent-preservation gate.
-   Test-based selection versus judge-only selection.
-   Robustness evaluation.
-   Any optional multi-agent component.

Pre-register the hypotheses, metrics, comparison methods, exclusion
rules, and benchmark version before running the final experiment.

Test hypotheses such as:

-   **H1:** FORGE improves task success over raw prompts and a generic
    rewrite on underspecified tasks.
-   **H2:** FORGE offers little benefit or may cause harm on
    well-specified prompts.
-   **H3:** Test-based selection outperforms judge-only selection.
-   **H4:** Intent gates reduce unauthorized scope/constraint changes.
-   **H5:** The improvement, when present, justifies added tokens,
    latency, and cost.

These are hypotheses to test, not conclusions to assume.

Track:

-   Held-out task success.
-   Hard-constraint adherence.
-   Output-format correctness.
-   Intent-preservation violations.
-   Robustness retention.
-   Pairwise win/tie/loss.
-   Invalid evaluation rate.
-   Judge-human agreement.
-   Latency overhead.
-   Token overhead.
-   Estimated cost.
-   Failure and timeout rates.

Include negative results. If FORGE does not outperform a generic
rewrite, report that honestly.

The benchmark must be runnable from a CLI or equivalent reproducible
command and produce:

-   A versioned manifest.
-   Machine-readable results.
-   Human-readable summary.
-   Per-case results.
-   Aggregate statistics and uncertainty.
-   Model/provider/configuration metadata.
-   Failure report.
-   Comparison and ablation report.

Use cached outputs for repeatable analysis when appropriate, but
distinguish cached replay from a fresh model execution.

Never publish invented benchmark results or claim that a small pilot
establishes general superiority.

## 19. Caching, budgets, and cost control

Implement a cache and budget system before large-scale optimization.

The cache key must incorporate every input that can materially change a
model result, including:

-   Provider and exact model ID.
-   Prompt/system instructions.
-   Input messages.
-   Generation parameters.
-   Relevant structured-output schema.
-   Evaluator version where caching evaluation results.
-   Other capability/configuration details affecting output.

Use a stable canonical serialization and content hash.

Do not cache failures indefinitely. Do not return a result for a
different model/configuration merely because the user inputs look
similar.

Record whether a result was a cache hit or a fresh execution.

Provide:

-   Per-run maximum model calls.
-   Per-run token budget where estimable.
-   Maximum candidates.
-   Maximum test cases.
-   Maximum samples per case.
-   Per-provider concurrency limits.
-   Request and model-call timeouts.
-   Bounded retries.
-   Cancellation.
-   Estimated cost before execution where possible.
-   Actual provider-reported usage after execution where available.

Distinguish:

-   Provider-reported token counts.
-   Locally estimated token counts.
-   Provider-reported cost.
-   Cost estimated from a versioned pricing configuration.
-   Unknown cost.

Never fabricate costs when the provider does not expose sufficient usage
data.

Large evaluations must run as background jobs rather than blocking a web
request until completion.

Provide budget estimation before execution and require explicit
confirmation when a configured threshold is exceeded.

## 20. Job execution and streaming

Keep synchronous Flask/Gunicorn for ordinary API operations.

Use a database-backed job table and a separate worker process for
expensive optimization, evaluation, and benchmark tasks.

For the initial version:

-   Use the same application image with a separate worker entry point.
-   Claim jobs safely using PostgreSQL-supported locking/claiming
    patterns.
-   Use bounded worker concurrency.
-   Record status, heartbeat, attempts, timestamps, and failure details.
-   Make retries idempotent where possible.
-   Support cancellation.
-   Recover or mark abandoned jobs after worker failure.
-   Prevent two workers from processing the same job concurrently.
-   Avoid holding database transactions open during long model calls.

Do not add Redis/Celery initially unless a measured requirement
justifies it.

Use Server-Sent Events (SSE) for progress streaming when appropriate.

Define events such as:

-   `job.started`
-   `stage.started`
-   `candidate.generated`
-   `execution.completed`
-   `evaluation.completed`
-   `progress.updated`
-   `job.failed`
-   `job.cancelled`
-   `job.completed`

Use structured JSON payloads and document the schema.

Persist important progress/results so a client reconnecting after a
network failure can retrieve current job state. SSE must not be the only
record of the experiment.

Interactive single-model completions may stream directly where
appropriate. Expensive multi-case evaluations should be asynchronous
jobs.

## 21. Backend implementation

Use Flask's application factory pattern and modular blueprints.

Organize code by domain responsibility, not by an excessive number of
tiny files.

### Suggested structure

``` text
forge/
  pyproject.toml
  src/
    forge/
      __init__.py
      app.py
      settings.py
      cli.py
      worker.py

      api/
        health.py
        prompts.py
        executions.py
        analysis.py
        optimization.py
        suites.py
        runs.py
        providers.py
        experiments.py
        benchmarks.py

      services/
        prompt_service.py
        execution_service.py
        analysis_service.py
        optimization_service.py
        suite_service.py
        run_service.py
        experiment_service.py

      domain/
        prompts.py
        intent.py
        suites.py
        runs.py
        evaluations.py
        errors.py

      providers/
        base.py
        router.py
        capabilities.py
        errors.py
        openai_compatible.py
        ollama.py
        llama_cpp.py
        google_genai.py

      analysis/
        lint.py
        conflicts.py
        intent_extraction.py
        intent_preservation.py

      optimization/
        pipeline.py
        candidate_generation.py
        selection.py
        constraints.py

      evaluation/
        runner.py
        deterministic.py
        rubric.py
        pairwise.py
        statistics.py
        robustness.py

      benchmark/
        runner.py
        manifests.py
        reporting.py

      db/
        models.py
        session.py
        repositories/
        migrations/

      jobs/
        queue.py
        executor.py
        events.py

      infrastructure/
        cache.py
        budgets.py
        logging.py

  web/
  benchmarks/
  tests/
  deploy/
  docs/
  .github/workflows/
```

This is a proposed structure, not a requirement to create empty modules
for every item immediately. Adapt it to the actual repository and
implement only modules needed for the current phase.

Use clear API/service/domain boundaries.

Keep route handlers thin:

-   Validate request.
-   Invoke a service.
-   Return a consistent response.
-   Map domain errors to appropriate HTTP status codes.

Do not put business logic in route handlers, React components, or
database model hooks.

Use structured error responses with stable error codes and safe
messages.

## 22. API design

Use a versioned API base path such as `/api/v1`.

Define and document request/response schemas.

### Core endpoint groups

**Health**

-   `GET /health`
-   `GET /ready`

**Prompts**

-   Create/list/get prompts.
-   Create/list/get versions.
-   Compare versions.
-   Duplicate or archive prompts.
-   Restore from a historical version by creating a new version.

**Execution**

-   Start an interactive execution.
-   Inspect execution history.
-   Retrieve execution output and usage.
-   Stream supported interactive completions.

**Analysis**

-   Analyze a prompt.
-   Extract/review IntentSpec.
-   Submit clarification answers.

**Optimization**

-   Start optimization.
-   Inspect candidate prompts.
-   Compare candidates.
-   Retrieve evidence.
-   Accept or reject a candidate.
-   Save accepted candidate as a new version.

**Test suites**

-   Create/update drafts.
-   Add/update/remove test cases before freezing a revision.
-   Freeze/retrieve suite revisions.
-   Import/export suites.

**Evaluation runs**

-   Estimate run budget.
-   Create a run.
-   Inspect run status.
-   Retrieve aggregate and per-case results.
-   Stream progress.
-   Cancel a run.
-   Compare runs.

**Providers**

-   List configured providers.
-   List available/configured model profiles.
-   Check provider health/capabilities.

**Experiments and benchmarks**

-   Create/retrieve experiment configurations.
-   Launch a benchmark.
-   Retrieve manifest, results, and reports.

Do not implement every endpoint before its underlying capability exists.

Use explicit API schemas and input validation. Do not expose database
models directly as API responses.

Use pagination for history/list endpoints.

Make job creation idempotent where appropriate.

Use consistent error responses and correlation IDs.

Keep secrets server-side and return only safe provider metadata.

Generate OpenAPI documentation or maintain an equivalent accurate API
spec.

## 23. Frontend: React + TypeScript + Vite

Build a professional developer-oriented interface, not a generic chatbot
UI.

Use:

-   React.
-   TypeScript with strict type checking.
-   Vite.
-   A maintainable client-side routing solution.
-   TanStack Query or an equivalent server-state library.
-   A small global state store only where shared client state requires
    it.
-   CodeMirror 6 or another suitable code/text editor.
-   Vitest for component/unit tests.
-   Playwright for critical end-to-end flows.

Do not add a complex frontend framework without a demonstrated need.

### Core pages

1.  Workspace/dashboard.
2.  Prompt editor/playground.
3.  Prompt version history and diff.
4.  Prompt analysis.
5.  Optimization wizard.
6.  Test-suite manager.
7.  Evaluation run details.
8.  Regression comparison.
9.  Experiment comparison.
10. Provider/model settings.
11. Benchmark results.

### Critical UI behavior

-   Display loading, empty, error, success, and cancellation states.
-   Show whether a prompt is unverified or tested.
-   Show sample size, failed cases, uncertainty, and relevant metrics.
-   Display baseline-versus-candidate comparisons.
-   Let users inspect individual test cases.
-   Show which requirements were preserved or changed.
-   Show model/provider and configuration used.
-   Show cache hits versus fresh execution.
-   Show estimated versus provider-reported usage.
-   Allow the user to review a candidate before accepting it.
-   Never represent a mock result as a real result.
-   Never imply statistical certainty when evidence is insufficient.

Do not display an unexplained universal prompt quality score.

Keep the interface focused on the developer workflow. Avoid unnecessary
decorative pages, a giant static template gallery, and charts that do
not answer a concrete question.

Sanitize and safely render all model-generated content. Treat it as
untrusted input.

## 24. CLI and reproducible experiments

Implement a small CLI after the underlying services and benchmark runner
are stable.

It should eventually support operations conceptually equivalent to:

``` text
forge doctor
forge providers list
forge prompt validate
forge prompt analyze
forge suite validate
forge run
forge run compare
forge benchmark run
forge benchmark report
forge export
```

Use exact command names only after designing and documenting their
schemas.

The CLI must:

-   Read configuration safely.
-   Return meaningful exit codes.
-   Support machine-readable JSON output.
-   Produce readable errors.
-   Avoid logging secrets.
-   Reuse application services rather than duplicating business logic.

Each benchmark or evaluation run must generate a manifest that records
the relevant immutable inputs and configuration.

## 25. Testing strategy

Use a layered testing strategy.

### Unit tests

-   IntentSpec validation.
-   Prompt version immutability.
-   Prompt template variable validation.
-   Deterministic linting.
-   Hard-constraint filters.
-   Intent preservation decision logic.
-   Cache key correctness.
-   Budget estimation.
-   Provider error normalization.
-   Evaluation metrics.
-   Statistical calculations.
-   Optimization selection rules.
-   Serialization and manifest hashing.

### Provider tests

-   Fake/mock adapters for deterministic unit tests.
-   Adapter contract tests.
-   Malformed structured responses.
-   Timeouts.
-   Rate limits.
-   Unsupported capabilities.
-   Retry behavior.
-   Streaming failures.
-   Cancellation.
-   Provider fallback recording.

### Database tests

-   PostgreSQL migrations.
-   Foreign keys and constraints.
-   Transaction boundaries.
-   Version immutability.
-   Suite revision immutability.
-   Concurrent job claims.
-   Worker recovery.
-   Cache uniqueness.
-   Run history integrity.

### Integration tests

-   API → service → PostgreSQL.
-   Prompt creation → versioning → execution.
-   Suite creation → run → evaluation.
-   Optimization → candidate evaluation → selection.
-   SSE reconnect/status retrieval.
-   Cancellation and job failure handling.

### Frontend tests

-   Prompt editor.
-   Version diff.
-   Test suite editor.
-   Run creation and progress.
-   Candidate comparison.
-   Failure and empty states.
-   Safe display of model output.

### End-to-end tests

At minimum:

1.  Create a prompt.
2.  Save a version.
3.  Create a small test suite.
4.  Execute a run with a fake provider.
5.  Inspect per-case and aggregate results.
6.  Optimize using a fake provider.
7.  Verify the original remains a candidate.
8.  Verify the selection logic can choose no change.
9.  Save an accepted candidate as a new version.
10. Verify that the prior version and run remain unchanged.

CI must not require paid inference calls. Use recorded fixtures and fake
providers for deterministic tests. Real-provider smoke tests may be
optional or manually triggered.

Use linting, formatting, static type checking where practical, migration
checks, backend tests, and frontend build/test commands in CI.

Never delete tests merely to make CI pass.

## 26. Security, privacy, and reliability

Treat all prompts, model responses, imported files, test cases, and
retrieved context as potentially untrusted data.

Address:

-   API key leakage.
-   Cross-workspace data access.
-   Prompt injection and judge injection.
-   Cross-site scripting through model output.
-   SQL injection through unsafe queries.
-   SSRF if external URL fetching is ever introduced.
-   Arbitrary file access.
-   Unbounded model-call loops.
-   Expensive evaluation abuse.
-   Provider rate limits.
-   Database connection exhaustion.
-   Oversized request bodies.
-   Unsafe import/export.
-   Secrets accidentally committed to Git.
-   Logs containing sensitive prompt content.

Do not implement arbitrary URL fetching or generated-code execution
merely for convenience.

Use request validation, output encoding, timeouts, rate limits, and
budget guards.

Do not log full prompts and model outputs by default if they may contain
sensitive data. Provide a documented retention/redaction policy.

Use workspace isolation even if initial authentication is simple. Do not
assume a workspace ID supplied by a client proves authorization.

If multi-user authentication is introduced, enforce authorization in the
backend, not just in the frontend.

Provide:

-   `.env.example` with placeholders.
-   `.gitignore` for secrets and generated artifacts.
-   Dependency scanning or equivalent basic supply-chain checks where
    feasible.
-   Security-focused tests.
-   Safe production error messages.
-   A documented backup/restore approach appropriate to the chosen
    database.

## 27. Deployment and local development

The project must work locally before deployment.

Use Docker Compose for a practical development setup where appropriate:

-   React development server or built frontend.
-   Flask API.
-   Background worker.
-   Local PostgreSQL.
-   Optional Nginx reverse proxy for production-like testing.

Use environment variables to switch between local PostgreSQL and the
selected hosted PostgreSQL provider.

Do not require Supabase or Neon credentials to run unit tests.

Do not assume the production environment has a GPU or local model
installed.

Provide configuration for:

-   A hosted compatible model endpoint.
-   A local Ollama endpoint where supported.
-   A local llama.cpp/OpenAI-compatible endpoint where supported.
-   Optional retained Google GenAI configuration.

Document which setup requires which credentials.

Use health checks and readiness checks that distinguish application
health from database connectivity and provider availability.

For production:

-   Use Gunicorn.
-   Configure streaming-compatible proxy behavior if SSE is enabled.
-   Configure worker processes and concurrency deliberately.
-   Keep API and worker entry points distinct.
-   Use non-root containers where practical.
-   Keep secrets out of images.
-   Avoid writing persistent application data into ephemeral container
    storage.
-   Configure database connections within provider limits.
-   Document migrations and deployment order.
-   Test graceful shutdown and job recovery.

Never claim the application is deployed or production-ready just because
Docker builds successfully.

## 28. Implementation phases

Follow these phases in order. Update
`docs/implementation/feature-status.md` after each phase.

### Phase 0 --- Foundation and baseline

Objectives:

-   Audit the existing repository.
-   Establish the target architecture and decisions.
-   Add or stabilize the Python package structure.
-   Configure SQLAlchemy and Alembic.
-   Connect to local PostgreSQL.
-   Verify configuration for the selected hosted PostgreSQL provider.
-   Implement the first minimal coherent schema.
-   Implement the provider abstraction and one working adapter.
-   Preserve the existing FORGE enhancement workflow.
-   Add cache and bounded budget controls.
-   Establish structured errors and logging.
-   Remove misleading or fake metrics after verifying their use.
-   Create approximately 30 benchmark tasks.
-   Compare raw prompts, a generic rewrite, and current FORGE behavior
    using a controlled pilot.
-   Record baseline limitations and evaluation costs.

**Acceptance criteria:**

-   Existing functionality has a documented compatibility status.
-   Application starts locally with documented configuration.
-   PostgreSQL migrations apply cleanly.
-   Data survives application restarts.
-   One configured provider can execute a real request.
-   A fake provider can run the same code path in CI.
-   Provider errors are normalized.
-   Cache keys separate different models and configurations.
-   Budget limits stop excessive work.
-   A small benchmark run creates a reproducible manifest and results.
-   Raw, generic rewrite, and current FORGE are distinguishable
    baselines.
-   Tests pass, or remaining failures are documented with evidence.
-   No unverified performance or quality claims are made.

Do not implement the full optimization platform during Phase 0.

### Phase 1 --- Prompt workspace

Implement:

-   Prompt CRUD.
-   Immutable prompt versions.
-   Textual diff.
-   Restore-as-new-version.
-   Variables and validation.
-   Playground.
-   Execution history.
-   Provider/model selection.
-   Safe streamed execution where supported.

**Acceptance criteria:**

-   A user can create, edit, save, execute, compare, and restore
    prompts.
-   Historical versions and executions remain inspectable.
-   Secrets are not exposed to the browser.
-   Critical flows have automated tests.

### Phase 2 --- Evaluation engine

Implement:

-   Test cases and suite revisions.
-   Deterministic evaluators.
-   Rubric-based evaluation.
-   Pairwise evaluation where appropriate.
-   Run/job lifecycle.
-   Background worker.
-   Per-case and aggregate results.
-   Paired statistical comparisons.
-   Confidence intervals and failure reporting.
-   Budget estimates.
-   Run manifests and cache integration.
-   Regression gates.

**Acceptance criteria:**

-   Evaluation works end-to-end with fake providers.
-   Real provider execution is supported by the same interfaces.
-   Baseline and candidate share the same suite revision.
-   Results can be reproduced from a saved manifest as far as provider
    determinism allows.
-   Invalid or failed cases are reported, not silently discarded.
-   The UI distinguishes inconclusive evidence from a demonstrated
    improvement.

### Phase 3 --- Intent and builder

Implement:

-   IntentSpec.
-   Intent extraction.
-   Requirement provenance.
-   Clarification questions.
-   Hard/soft constraint handling.
-   Scope-drift detection.
-   Intent-preservation report.
-   Prompt analyzer and deterministic linting.
-   Reviewable candidate changes.

**Acceptance criteria:**

-   Explicit requirements are traceable.
-   Assumptions are identified.
-   Material changes are visible.
-   The user can review extracted intent before optimization.
-   Heuristic findings are not represented as guaranteed truth.

### Phase 4 --- Evidence-gated optimization

Implement:

-   Bounded candidate generation.
-   Candidate filtering.
-   Intent-preservation gate.
-   Optional critique.
-   Baseline-versus-candidate evaluation.
-   Statistical selection policy.
-   No-change selection.
-   Change records.
-   Lite and Tested modes.
-   Explicit acceptance and version creation.

**Acceptance criteria:**

-   The baseline is always evaluated and eligible for selection.
-   Lite results are clearly marked unverified.
-   Tested results show the suite, sample size, metrics, failures, and
    uncertainty.
-   Candidates that violate hard constraints are rejected or escalated.
-   Inconclusive results do not become unsupported improvement claims.
-   Optimization cost is bounded and visible.

### Phase 5 --- Benchmark and multi-model study

Implement:

-   Versioned benchmark manifests.
-   Held-out benchmark execution.
-   Raw/generic/expert/iterative/FORGE comparisons.
-   Ablations.
-   Multiple configured target models.
-   Judge configuration and calibration.
-   Exportable reports.
-   Value-for-cost analysis.

**Acceptance criteria:**

-   The benchmark can be executed and reported using documented
    commands.
-   Every result identifies the model and configuration used.
-   The report includes limitations, failures, and uncertainty.
-   No result is described as universal without sufficient evidence.
-   The system supports reporting negative results.

### Phase 6 --- Experiments and polish

Implement:

-   Experiment comparison.
-   Saved evaluation configurations.
-   Versioned evaluator/rubric configuration.
-   Improved search and filtering.
-   Export/import.
-   History and audit views.
-   UI and workflow polish.
-   Performance optimization based on actual measurements.

### Phase 7 --- Developer platform

Only after the core is stable, consider:

-   Public SDK.
-   Deployment workflows.
-   Runtime traces.
-   Additional authentication/team collaboration.
-   External observability integrations.

### Phase 8 --- Research extras

Only with supporting evidence, consider:

-   Multi-agent optimization.
-   Model-specific optimization.
-   Advanced mutation strategies.
-   Feedback-driven improvements.
-   Sandboxed execution.

Do not implement future phases prematurely just because their directory
names appear in the proposed architecture.

## 29. Required engineering documentation

Maintain:

-   `README.md`
-   `docs/architecture/current-state.md`
-   `docs/architecture/target-architecture.md`
-   `docs/architecture/architecture-decisions.md`
-   `docs/implementation/phase-0-plan.md`
-   `docs/implementation/feature-status.md`
-   `docs/implementation/testing.md`
-   `docs/implementation/local-development.md`
-   `docs/implementation/deployment.md`
-   `docs/implementation/database.md`
-   `docs/evaluation/evaluation-methodology.md`
-   `docs/evaluation/benchmark-protocol.md`
-   `docs/evaluation/limitations.md`
-   `docs/security/threat-model.md`
-   `docs/api/openapi.yaml` or an equivalent generated/documented API
    specification.

Document:

-   How to install and run the project.
-   How to configure local PostgreSQL.
-   How to connect Supabase or Neon.
-   How to configure model providers.
-   How to run tests.
-   How to run migrations.
-   How to execute a benchmark.
-   How to reproduce a saved run.
-   How to understand the reported statistics.
-   What is implemented versus planned.
-   Known limitations and failure modes.

Do not claim support for a feature merely because documentation mentions
it.

## 30. Acceptance rules that apply to every phase

A phase is not complete merely because its code has been written.

For each phase:

1.  Identify the scope.
2.  List the files and modules to be changed.
3.  Implement the smallest coherent slice.
4.  Add or update tests.
5.  Run relevant tests.
6.  Run lint/type/build checks as applicable.
7.  Run database migrations against PostgreSQL where applicable.
8.  Inspect failures and fix regressions.
9.  Update documentation.
10. Update feature status.
11. Record remaining limitations.
12. Summarize what was verified.

Do not:

-   Skip failing tests without explanation.
-   Weaken acceptance criteria to match a broken implementation.
-   Replace real logic with mocks outside test boundaries.
-   Add meaningless abstractions.
-   Introduce large dependencies without justification.
-   Overwrite user data.
-   Silently change API contracts.
-   Claim unsupported provider capabilities.
-   Claim benchmark improvements before measuring them.
-   Implement several phases in parallel in a way that obscures
    failures.

Preserve a clean, reviewable Git history where practical. Do not commit,
push, publish secrets, or deploy without explicit authorization.

## 31. Immediate execution instructions

Start now with the repository audit and Phase 0.

**Step 1:** Inspect the actual repository and run the existing checks.

**Step 2:** Create the current-state and target-architecture documents.

**Step 3:** Produce a concise audit report that lists:

-   Verified existing functionality.
-   Existing technical debt.
-   Compatibility requirements.
-   Planned changes.
-   Risks and decisions.
-   Phase 0 tasks and acceptance criteria.

**Step 4:** Implement Phase 0 in small, reviewable increments.

**Step 5:** Configure PostgreSQL from the beginning. Support local
PostgreSQL and prepare configuration for one selected hosted provider,
preferably Supabase or Neon, without introducing a provider-specific
dependency into the domain.

**Step 6:** Implement and test the provider interface, database layer,
cache, budgets, and baseline runner.

**Step 7:** Create the initial approximately 30-task benchmark and
define the baseline comparison protocol. If real model credentials are
unavailable, implement the runner and deterministic fake-provider tests,
clearly mark the real benchmark as **NOT RUN**, and document exactly how
to execute it later.

**Step 8:** Run the complete available test suite, linting, type checks,
build, and PostgreSQL integration checks.

**Step 9:** Update documentation and report the actual results.

Do not begin Phases 1--8 until Phase 0 acceptance criteria have been
reviewed and the foundational code is stable. Do not stop after planning
unless a real blocker exists.

If a critical design decision is unresolved, choose the simplest
reversible option, document it, and proceed. Ask the user only when the
decision is irreversible, requires credentials or external
authorization, risks data loss, or materially changes product direction.

## 32. Final report format

After completing the authorized work, report:

### A. Repository audit

-   Existing architecture.
-   What was retained, modified, and removed.
-   Verified existing behavior and test status.

### B. Phase 0 implementation

-   Features actually implemented.
-   Important architectural decisions.
-   Database configuration and migrations.
-   Provider support.
-   Cache/budget behavior.
-   Baseline and benchmark implementation.

### C. Files changed

-   New files.
-   Modified files.
-   Deleted files, with reasons.

### D. Verification

-   Exact commands executed.
-   Tests passed/failed/skipped.
-   Lint/type/build results.
-   PostgreSQL migration/integration results.
-   Real model calls made, if any.
-   Benchmark results actually obtained, if any.

### E. Remaining work

-   Incomplete requirements.
-   Known limitations.
-   External configuration still required.
-   Unverified features.

### F. Next phase

-   Recommended next phase.
-   Dependencies and acceptance criteria.
-   Why it is safe to proceed.

### G. Honesty check

Explicitly distinguish:

-   Implemented.
-   Tested with fake providers.
-   Tested with real providers.
-   Benchmarked.
-   Not yet verified.

Do not report a successful deployment, real-world model performance, or
benchmark superiority unless the relevant operation was actually
completed.

The objective is not to maximize the number of files or features
generated. The objective is to build a stable foundation for a genuinely
useful, reproducible, evidence-driven prompt engineering platform.

**Begin with the repository audit, then implement Phase 0.**
