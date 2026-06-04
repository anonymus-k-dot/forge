"""
FORGE – Research domain templates  [R1 – R15]
"""

from .base import ForgeTemplate

RESEARCH_TEMPLATES: dict[str, ForgeTemplate] = {

    "R1": ForgeTemplate(
        id="R1",
        domain="Research",
        name="Literature Review Generator",
        description="Academic literature synthesis with annotated bibliography",
        triggers=[
            "literature review", "academic research", "research papers",
            "scholarly sources", "research synthesis", "review existing research",
            "systematic review", "academic literature",
        ],
        structure="""\
Role: Academic researcher producing a rigorous literature review.

OUTPUT SECTIONS (in order):

1. INTRODUCTION & SCOPE
   • Topic relevance and significance
   • Temporal and disciplinary boundaries
   • Key research questions guiding the review

2. CATEGORISED SOURCES
   Categories: Foundational | Empirical | Theoretical | Recent (last 3 years) | Contrasting
   Per source: Citation (APA 7th) | Methodology | Key findings | Relevance | Gaps/limitations

3. SYNTHESISED KEY FINDINGS
   • Major themes across sources
   • Points of scholarly consensus
   • Ongoing debates and unresolved tensions
   • How understanding has evolved over time

4. RESEARCH GAPS
   • What remains unstudied or poorly understood
   • Methodological limitations in the field

5. ANNOTATED BIBLIOGRAPHY  (APA 7th)
   • Full citation + 2–3 sentence annotation per source

6. RECOMMENDATIONS FOR FUTURE INVESTIGATION
   • 3–5 specific, actionable research directions
""",
    ),

    "R2": ForgeTemplate(
        id="R2",
        domain="Research",
        name="Competitive Analysis Framework",
        description="Structured competitor comparison with strategic conclusions",
        triggers=[
            "competitor analysis", "compare competitors", "market research",
            "who are my competitors", "competitive landscape",
            "competition analysis", "competitors",
        ],
        structure="""\
Role: Competitive intelligence analyst with strategic consulting background.

OUTPUT SECTIONS (in order):

1. EXECUTIVE SUMMARY  (2–3 sentences covering landscape and key insight)

2. COMPETITOR COMPARISON TABLE
   Columns: Company | Market Position | Key Strengths | Key Weaknesses | Pricing Strategy | Target Segment | Strategic Recommendations
   Cover 3–5 direct and 1–2 indirect competitors.

3. STRATEGIC CONCLUSION
   • Overall competitive landscape characterisation
   • White-space opportunities
   • Key threats to monitor
   • Recommended differentiation direction
""",
    ),

    "R3": ForgeTemplate(
        id="R3",
        domain="Research",
        name="Data Extraction and Summary",
        description="BI-style data parsing with trend analysis and actionable insights",
        triggers=[
            "extract data", "summarize data", "parse document",
            "find metrics", "pull numbers", "business intelligence",
            "extract metrics", "pull data from",
        ],
        structure="""\
Role: Business intelligence analyst extracting signal from unstructured sources.

OUTPUT SECTIONS (in order):

1. EXTRACTED METRICS TABLE
   Columns: Metric | Value | Unit | Time Period | Source Location

2. TREND ANALYSIS
   Per trend: Name | Description | Supporting data points (min 2)

3. KEY FINDINGS SUMMARY
   2–3 sentences covering the most critical data revelations

4. ACTIONABLE INSIGHTS
   3–5 specific, data-backed recommendations
   Each: Recommendation | Supporting metric | Expected business impact
""",
    ),

    "R4": ForgeTemplate(
        id="R4",
        domain="Research",
        name="Research Methodology Design",
        description="Full study design with hypotheses, sampling, analysis plan, and validity",
        triggers=[
            "design a study", "research methodology", "how to study",
            "experimental design", "sample size", "quantitative research",
            "qualitative research", "study design", "research design",
        ],
        structure="""\
Role: Research methodologist with expertise in both quantitative and qualitative designs.

OUTPUT SECTIONS (in order):

1. RESEARCH QUESTIONS & HYPOTHESES
   • 3–5 research questions
   • For each: Null hypothesis (H₀) and Alternative hypothesis (H₁)

2. SAMPLE SIZE CALCULATION
   • Target population definition
   • Power analysis: α, β (power), effect size assumption
   • Minimum N and recommended N with justification

3. DATA COLLECTION METHODS
   • Instruments (surveys, interviews, sensors, archival data)
   • Validity and reliability considerations
   • Timeline and logistics
   • Bias mitigation strategies

4. RESEARCH DESIGN
   • Design type: experimental / quasi-experimental / observational / mixed
   • Justification for this design
   • Control groups and randomisation approach

5. STATISTICAL ANALYSIS PLAN
   • Descriptive statistics planned
   • Inferential tests (with assumptions checked)
   • Effect size measures
   • Secondary and sensitivity analyses

6. VALIDITY & LIMITATIONS
   • Internal validity threats and mitigations
   • External validity (generalisability) considerations
""",
    ),

    "R5": ForgeTemplate(
        id="R5",
        domain="Research",
        name="Market Trend Analysis",
        description="Historical, current, and forward-looking market analysis with scenarios",
        triggers=[
            "market trends", "industry trends", "emerging trends",
            "market forecast", "market analysis", "sector outlook",
            "trend analysis", "market outlook",
        ],
        structure="""\
Role: Markets analyst combining quantitative data with strategic narrative.

OUTPUT SECTIONS (in order):

1. HISTORICAL CONTEXT
   • Key inflection points and how the market evolved
   • Structural shifts (regulatory, technological, behavioural)

2. CURRENT DATA INSIGHTS
   • Specific metrics with sources (market size, growth rate, key players)
   • Momentum signals: what is accelerating vs decelerating
   • Sub-trends and their relative maturity

3. FORECAST PROJECTIONS  (3–5 year horizon)
   • Base scenario: most likely path with key assumptions
   • Upside scenario: catalysts that could accelerate growth
   • Downside scenario: risks that could suppress growth
   • Key variables to monitor

4. STRATEGIC IMPLICATIONS
   3–5 concrete actions per stakeholder group (investor / operator / new entrant)
   Include first-mover opportunity windows with rough timing
""",
    ),

    "R6": ForgeTemplate(
        id="R6",
        domain="Research",
        name="Technical Specification Document",
        description="System architecture, APIs, data models, and security requirements",
        triggers=[
            "technical spec", "system requirements", "architecture blueprint",
            "system design document", "tech spec", "system specification",
            "software specification", "technical specification",
        ],
        structure="""\
Role: Senior technical writer and system architect.

OUTPUT SECTIONS (in order):

1. SYSTEM ARCHITECTURE
   • Components and their responsibilities
   • Integration patterns and communication protocols
   • Deployment topology overview

2. API ENDPOINTS
   • Per endpoint: HTTP method | URL | Auth required | Request schema | Response schema | Status codes
   • Use RESTful or GraphQL conventions as applicable

3. DATA MODELS
   • Entities with field definitions (name, type, constraints)
   • Relationships and cardinality
   • Validation rules and business constraints

4. SECURITY REQUIREMENTS
   • Authentication and authorisation model
   • Encryption at rest and in transit
   • Compliance requirements (GDPR, HIPAA, SOC2, etc.)

5. IMPLEMENTATION GUIDELINES
   • Coding standards and conventions
   • Deployment procedures and environment parity
   • Known edge cases and constraints
   • Performance and scalability targets
""",
    ),

    "R7": ForgeTemplate(
        id="R7",
        domain="Research",
        name="Evidence-Based Recommendations",
        description="Research-backed policy or business recommendations with case studies",
        triggers=[
            "evidence-based", "research-backed", "data-driven recommendations",
            "what does research say", "policy recommendation",
            "evidence based", "research based recommendation",
        ],
        structure="""\
Role: Policy and business advisor synthesising research into actionable recommendations.

For EACH recommendation, provide:

1. RECOMMENDATION STATEMENT
   Clear, specific, actionable directive

2. EVIDENCE BASE
   2–3 citations (Author, Year) with study type and sample size

3. KEY STATISTICS
   Specific numbers with confidence intervals and sample size

4. CASE STUDY
   Context | Implementation | Measurable outcomes | Transferability notes

5. RISK ASSESSMENT
   Probability (H/M/L) | Impact | Mitigation strategy

6. CONFIDENCE LEVEL
   High / Medium / Low — with explicit reasoning

7. IMPLEMENTATION CONSIDERATIONS
   Prerequisites, resource requirements, timeline, likely resistance points
""",
    ),

    "R8": ForgeTemplate(
        id="R8",
        domain="Research",
        name="Case Study Analysis",
        description="Multi-dimensional case study from background to transferable lessons",
        triggers=[
            "case study", "analyze this scenario", "real-world example",
            "organisational analysis", "business case analysis",
            "analyze case", "case analysis",
        ],
        structure="""\
Role: Case study analyst applying structured analytical frameworks.

OUTPUT SECTIONS (in order):

1. BACKGROUND
   • Organisation profile: industry, size, timeline, key stakeholders
   • Market context at the time of the events

2. PROBLEM IDENTIFICATION
   • Core problem vs surface symptoms (clearly distinguished)
   • Root causes (5-Why analysis or Fishbone)
   • Quantified impact on business metrics

3. SOLUTION APPROACH
   • Methodology and decision-making process
   • Implementation steps and timeline
   • Constraints encountered and how addressed

4. RESULTS & OUTCOMES
   • Specific metrics (before vs after)
   • Intended vs unintended consequences
   • Variance from stated objectives and why

5. LESSONS LEARNED
   • What worked and why
   • What failed and why
   • What would be done differently

6. APPLICABILITY & TRANSFERABILITY
   • Boundary conditions (what context this applies to)
   • Adaptation requirements for different settings
""",
    ),

    "R9": ForgeTemplate(
        id="R9",
        domain="Research",
        name="Survey Analysis Insights",
        description="Statistical survey analysis with segmentation and visualisation recommendations",
        triggers=[
            "analyze survey", "survey results", "survey data",
            "questionnaire analysis", "survey insights",
            "survey analysis", "analyse survey",
        ],
        structure="""\
Role: Survey research analyst with expertise in quantitative and qualitative data synthesis.

OUTPUT SECTIONS (in order):

1. EXECUTIVE SUMMARY  (2–3 sentences)

2. STATISTICAL OVERVIEW
   • Response rate and sample representativeness
   • Top-line findings summary
   • Score distributions for key questions

3. DEMOGRAPHIC ANALYSIS
   Per segment: key metrics | notable differences from overall | implications

4. SENTIMENT & QUALITATIVE INSIGHTS
   • Positive / Neutral / Negative % with context
   • Top 5 themes from open-ended responses
   • 2–3 representative verbatim quotes per theme

5. CORRELATION ANALYSIS
   3–5 notable correlations with practical significance explanation

6. VISUALISATION RECOMMENDATIONS
   5 recommended charts: Chart type | Title | Variables to plot | Insight it reveals

7. RECOMMENDED ACTIONS
   Numbered, specific actions tied directly to findings
""",
    ),

    "R10": ForgeTemplate(
        id="R10",
        domain="Research",
        name="Research Paper Outline",
        description="Academic paper structure with thesis, argument flow, and evidence map",
        triggers=[
            "research paper outline", "academic paper structure",
            "structure my paper", "paper outline", "thesis structure",
            "outline my paper", "academic outline",
        ],
        structure="""\
Role: Academic advisor helping construct a rigorous, publishable research paper structure.

OUTPUT SECTIONS (in order):

1. THESIS STATEMENT
   • Arguable, specific, and representing an original contribution
   • Clearly states the argument being made, not just the topic

2. PAPER STRUCTURE (hierarchical)
   For each section: Title | Purpose | Research questions addressed | Main arguments
   Include: Introduction → Literature Review → Body Sections (2–4) → Counterarguments → Conclusion

3. PER-SECTION DETAIL
   For each section:
   • Argument progression rationale (why this section follows the previous)
   • Citation placeholders: [CITE: type/year/claim-type]
   • Evidence requirements (empirical data / expert opinion / case studies)

4. ARGUMENT FLOW
   Explicit transitions: how each section logically leads to the next

5. EVIDENCE REQUIREMENTS SUMMARY TABLE
   Section | Evidence Type | Quantity Needed | Priority
""",
    ),

    "R11": ForgeTemplate(
        id="R11",
        domain="Research",
        name="Risk Assessment Matrix",
        description="Scored risk register with mitigation strategies and implementation roadmap",
        triggers=[
            "risk assessment", "identify risks", "risk matrix",
            "risk management", "what could go wrong",
            "risk register", "risk analysis", "organisational risks",
        ],
        structure="""\
Role: Risk management consultant applying structured risk assessment methodology.

OUTPUT SECTIONS (in order):

1. RISK REGISTER TABLE
   Columns: Category | Risk Description | Probability (1–5) | Impact (1–5) | Score (P×I) | Mitigation Strategy | Contingency Plan | Owner | Review Frequency

2. RISK TIER SUMMARY
   • Critical (score 20–25): list + immediate actions
   • High (16–19): list + near-term actions
   • Medium (10–15): monitoring plan
   • Low (5–9): accept or defer

3. PRIORITISED ACTION ITEMS
   Numbered, owner-assigned, with deadline

4. IMPLEMENTATION ROADMAP
   30 / 60 / 90-day action milestones for highest-priority risks
""",
    ),

    "R12": ForgeTemplate(
        id="R12",
        domain="Research",
        name="Stakeholder Analysis Report",
        description="Power/interest grid with tailored engagement and communication strategy",
        triggers=[
            "stakeholder analysis", "stakeholder mapping",
            "who are the stakeholders", "engagement plan",
            "stakeholder strategy", "stakeholder management",
        ],
        structure="""\
Role: Project management consultant specialising in stakeholder engagement.

OUTPUT SECTIONS (in order):

1. STAKEHOLDER IDENTIFICATION MATRIX
   Columns: Name/Role | Organisation | Primary Interest | Influence Source | Current Sentiment (Supportive/Neutral/Opposed)

2. POWER / INTEREST GRID
   Four quadrants: Manage Closely | Keep Satisfied | Keep Informed | Monitor
   Place each stakeholder with a brief engagement rationale

3. ENGAGEMENT STRATEGIES
   Per stakeholder group: strategy, key messages, success criteria

4. COMMUNICATION PLAN TABLE
   Columns: Group | Frequency | Channels | Key Messages | Owner | Format (meeting/email/report)

5. RISK ASSESSMENT
   Stakeholder risks: resistant parties, conflicting interests, power dynamics

6. IMPLEMENTATION TIMELINE
   Engagement milestones over the project lifecycle
""",
    ),

    "R13": ForgeTemplate(
        id="R13",
        domain="Research",
        name="Hypothesis Testing Framework",
        description="Full statistical testing design with test selection and interpretation guide",
        triggers=[
            "hypothesis test", "statistical test", "null hypothesis",
            "p-value", "significance test", "experimental framework",
            "statistical significance", "t-test", "anova", "chi-square",
        ],
        structure="""\
Role: Statistician designing a rigorous hypothesis testing framework.

OUTPUT SECTIONS (in order):

1. NULL HYPOTHESIS H₀  (formal statistical notation)

2. ALTERNATIVE HYPOTHESIS H₁  (directional or non-directional, justified)

3. SIGNIFICANCE LEVEL
   • Chosen α with justification (0.05 / 0.01 / Bonferroni adjustment)

4. SAMPLE REQUIREMENTS
   • Minimum N from power analysis (α, β=0.80 default, expected effect size)
   • Sampling method and representativeness requirements

5. TEST SELECTION RATIONALE
   • Recommended statistical test and why
   • Assumptions of the test and how to verify them
   • Alternative tests if assumptions are violated

6. INTERPRETATION GUIDELINES
   • p-value decision rules (reject / fail to reject H₀)
   • Type I and Type II error implications
   • Statistical vs practical significance distinction
   • Confidence interval interpretation
""",
    ),

    "R14": ForgeTemplate(
        id="R14",
        domain="Research",
        name="Content Gap Analysis",
        description="Phased content gap identification with prioritised creation strategy",
        triggers=[
            "content gap", "missing content", "what content do i need",
            "content audit", "content strategy gaps",
            "content gap analysis", "audit my content",
        ],
        structure="""\
Role: Content strategist identifying gaps between current content and audience needs.

OUTPUT SECTIONS (in order):

1. EXECUTIVE SUMMARY

2. CURRENT STATE ASSESSMENT
   • Inventory of existing content
   • Strengths and weaknesses
   • Audience segments and their current coverage

3. GAP ANALYSIS TABLE
   Columns: Topic | Current Coverage (None/Partial/Full) | Required Coverage | Gap Severity (H/M/L) | Audience Impact

4. PRIORITISED RECOMMENDATIONS
   • Tier 1 – Quick Wins (1–2 months): high impact, low effort
   • Tier 2 – High Impact (2–4 months): strategic topics
   • Tier 3 – Strategic (4–6 months): long-form, foundational

5. CONTENT CREATION STRATEGY
   • Phased rollout plan
   • Repurposing opportunities from existing content
   • Distribution channels per content type

6. SUCCESS METRICS
   • Measurable outcomes for each tier (traffic, engagement, conversions)
""",
    ),

    "R15": ForgeTemplate(
        id="R15",
        domain="Research",
        name="Research Synthesis Brief",
        description="Cross-source synthesis with consensus, contradictions, and implications",
        triggers=[
            "synthesize research", "combine findings",
            "summarize multiple sources", "executive brief from research",
            "research synthesis", "synthesis brief", "synthesise research",
        ],
        structure="""\
Role: Research synthesiser distilling multiple sources into executive-ready intelligence.

OUTPUT SECTIONS (in order):

1. EXECUTIVE SUMMARY  (2–3 sentences: the single most important takeaway)

2. KEY FINDINGS  (organised by theme, not by source)
   Each finding: Statement | Sources supporting it (cited) | Strength of evidence

3. POINTS OF CONSENSUS
   • Where sources agree, with confidence level
   • How robust is the consensus (number and quality of sources)

4. CONTRADICTIONS & TENSIONS
   • Where sources conflict
   • Possible explanations for divergence
   • What remains genuinely unresolved

5. IMPLICATIONS FOR PRACTICE
   • 3–5 actionable recommendations drawn directly from the evidence

6. POLICY IMPLICATIONS
   • What decision-makers should consider changing or adopting

7. GAPS & CAVEATS
   • What the research cannot answer
   • Methodological limitations across the body of work
""",
    ),
}