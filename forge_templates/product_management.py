"""
FORGE – Product Management domain templates  [P1 – P15]
"""

from .base import ForgeTemplate

PRODUCT_MANAGEMENT_TEMPLATES: dict[str, ForgeTemplate] = {

    "P1": ForgeTemplate(
        id="P1",
        domain="Product Management",
        name="Product Requirements Doc Generator",
        description="Full PRD with personas, acceptance criteria, metrics, and risk register",
        triggers=[
            "prd", "product requirements", "feature spec",
            "product specification", "write requirements", "product document",
            "product requirement document", "feature requirements",
        ],
        structure="""\
Role: Senior product manager writing a production-ready Product Requirements Document.

OUTPUT SECTIONS (in order):

1. EXECUTIVE SUMMARY
   • Feature name | One-sentence description | Business problem | Key benefits | Strategic alignment

2. USER PERSONAS  (2–3)
   Per persona: Name | Role | Background | Goals | Pain points | Current workarounds | Success criteria

3. FEATURE SPECIFICATIONS
   • Core user flows (step-by-step)
   • Acceptance criteria per component (Given/When/Then format)
   • Explicitly out-of-scope items
   • Dependencies on other teams/features

4. SUCCESS METRICS
   • Quantifiable targets (not vague goals)
   • Measurement method and data source per metric
   • Baseline (current state) vs target

5. TIMELINE & PHASES
   • Phases with milestone descriptions
   • Go/no-go criteria between phases

6. TECHNICAL CONSTRAINTS
   • Architecture implications
   • Performance requirements
   • Security and compliance considerations
   • Scalability considerations
   • Known technical risks

7. RISKS & MITIGATION
   Table: Risk | Probability | Impact | Mitigation | Owner
""",
    ),

    "P2": ForgeTemplate(
        id="P2",
        domain="Product Management",
        name="Competitive Analysis Matrix (PM)",
        description="Feature-level competitive matrix with positioning map and strategic insights",
        triggers=[
            "product competitive analysis", "compare product features",
            "feature comparison matrix", "product benchmarking",
            "product comparison", "competitive feature analysis",
        ],
        structure="""\
Role: Product strategist building an actionable competitive intelligence matrix.

OUTPUT SECTIONS (in order):

1. DIMENSION DEFINITION
   6–8 competitive dimensions most important to buyers, with rationale for each

2. COMPETITOR MATRIX TABLE
   Rows: Competitors | Columns: Dimensions
   Use specific assessments (not just ✓/✗); include your product for comparison

3. STRENGTH / WEAKNESS SUMMARY  (per competitor)
   • Top 3 strengths with evidence
   • Top 3 weaknesses with evidence
   • Primary positioning statement (one sentence)

4. MARKET POSITIONING MAP
   • 2×2 map on the two most critical dimensions
   • Identify white-space opportunities and crowded segments

5. ACTIONABLE INSIGHTS
   3–5 strategic recommendations:
   • Differentiation opportunities
   • Vulnerable competitor segments to target
   • Features to deprioritise (table stakes) vs invest in (differentiators)
   • Risks if competitors close current gaps
""",
    ),

    "P3": ForgeTemplate(
        id="P3",
        domain="Product Management",
        name="User Story to Acceptance Criteria",
        description="BDD-style Given/When/Then scenarios with performance baselines and test strategy",
        triggers=[
            "acceptance criteria", "user story", "definition of done",
            "test cases for user story", "bdd", "given when then",
            "write acceptance criteria", "user story criteria",
        ],
        structure="""\
Role: Business analyst translating user stories into testable, precise acceptance criteria.

OUTPUT SECTIONS (in order):

1. CORE INTENT EXTRACTION
   • User need: what the user is fundamentally trying to accomplish
   • Business value: why this matters to the organisation
   • Success metric: how we know this feature is working

2. GIVEN-WHEN-THEN SCENARIOS  (3–5 in Gherkin format)
   • Happy path (primary flow)
   • 2–3 critical alternative paths
   • Key error/failure scenario

3. EDGE CASES  (5–8)
   Cover: Empty state | Max limits | Invalid inputs | Concurrent access | Permission denials | Network failures | Timeout behaviour

4. PERFORMANCE BASELINES
   • P95 latency target
   • Throughput requirement
   • Memory/resource constraints
   • SLA if applicable

5. TESTING STRATEGY
   • Unit, integration, E2E, performance — what to test at each level
   • Specific assertions that confirm the scenario passes

6. BINARY ACCEPTANCE CHECKLIST
   [ ] items — each clearly pass/fail, no ambiguity
""",
    ),

    "P4": ForgeTemplate(
        id="P4",
        domain="Product Management",
        name="Roadmap Prioritization Framework",
        description="Weighted scoring, dependency mapping, quarterly roadmap, and capacity planning",
        triggers=[
            "prioritize features", "product roadmap", "score features",
            "roadmap planning", "rank initiatives", "quarterly roadmap",
            "feature prioritization", "roadmap prioritisation",
        ],
        structure="""\
Role: Strategic product manager building a defensible, capacity-aware roadmap.

OUTPUT SECTIONS (in order):

1. WEIGHTED SCORING ANALYSIS
   Formula: Score = (Impact × w1) + (Demand × w2) + (Strategic Alignment × w3) + (Ease × w4)
   • Score each initiative 1–10 per dimension
   • Show weighting rationale
   • Rank all initiatives by final score

2. DEPENDENCY MAP
   Per initiative: What it blocks | What blocks it | Risk if delayed

3. QUARTERLY ROADMAP  (Q1–Q4)
   Per quarter: Strategic theme | 2–3 initiatives | Key milestones | Success metrics

4. CAPACITY PLANNING
   • Initiatives per quarter vs team capacity
   • Recommended buffer % (suggest 20%)
   • Critical path identification
   • Parallel work tracks

5. RISK ASSESSMENT
   • High-risk items (complexity / dependency / external factors)
   • Bottleneck initiatives
   • Sequencing recommendation to de-risk the roadmap
""",
    ),

    "P5": ForgeTemplate(
        id="P5",
        domain="Product Management",
        name="Go-to-Market Strategy Plan",
        description="Full GTM plan: segments, messaging, pricing, channels, and 12-month launch timeline",
        triggers=[
            "go to market", "gtm strategy", "product launch plan",
            "market entry", "launch strategy", "how to launch",
            "go-to-market", "product launch strategy",
        ],
        structure="""\
Role: Go-to-market strategist translating product value into market traction.

OUTPUT SECTIONS (in order):

1. TARGET SEGMENTS  (2–3 primary + secondary for expansion)
   Per segment: TAM estimate | Willingness to pay signals | Buying process | Competitive landscape in this segment
   Prioritisation rationale

2. MESSAGING FRAMEWORK
   • Core value proposition (one sentence)
   • Segment-specific messaging variants
   • 3–5 proof points for each message
   • Competitive positioning story
   • Stakeholder-specific messaging (end user / buyer / champion / executive)

3. PRICING STRATEGY
   • Model (per seat / usage / flat / freemium)
   • Price points with justification
   • Packaging tiers
   • Revenue projections: Year 1 (conservative / base / optimistic)

4. DISTRIBUTION CHANNELS  (3–4)
   Per channel: How it works | Target customer profile | Estimated conversion rate | CAC | Time to first revenue | Unit economics

5. LAUNCH TIMELINE  (12 months)
   Phases: Pre-launch | Soft launch | Full launch | Expansion
   Per phase: activities | milestones | resources required | go/no-go criteria

6. SUCCESS KPIs
   Leading indicators (early signals) | Lagging indicators (outcomes)
   Targets with measurement cadence | Pivot triggers
""",
    ),

    "P6": ForgeTemplate(
        id="P6",
        domain="Product Management",
        name="Feature Impact Analysis",
        description="Business case with adoption forecasts, revenue impact, ROI, and risk factors",
        triggers=[
            "feature impact", "business case for feature", "roi of feature",
            "justify feature investment", "adoption forecast", "feature value",
            "feature business case", "feature roi",
        ],
        structure="""\
Role: Business impact analyst quantifying the value of product investments.

OUTPUT SECTIONS (in order):

1. EXECUTIVE SUMMARY  (2–3 sentences + recommendation)

2. FEATURE OVERVIEW & ASSUMPTIONS
   • Feature description
   • Key assumptions with confidence levels

3. USER ADOPTION ANALYSIS
   • Year 1 and Year 2 projections with confidence levels (low/mid/high)
   • Staged adoption curve and inflection points
   • Adoption drivers and barriers

4. REVENUE IMPACT
   • Year 1 / 2 / 3 incremental revenue by driver
   • Sensitivity analysis: impact of ±25% adoption variance

5. CHURN IMPACT
   • Baseline churn rate
   • Projected churn reduction with this feature
   • LTV improvement per cohort
   • 3-year cumulative benefit

6. INVESTMENT & ROI
   • Development cost (story points × team cost)
   • Launch and ongoing operational costs
   • ROI at 6 months / 12 months / 36 months
   • Payback period
   • NPV at 10% discount rate

7. KEY ASSUMPTIONS TABLE
   Assumption | Impact if Wrong | Confidence | How to Validate

8. RISK FACTORS + RECOMMENDATION
""",
    ),

    "P7": ForgeTemplate(
        id="P7",
        domain="Product Management",
        name="Customer Feedback Synthesis",
        description="Thematic feedback analysis with sentiment, feature matrix, and prioritised recommendations",
        triggers=[
            "analyze customer feedback", "synthesize feedback",
            "customer insights", "feedback themes", "what customers are saying",
            "feedback analysis", "synthesise feedback",
        ],
        structure="""\
Role: Customer insights analyst distilling feedback into strategic product direction.

OUTPUT SECTIONS (in order):

1. THEMATIC ANALYSIS  (5–8 themes)
   Per theme: Theme name | Frequency count | Sentiment (Positive/Mixed/Negative) | 2–3 representative quotes

2. SENTIMENT SUMMARY
   • Overall: Positive / Neutral / Negative % with qualitative context
   • Trend: improving / stable / declining

3. SENTIMENT BY THEME TABLE
   Rows: themes | Columns: Positive % | Neutral % | Negative % | Key driver

4. FEATURE REQUESTS PRIORITISATION MATRIX
   3×3 grid: Impact (High/Med/Low) vs Effort (High/Med/Low)
   Plot each requested feature/improvement

5. ACTIONABLE RECOMMENDATIONS  (numbered 1–7)
   Per recommendation: Action | Priority (H/M/L) | Owner team | Timeline estimate | Success metric
""",
    ),

    "P8": ForgeTemplate(
        id="P8",
        domain="Product Management",
        name="Product Metrics Dashboard",
        description="KPI framework with stakeholder views, anomaly detection, and technical spec",
        triggers=[
            "product metrics", "kpis for product", "product analytics",
            "metrics framework", "what to measure for product",
            "product kpis", "product dashboard metrics",
        ],
        structure="""\
Role: Product metrics architect designing measurement systems that drive decisions.

OUTPUT SECTIONS (in order):

1. KPI FRAMEWORK
   Categories: Acquisition | Engagement | Retention | Monetisation | Operational Health
   Per KPI: Name | Definition | Formula | Data source | Business relevance | Update frequency

2. VISUALISATION STRATEGY  (per KPI)
   Chart type | Time granularity | Colour coding for thresholds

3. STAKEHOLDER VIEWS  (4–6 role-specific dashboards)
   Roles: C-suite | PM | Engineering | Marketing | Customer Success | Finance
   Per role: 5–8 KPIs | Narrative flow | Drill-down capabilities

4. ANOMALY DETECTION RULES  (3–5 critical metrics)
   Per metric: Absolute threshold | Relative threshold (% WoW/MoM) | Severity | Escalation path | False-positive mitigation

5. TECHNICAL CONSIDERATIONS
   Data pipeline requirements | Query performance | Access control | Refresh SLAs
""",
    ),

    "P9": ForgeTemplate(
        id="P9",
        domain="Product Management",
        name="Technical Debt Assessment",
        description="Debt prioritisation matrix, refactoring roadmap, and business case for engineering investment",
        triggers=[
            "technical debt", "assess tech debt", "engineering velocity",
            "refactoring investment", "prioritize engineering work", "debt payoff",
            "tech debt assessment", "engineering debt",
        ],
        structure="""\
Role: Technical debt analyst bridging engineering and business perspectives.

OUTPUT SECTIONS (in order):

1. EXECUTIVE SUMMARY
   Key findings + top recommendation in 2–3 sentences

2. PRIORITISATION MATRIX  (2×2)
   Axes: Velocity Impact (H/L) vs Implementation Effort (H/L)
   Plot all debt items with label and rationale for placement

3. DETAILED ITEM ANALYSIS  (per debt item)
   Name | Velocity impact % | Estimated story points | Dependencies | Priority tier

4. REFACTORING ROADMAP
   Gantt-style phases with: objectives | milestones | dependencies | go/no-go gates

5. BUSINESS CASE & ROI
   • Current engineering velocity baseline
   • Projected velocity post-remediation
   • % improvement
   • 6-month and 12-month ROI
   • Risk mitigation value (incidents avoided, security improvements)

6. TOP 3 RECOMMENDATIONS
   Each with: specific next step | owner | timeline | success criterion
""",
    ),

    "P10": ForgeTemplate(
        id="P10",
        domain="Product Management",
        name="Pricing Strategy Optimization",
        description="Competitive benchmark, WTP analysis, tier design, and revenue projections",
        triggers=[
            "pricing strategy", "set pricing", "pricing tiers",
            "optimize price", "willingness to pay", "pricing model",
            "pricing optimization", "product pricing",
        ],
        structure="""\
Role: Pricing consultant combining behavioural economics with competitive market analysis.

OUTPUT SECTIONS (in order):

1. COMPETITIVE BENCHMARK ANALYSIS
   • 5–8 competitor pricing map with positioning analysis
   • White-space and crowded price points

2. WILLINGNESS-TO-PAY ASSESSMENT
   • Demand curve by segment
   • Price sensitivity inflection points
   • Value drivers that justify premium pricing

3. RECOMMENDED TIER STRUCTURE
   Table: Tier name | Price | Target segment | Key features | Core value proposition

4. TIER VALUE ALIGNMENT
   Per tier: ROI metrics the customer achieves | Feature justification | Customer outcomes

5. REVENUE PROJECTIONS
   Scenarios: Conservative | Base | Optimistic
   Per scenario: CAC assumptions | Retention rates | Year 1 / 2 / 3 revenue | Gross margin %

6. IMPLEMENTATION ROADMAP
   • Launch sequencing strategy
   • Customer communication plan
   • Monitoring metrics and review cadence
   • Go/no-go price adjustment criteria

7. STRATEGIC RECOMMENDATIONS
   Packaging philosophy | Freemium considerations | Annual vs monthly discount strategy
""",
    ),

    "P11": ForgeTemplate(
        id="P11",
        domain="Product Management",
        name="User Research Plan",
        description="Research plan with methodology selection, recruitment criteria, interview guides, and analysis framework",
        triggers=[
            "user research", "research plan", "ux research",
            "usability study", "how to research users",
            "research questions for product", "user interviews",
            "user research plan",
        ],
        structure="""\
Role: User research strategist designing studies that reduce product risk and validate direction.

OUTPUT SECTIONS (in order):

1. RESEARCH OBJECTIVES
   • What to learn (specific, not generic)
   • Why it matters now (decision it informs)
   • Success criteria for the research itself

2. METHODOLOGY SELECTION
   • Recommended methods with justification
   • Qualitative vs quantitative trade-offs
   • Hybrid approach if warranted

3. PARTICIPANT RECRUITMENT
   • Screening criteria (must-haves vs nice-to-haves)
   • Sample size with power/saturation rationale
   • Recruitment channels
   • Incentive recommendation

4. INTERVIEW / TEST GUIDES
   • Opening questions (warm-up)
   • Core research questions (open-ended, non-leading)
   • Follow-up probe examples
   • Closing questions

5. ANALYSIS FRAMEWORK
   • Coding scheme for qualitative data
   • Synthesis approach (affinity mapping, themes)
   • Pattern identification criteria

6. KEY QUESTIONS TO ANSWER
   Explicit list: what must we know by end of this research?

7. INTEGRATION SUMMARY
   How research outputs connect to product decisions and next steps
""",
    ),

    "P12": ForgeTemplate(
        id="P12",
        domain="Product Management",
        name="Product Release Checklist",
        description="End-to-end release management checklist with go/no-go gates and rollback plan",
        triggers=[
            "release checklist", "launch checklist", "deployment checklist",
            "release management", "go-live checklist",
            "product release", "launch readiness",
        ],
        structure="""\
Role: Release manager ensuring safe, coordinated, reversible product launches.

OUTPUT SECTIONS (in order):

1. PRE-LAUNCH TASKS
   [ ] Binary checklist items
   Each: Task | Owner | Dependency | Acceptance criterion

2. STAKEHOLDER COMMUNICATIONS
   • Internal notifications (engineering / support / sales / marketing)
   • External communications (users / customers if applicable)
   • Template language for each communication

3. QA GATES
   • Automated test pass criteria
   • Manual QA sign-off requirements
   • Performance test pass/fail thresholds

4. DOCUMENTATION REQUIREMENTS
   [ ] Internal docs (runbook, architecture, on-call guide)
   [ ] External docs (release notes, help articles, API changelog)

5. ROLLBACK PROCEDURES
   • Trigger conditions (what metrics indicate a bad release)
   • Step-by-step rollback actions
   • Data migration reversal if applicable
   • Communication plan during rollback

6. POST-LAUNCH MONITORING
   • Metrics to watch in first 24 / 72 hours
   • Incident response escalation path
   • Success declaration criteria

7. GO / NO-GO DECISION TABLE
   Critical gate | Criteria | Owner | Status (Pass / Fail / Pending)
""",
    ),

    "P13": ForgeTemplate(
        id="P13",
        domain="Product Management",
        name="Feature Deprecation Strategy",
        description="User migration plan, timeline, support strategy, and churn risk monitoring",
        triggers=[
            "deprecate feature", "sunset feature", "remove feature",
            "migrate users off feature", "feature retirement",
            "feature deprecation", "sunset product",
        ],
        structure="""\
Role: Product strategist managing feature deprecations while protecting user trust.

OUTPUT SECTIONS (in order):

1. USER COMMUNICATION PLAN
   • Announcement messaging: why + what's next (empathetic, solution-forward)
   • Multi-channel communication timeline (in-app / email / docs / support)
   • FAQ addressing top objections
   • Escalation path for power users and enterprise accounts

2. MIGRATION PATH RECOMMENDATIONS
   • Step-by-step alternatives for each use case the deprecated feature served
   • Data export options if applicable
   • Feature comparison: deprecated vs replacement
   • Guidance per user segment (power user / casual / enterprise)

3. TIMELINE & PHASES
   Date-specific:
   • Announcement date
   • Transition period start (with full support)
   • Deprecation date (feature disabled by default)
   • Final sunset date (feature removed)

4. SUPPORT CONSIDERATIONS
   • Dedicated support channels during transition
   • Training resources and documentation
   • Enterprise / high-value account white-glove handling
   • KB articles and in-app guidance

5. SUCCESS METRICS & MONITORING
   • Migration adoption rate targets
   • User sentiment tracking
   • Churn risk indicators
   • Alternative feature adoption rate
   • Timeline adherence
""",
    ),

    "P14": ForgeTemplate(
        id="P14",
        domain="Product Management",
        name="Onboarding Flow Optimization",
        description="Activation flow design with friction removal, analytics events, and copy examples",
        triggers=[
            "user onboarding", "onboarding flow", "activation flow",
            "time to value", "reduce time to first value", "new user experience",
            "onboarding optimization", "improve onboarding",
        ],
        structure="""\
Role: Onboarding UX strategist optimising activation and time-to-value.

FLOW DESIGN  (per phase, provide: Flow Step | Value Proposition | Friction Mitigations | Analytics Event | Exit/Skip Strategy):

1. DISCOVERY PHASE  (first 2 minutes)
   • Value proposition establishment (before asking for anything)
   • Minimal viable setup (what's the absolute minimum to start?)
   • User intent segmentation (personalise from the start)

2. FEATURE INTRODUCTION PHASE
   • 3–5 core features in competence-building sequence
   • Interactive vs passive demo decision per feature
   • Contextual hints over information dumps

3. FIRST ACTION PHASE
   • The single most meaningful first action to drive
   • Barrier reduction tactics
   • Micro-interactions that reinforce progress

4. FRICTION POINT REMOVAL
   • Common abandonment points and interventions
   • Just-in-time help (not upfront tutorials)
   • Optional steps deferred to later

5. ANALYTICS INTEGRATION
   Engagement events to track | Funnel bottleneck metrics | Feature adoption signals

6. SUMMARY TABLE
   Phase → Key metric → Success threshold

7. COPY EXAMPLES
   Critical CTAs | Value statements | Error state messages | Empty state messages
""",
    ),

    "P15": ForgeTemplate(
        id="P15",
        domain="Product Management",
        name="Product Vision Statement",
        description="Vision narrative with long-term goals, core values, market opportunity, and differentiation",
        triggers=[
            "product vision", "vision statement", "long-term product direction",
            "product strategy narrative", "product mission",
            "write product vision", "product north star",
        ],
        structure="""\
Role: Product visioning expert crafting north-star direction for product teams.

OUTPUT SECTIONS (in order):

1. VISION STATEMENT  (1–2 sentences)
   • Inspiring and outcome-focused (not feature-describing)
   • Memorable and team-rally-worthy

2. SUPPORTING NARRATIVE  (150–200 words)
   • The problem being solved at scale
   • Why now is the right time
   • The transformation enabled for users

3. LONG-TERM GOALS  (3–4 goals, 3–5 year horizon)
   • Specific and measurable (not directional aspirations)
   • Ambitious but achievable

4. CORE VALUES  (3–5)
   Per value: Name | One-sentence rationale showing how it guides product decisions

5. MARKET OPPORTUNITY ASSESSMENT
   • TAM estimate with methodology
   • Enabling trends (technology / regulatory / behavioural)
   • Customer segments and pain points
   • Market timing window

6. STRATEGIC DIFFERENTIATION
   2–3 key alternatives in the market:
   Per alternative: Their approach | Their strengths | Their limitations → Your unique approach | Competitive advantages | Why customers will choose you
""",
    ),
}