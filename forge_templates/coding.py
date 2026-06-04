"""
FORGE – Coding domain templates  [C1 – C15]
"""

from .base import ForgeTemplate

CODING_TEMPLATES: dict[str, ForgeTemplate] = {

    "C1": ForgeTemplate(
        id="C1",
        domain="Coding",
        name="Code Review Checklist",
        description="Systematic multi-tier code quality review",
        triggers=[
            "review code", "audit code", "feedback on code",
            "code quality", "code review", "code audit",
            "check my code", "look at my code",
        ],
        structure="""\
Role: Expert code reviewer with deep knowledge of software engineering best practices.

OUTPUT SECTIONS (in order):

1. SEVERITY TIERS — for each issue found, provide:
   • Tier: Critical / High / Medium / Low
   • Issue: concise name
   • Location: file + line reference
   • Impact: what breaks or degrades if unaddressed
   • Explanation: WHY it is a problem (not just what it is)
   • Recommendation: specific corrective action with code snippet if applicable

2. SUMMARY
   • Total issue counts per severity tier
   • Top 3 priorities (ordered, with one-line rationale each)
   • Overall quality score (1–10) with justification

RULES:
- Be precise about locations; never give vague feedback.
- Prioritize correctness > security > maintainability > style.
- Acknowledge what is done well (min 2 positives).
""",
    ),

    "C2": ForgeTemplate(
        id="C2",
        domain="Coding",
        name="Bug Triage Analysis",
        description="Structured debugging from symptom to fix to prevention",
        triggers=[
            "debug", "fix bug", "bug", "error", "unexpected behavior",
            "troubleshoot", "broken", "crash", "not working",
            "exception", "stack trace", "failing", "breaks",
        ],
        structure="""\
Role: Senior debugging specialist with expertise in systematic fault isolation.

OUTPUT SECTIONS (in order):

1. SYMPTOM ANALYSIS
   • Observed behavior (exact, quoting error messages if present)
   • Conditions that trigger the bug (always / intermittent / environment-specific)
   • Recent changes that may be correlated

2. HYPOTHESIS GENERATION
   • List 3–5 ranked probable root causes
   • For each: reasoning chain that connects it to the symptom

3. DIAGNOSTIC STEPS
   • Numbered step-by-step investigation plan
   • Each step: action + what a positive result confirms + what a negative result refutes

4. ROOT CAUSE IDENTIFICATION
   • Most likely root cause with confidence level (High / Medium / Low)
   • Evidence that supports this conclusion

5. SOLUTION IMPLEMENTATION
   • Code-level fix with before/after snippets
   • Explanation of why the fix addresses the root cause

6. PREVENTIVE MEASURES
   • 2–3 coding/process changes that prevent this class of bug in future
""",
    ),

    "C3": ForgeTemplate(
        id="C3",
        domain="Coding",
        name="Refactoring Plan",
        description="Phased refactoring roadmap with risk controls",
        triggers=[
            "refactor", "improve code quality", "clean up code",
            "reduce technical debt", "restructure", "code smell",
            "cleanup", "rewrite", "simplify code",
        ],
        structure="""\
Role: Software architect specializing in incremental, risk-controlled refactoring.

OUTPUT SECTIONS (in order):

1. CODE SMELL DETECTION TABLE
   Columns: Smell | Location | Severity (High/Med/Low) | Impact | Rationale

2. PATTERN RECOMMENDATIONS
   • Per smell: before-code snippet → after-code snippet with inline comments
   • Name the design pattern or principle applied (e.g., SRP, DRY, Strategy Pattern)

3. PHASED ROADMAP
   • Phase 1 (Quick Wins), Phase 2 (Structural), Phase 3 (Deep Refactors)
   • Each phase: Objective | Effort estimate | Risk level | Changes | Test checklist | Rollback plan | Success criteria

4. INTERDEPENDENCIES
   • Components that must change together
   • Ordering constraints between phases

5. MONITORING & VALIDATION
   • Metrics to verify quality improved (cyclomatic complexity, test coverage, build time)
   • Regression test strategy
""",
    ),

    "C4": ForgeTemplate(
        id="C4",
        domain="Coding",
        name="Test Generation",
        description="Comprehensive test suite: happy path, edge cases, mocks",
        triggers=[
            "write tests", "unit tests", "test suite", "integration tests",
            "test coverage", "tdd", "testing", "test cases",
            "write unit test", "add tests", "jest", "pytest", "mocha",
        ],
        structure="""\
Role: Senior test engineer applying TDD and behavior-driven design principles.

OUTPUT SECTIONS (in order):

1. TEST STRATEGY
   • Overall approach (unit / integration / E2E mix)
   • Edge cases identified upfront
   • Mocking / stubbing strategy

2. HAPPY PATH TESTS
   • Normal usage scenarios; each test: name + arrange/act/assert structure

3. EDGE CASE TESTS
   • Boundary values, empty inputs, max limits, type coercions
   • Each test clearly labelled with the edge condition being exercised

4. ERROR HANDLING TESTS
   • Expected exceptions, timeout behaviour, invalid state transitions

5. INTEGRATION TESTS
   • Cross-component flows; real or realistic dependencies

6. MOCK DEFINITIONS
   • Setup and teardown for all mocks/stubs/spies

7. COVERAGE NOTES
   • What each test validates and why it matters for production safety
""",
    ),

    "C5": ForgeTemplate(
        id="C5",
        domain="Coding",
        name="Documentation Generator",
        description="README, API docs, or inline docstrings — audience-calibrated",
        triggers=[
            "write docs", "readme", "api documentation", "inline comments",
            "developer guide", "docstrings", "documentation",
            "write documentation", "document this", "add docstrings",
        ],
        structure="""\
Role: Technical documentation expert who writes for future maintainers, not the original author.

CHOOSE THE APPLICABLE FORM(S) AND FOLLOW ITS RULES:

README FORMAT:
  • One-sentence description (what + for whom)
  • Why this project exists (problem it solves)
  • Minimal working example (copy-paste runnable)
  • Installation / setup steps
  • Configuration reference
  • Contributing guidelines stub

API DOCUMENTATION FORMAT:
  • Function/endpoint purpose (one sentence)
  • Parameters table: name | type | required | default | description
  • Return value: type + shape
  • 2–3 usage examples (different scenarios)
  • All error/exception cases with HTTP status or exception type

INLINE COMMENTS FORMAT:
  • Explain WHY, never WHAT (what is visible from the code itself)
  • Flag non-obvious assumptions and trade-offs
  • Note ticket/spec references for business-logic decisions
  • Use single-line for brief context; block comments for complex reasoning
""",
    ),

    "C6": ForgeTemplate(
        id="C6",
        domain="Coding",
        name="API Design Review",
        description="REST/GraphQL API evaluation with actionable improvement plan",
        triggers=[
            "review api", "evaluate api", "api design", "rest design",
            "graphql design", "endpoint naming", "api feedback",
            "api review", "check my api", "api structure",
        ],
        structure="""\
Role: API architect with expertise in REST, GraphQL, and developer-experience design.

OUTPUT SECTIONS (in order):

1. STRENGTHS  (2–3 with specific rationale each)

2. AREAS FOR IMPROVEMENT
   • Per issue: Problem | Why it matters to consumers | Recommended change (with example)

3. IMPLEMENTATION PRIORITY
   • Ordered list: High (breaking/critical) | Medium (DX improvements) | Nice-to-Have

4. DESIGN CHECKLIST
   Evaluate and score (Pass / Partial / Fail) each:
   □ Naming consistency (nouns for resources, verbs for actions)
   □ Error response structure (code + message + details)
   □ Pagination strategy
   □ Authentication & authorisation headers
   □ Rate-limiting headers
   □ Versioning strategy
   □ Correct HTTP status codes
   □ Idempotency for mutating operations
""",
    ),

    "C7": ForgeTemplate(
        id="C7",
        domain="Coding",
        name="Performance Optimization",
        description="Bottleneck analysis with ranked, quantified optimizations",
        triggers=[
            "slow code", "optimize", "speed up", "performance",
            "bottleneck", "latency", "inefficient", "o(n²)",
            "too slow", "high cpu", "memory usage", "throughput",
        ],
        structure="""\
Role: Performance analyst and systems engineer with expertise in profiling and algorithmic optimisation.

OUTPUT SECTIONS (in order):

1. EXECUTIVE SUMMARY
   • Top 2–3 bottlenecks in plain language; projected overall impact

2. PER BOTTLENECK ANALYSIS
   For each bottleneck:
   • Problem: describe with Big-O complexity or measured metric
   • Impact: quantified if possible (e.g., "accounts for ~70% of latency")
   • 3 Optimisation Options ranked by impact:
       Option A (Highest Impact): description + code example
       Option B (Medium):         description + code example
       Option C (Low-effort):     description + code example

3. CODE EXAMPLES
   Full before/after implementation for the top recommendation

4. PRIORITISED ACTION PLAN
   Ordered steps with estimated effort (hours/days) and expected gain

5. TRADE-OFF NOTES
   • Memory vs speed, readability vs performance, correctness risks
""",
    ),

    "C8": ForgeTemplate(
        id="C8",
        domain="Coding",
        name="Code Explanation",
        description="Three-level code walkthrough from overview to line-by-line",
        triggers=[
            "explain code", "understand code", "what does this do",
            "how does this work", "walk me through", "explain this",
            "what is this code doing", "break down this code",
        ],
        structure="""\
Role: Code educator who adapts explanations to different levels of technical depth.

OUTPUT SECTIONS (in order):

1. LEVEL 1 — BIG PICTURE (Plain English)
   • What this code does, in one paragraph a non-programmer could grasp
   • Why it exists (the problem it solves)
   • The major components / modules involved

2. LEVEL 2 — EXECUTION WALKTHROUGH
   • Step-by-step execution flow (numbered)
   • Key decisions and branching logic
   • Data transformations: input shape → output shape
   • External dependencies and side effects

3. LEVEL 3 — LINE-BY-LINE DEEP DIVE
   • Annotate non-obvious syntax, idioms, and patterns
   • Explain edge cases handled (and unhandled)
   • Note any implicit assumptions in the code

4. TRICKY PARTS HIGHLIGHT
   • Explicitly call out any gotchas, subtle bugs risks, or clever tricks
""",
    ),

    "C9": ForgeTemplate(
        id="C9",
        domain="Coding",
        name="Error Handling Improvement",
        description="User-centric error messages with root cause and recovery steps",
        triggers=[
            "error messages", "improve errors", "user-friendly errors",
            "exception handling", "error ux", "better error messages",
            "error handling", "error design",
        ],
        structure="""\
Role: Error message architect focused on developer and end-user experience.

OUTPUT SECTIONS — for each error type:

1. ERROR TYPE & CODE
   • Machine-readable error code (e.g., ERR_AUTH_TOKEN_EXPIRED)
   • HTTP status code if applicable

2. USER-FACING EXPLANATION
   • Plain language, zero jargon
   • What happened (not what the system did internally)

3. WHY THIS HAPPENED
   • Most common root causes (non-blaming, factual tone)

4. WHAT TO DO NEXT
   • 2–4 numbered, actionable recovery steps in order of likelihood to succeed

5. EMPATHETIC CLOSING
   • One sentence acknowledging the inconvenience if user-facing
   • Link to support/docs if applicable

TONE RULES: Clear, calm, helpful. Never expose stack traces to end users. Never say "invalid" without saying what is valid.
""",
    ),

    "C10": ForgeTemplate(
        id="C10",
        domain="Coding",
        name="Security Audit",
        description="OWASP-aligned vulnerability review with remediated code",
        triggers=[
            "security review", "vulnerabilities", "owasp",
            "penetration test", "security audit", "sql injection",
            "xss", "auth issues", "security issues", "insecure",
            "security vulnerability", "csrf",
        ],
        structure="""\
Role: Application security auditor with OWASP Top 10 expertise.

OUTPUT SECTIONS — per vulnerability found:

1. VULNERABILITY PROFILE
   • Name
   • OWASP Classification (e.g., A03:2021 – Injection)
   • Severity: Critical / High / Medium / Low / Informational
   • Affected location (file + function + line)

2. RISK EXPLANATION
   • What an attacker could do (business impact, not just technical)
   • Accessible language — assume a non-security engineering audience

3. VULNERABLE CODE (as-is, labelled)

4. REMEDIATED CODE (with inline security comments explaining each change)

5. PREVENTION GUIDELINES
   • 2–3 actionable, specific steps to prevent this class of vulnerability

CLOSING:
• Acknowledge security positives found (e.g., proper password hashing, HTTPS enforcement)
• Recommend a severity-prioritised fix order
""",
    ),

    "C11": ForgeTemplate(
        id="C11",
        domain="Coding",
        name="Code Migration Guide",
        description="Phased migration strategy with rollback and risk controls",
        triggers=[
            "migrate code", "upgrade version", "breaking changes",
            "move to new framework", "port codebase", "migration",
            "upgrade framework", "upgrade library", "v2", "upgrade to",
        ],
        structure="""\
Role: Migration specialist with experience in large-scale codebase transitions.

OUTPUT SECTIONS (in order):

1. BREAKING CHANGES IDENTIFICATION
   Table: Change | Why it breaks | Affected components | Severity | Impact radius

2. MIGRATION STRATEGY
   • Preparation phase: inventory, test baseline, feature flags
   • Execution phase: ordered steps, go/no-go checkpoints
   • Validation phase: regression testing, performance comparison
   • Cleanup phase: remove deprecated code, update docs

3. TESTING STRATEGY
   • Unit, integration, regression, performance, smoke tests
   • Specific assertions that confirm migration success

4. RISK MITIGATION
   • Top 3 risks with probability and mitigation action
   • Rollback procedures: step-by-step, with trigger conditions

5. IMPLEMENTATION CHECKLIST
   Binary [ ] items covering all phases
""",
    ),

    "C12": ForgeTemplate(
        id="C12",
        domain="Coding",
        name="TypeScript Conversion",
        description="JavaScript to TypeScript with type guards, generics, and explanations",
        triggers=[
            "convert to typescript", "add types", "typescript migration",
            "js to ts", "type safety", "typescript", "add typescript",
            "migrate to typescript",
        ],
        structure="""\
Role: TypeScript expert specialising in safe, incremental JS-to-TS migrations.

OUTPUT SECTIONS (in order):

1. FULLY TYPED IMPLEMENTATION
   • Complete converted code with:
     - Interface and type definitions for all data shapes
     - Strict function signatures (param types + return types)
     - Generics where reusability warrants it
     - Type guards for runtime narrowing
   • Inline comments explaining non-obvious type decisions

2. TYPE SAFETY IMPROVEMENTS
   Table: Improvement | Specific benefit | Risk prevented

3. TYPE GUARD EXPLANATIONS
   • For each type guard: what it narrows, why runtime check is needed

4. GENERIC PATTERNS USED
   • List each generic with its purpose and usage example

5. MIGRATION NOTES
   • tsconfig.json recommended settings
   • Files to migrate first (least-dependent → most-dependent)
   • Known any/unknown escape hatches that need future attention
""",
    ),

    "C13": ForgeTemplate(
        id="C13",
        domain="Coding",
        name="Database Schema Review",
        description="Normalisation, indexing, and query-pattern optimisation audit",
        triggers=[
            "review schema", "database design", "normalization",
            "indexes", "foreign keys", "db schema", "schema review",
            "database schema", "sql schema", "table design",
        ],
        structure="""\
Role: Database architect with expertise in relational schema design, normalisation, and query performance.

OUTPUT SECTIONS (in order):

1. EXECUTIVE SUMMARY  (2–3 sentences)

2. NORMALISATION ASSESSMENT
   • Current normal form achieved
   • Any justified denormalisation (with rationale)
   • Violations to address

3. INDEX STRATEGY REVIEW
   • Effective indexes (keep)
   • Recommended new indexes (with CREATE INDEX SQL + rationale)
   • Redundant/duplicate indexes to drop

4. RELATIONSHIP DESIGN
   • Primary key choices (natural vs surrogate)
   • Foreign key enforcement gaps
   • Referential integrity issues

5. QUERY PATTERN OPTIMISATION
   • 2–3 common query patterns and how the schema supports or hinders them

6. PRIORITISED RECOMMENDATIONS
   Tiers: High (correctness/integrity) | Medium (performance) | Low (style/convention)
   Each with SQL example demonstrating the improvement
""",
    ),

    "C14": ForgeTemplate(
        id="C14",
        domain="Coding",
        name="Architecture Decision Record",
        description="Structured ADR documenting context, options, decision, and consequences",
        triggers=[
            "adr", "architecture decision", "compare technologies",
            "document tech choice", "technical decision",
            "architecture record", "tech decision", "choose framework",
            "choose technology", "tech comparison",
        ],
        structure="""\
Role: Technical architect producing a formal Architecture Decision Record (ADR).

ADR STRUCTURE:

1. METADATA
   • Title | Status (Proposed / Accepted / Deprecated / Superseded) | Date | Deciders

2. CONTEXT
   • Problem statement and technical constraints
   • Business/technical drivers
   • Stakeholders affected

3. OPTIONS CONSIDERED  (2–4 options)
   Per option: Name | Description | Pros | Cons | Effort estimate | Risk level

4. DECISION
   • Chosen option
   • Primary reason in one sentence

5. RATIONALE
   • Technical reasoning in depth
   • Long-term architectural implications
   • Alignment with existing system principles

6. CONSEQUENCES
   • Positive outcomes expected
   • Risks and mitigations
   • Resources required and timeline
   • What becomes harder or easier

7. ALTERNATIVES REJECTED
   • Brief note on why each non-chosen option was eliminated
""",
    ),

    "C15": ForgeTemplate(
        id="C15",
        domain="Coding",
        name="Code Comment Generator",
        description="WHY-focused inline comments for future maintainers",
        triggers=[
            "add comments", "explain why", "comment this code",
            "document decisions", "annotation", "code comments",
            "add annotations", "comment my code",
        ],
        structure="""\
Role: Documentation specialist writing comments for future maintainers who have zero context.

COMMENT RULES:
  • Explain WHY, never WHAT (the code already shows what)
  • Never restate syntax ("// increment i by 1" is forbidden)

PER CODE BLOCK, INCLUDE:
  1. Intent — what this block is trying to accomplish
  2. Trade-offs — why this approach was chosen over alternatives
  3. Business Logic — links to specs, tickets, or domain rules
  4. Context — relevant constraints (e.g., "must match legacy API contract")
  5. Non-obvious behaviour — gotchas, timing dependencies, ordering requirements

FORMAT RULES:
  • Single-line comment (#, //) for brief context on a single expression
  • Block comment (docstring / JSDoc / /** */) for functions, classes, and complex algorithms
  • Mark future improvement debt with TODO: or FIXME: and a ticket reference

OUTPUT: Fully commented version of the provided code.
""",
    ),
}