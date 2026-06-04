"""
FORGE – Writing domain templates  [W1 – W15]
"""

from .base import ForgeTemplate

WRITING_TEMPLATES: dict[str, ForgeTemplate] = {

    "W1": ForgeTemplate(
        id="W1",
        domain="Writing",
        name="SEO Optimized Blog Strategy",
        description="Full-stack SEO blog plan: metadata, headers, FAQs, and engagement hooks",
        triggers=[
            "blog post", "seo article", "web content", "rank on google",
            "keyword article", "content marketing", "seo blog",
            "write a blog", "write blog post",
        ],
        structure="""\
Role: SEO strategist and content writer with expertise in organic search optimisation.

OUTPUT SECTIONS (in order):

1. SEO METADATA
   • Meta title: 55–60 characters, keyword-first
   • Meta description: 155–160 characters, includes CTA
   • Focus keyword + estimated monthly search volume
   • Target word count

2. HEADER HIERARCHY & KEYWORD MAP
   • H1 (one, includes focus keyword)
   • H2s (3–6, each targeting a sub-topic or LSI keyword)
   • H3s under each H2 as needed
   • Keyword placement notes per heading level

3. SECTION OUTLINE
   Per section: Talking points | Recommended format (prose/list/table) | LSI keywords to weave in

4. INTERNAL LINKING STRATEGY
   • 3–5 internal link opportunities with suggested anchor text

5. FAQ SECTION
   3–4 questions targeting featured snippet format
   Each: Question (mirroring common search query) + concise direct answer (40–60 words)

6. SCHEMA MARKUP RECOMMENDATIONS
   Recommended schema types (Article, FAQ, HowTo) with rationale

7. ENGAGEMENT HOOKS
   • Opening hook (first 2 sentences — must earn the scroll)
   • Curiosity-driving subheadings (2–3 examples)
   • Key data points to include
   • Benefit statements for CTA section
""",
    ),

    "W2": ForgeTemplate(
        id="W2",
        domain="Writing",
        name="Technical Documentation Generator",
        description="Developer-grade docs: API reference, parameters, examples, and error codes",
        triggers=[
            "technical documentation", "developer docs", "software documentation",
            "api reference", "feature documentation", "write technical docs",
            "document my api", "api docs",
        ],
        structure="""\
Role: Technical documentation expert writing for developer audiences.

OUTPUT SECTIONS (in order):

1. OVERVIEW
   • Feature/API purpose in one sentence
   • Prerequisites and dependencies
   • Quick-start example (minimal working snippet)

2. API ENDPOINTS / FUNCTIONS
   Per endpoint: HTTP method + URL (or function signature) | Auth requirements | Description

3. PARAMETERS TABLE
   Columns: Name | Type | Required | Default | Description | Constraints/Notes

4. CODE EXAMPLES
   • Language-specific examples (Python, JavaScript, curl at minimum)
   • Each example: copy-paste ready, with expected output shown
   • Cover: basic usage, auth, error handling, pagination

5. ERROR HANDLING
   Table: Error code | HTTP status | Message | Likely cause | Resolution

6. TROUBLESHOOTING
   • 4–6 common issues: symptom → diagnostic step → solution
""",
    ),

    "W3": ForgeTemplate(
        id="W3",
        domain="Writing",
        name="Persuasive Email Sequences",
        description="5–7 email funnel from awareness to conversion with A/B variants",
        triggers=[
            "email sequence", "sales funnel emails", "email campaign",
            "drip campaign", "marketing emails", "nurture sequence",
            "email funnel", "sales emails",
        ],
        structure="""\
Role: Email marketing strategist with expertise in conversion-optimised sequences.

OUTPUT SECTIONS (in order):

1. FUNNEL OVERVIEW
   • Total emails, target conversion rate, total sequence duration
   • Audience segment definition

2. EMAIL SEQUENCE  (5–7 emails)
   Stages: Awareness → Problem → Solution → Social Proof → Urgency → Win-Back
   Per email:
   • Email #N: [Stage Name]
   • Subject line + 2–3 A/B variants
   • Preview text
   • Body copy (150–300 words)
   • Primary CTA + secondary CTA
   • Send timing (Day X after trigger)
   • Target segment

3. A/B TESTING PLAN
   • Phase 1: Subject lines (first 2 emails)
   • Phase 2: CTAs (emails 3–5)
   • Sample size requirements per variant

4. SUCCESS METRICS
   Per email: open rate target | CTR target | conversion target
""",
    ),

    "W4": ForgeTemplate(
        id="W4",
        domain="Writing",
        name="Content Calendar Planner",
        description="90-day multi-platform content calendar with keyword integration",
        triggers=[
            "content calendar", "posting schedule", "90-day content plan",
            "social media calendar", "editorial calendar",
            "content plan", "content schedule",
        ],
        structure="""\
Role: Content strategist planning a multi-platform 90-day content programme.

OUTPUT SECTIONS (in order):

1. THREE 30-DAY BLOCKS
   Each block: strategic theme + expected outcomes + key content formats

2. WEEKLY BREAKDOWN
   Per week (across 12 weeks):
   • Platform-specific posts: Title | Content type | Primary keyword | CTA | Seasonal/topical hook

3. PLATFORM OPTIMISATION NOTES
   Per platform (LinkedIn / Instagram / X/Twitter / TikTok / Blog / Email / YouTube):
   • Optimal format, length, posting frequency, best times to post

4. KEYWORD INTEGRATION
   2–3 primary keywords + 2–3 secondary keywords per weekly theme

5. STRATEGIC INSIGHTS
   5 bullets: content themes → expected outcomes | content risks | resource requirements | repurposing opportunities
""",
    ),

    "W5": ForgeTemplate(
        id="W5",
        domain="Writing",
        name="Case Study Framework",
        description="B2B case study from challenge to quantified results with testimonial",
        triggers=[
            "write case study", "customer success story", "client case study",
            "b2b case study", "proof of results", "case study writing",
        ],
        structure="""\
Role: B2B marketing strategist writing compelling, credible customer case studies.

OUTPUT SECTIONS (in order):

1. CHALLENGE STATEMENT
   • Client background (industry, size, role of decision-maker)
   • Specific problems with quantified pain (e.g., "lost X hours/week")
   • Why previous solutions failed

2. SOLUTION OVERVIEW
   • Approach and methodology
   • Key components and differentiating factors

3. IMPLEMENTATION TIMELINE
   Phases with milestones | Resources deployed | Challenges encountered | Go-live moment

4. QUANTIFIABLE RESULTS  (4–5 metrics)
   Format: "[Metric] improved by [X%] within [timeframe]"
   Include a mix: efficiency / revenue / cost / customer experience

5. BUSINESS IMPACT
   • Strategic advantages gained
   • Competitive positioning improvements
   • Downstream effects

6. CLIENT TESTIMONIAL
   3–4 sentences in authentic first-person voice
   Cover: before state, transformation, specific outcome, recommendation to peers
""",
    ),

    "W6": ForgeTemplate(
        id="W6",
        domain="Writing",
        name="Product Description Optimizer",
        description="E-commerce copy: feature-to-benefit map, body copy, specs, trust signals",
        triggers=[
            "product description", "e-commerce copy", "product listing",
            "amazon listing", "write about product", "ecommerce description",
            "product copy",
        ],
        structure="""\
Role: E-commerce copywriter maximising conversion through benefit-led copy.

OUTPUT SECTIONS (in order):

1. HEADLINE & HOOK  (50–80 words)
   • Lead with the primary USP, not a feature
   • Evoke the outcome the buyer wants

2. FEATURE-TO-BENEFIT MAP
   Table: Feature | So What? (Customer Benefit) | Emotional Payoff

3. BODY COPY  (150–200 words)
   • 3–5 keywords integrated naturally
   • Active voice, 6th–8th grade reading level
   • Lead with benefits; support with features
   • End with soft CTA

4. SPECIFICATIONS TABLE
   Technical details in structured format

5. VARIANT COMPARISON TABLE
   If multiple SKUs/versions, compare clearly

6. TRUST SIGNALS
   • Warranty / guarantee terms
   • Certifications and awards
   • Social proof summary (review count/rating)
   • Returns policy in plain language

7. USPs  (3–5 bullet points)
   Differentiated reasons to choose this product over alternatives
""",
    ),

    "W7": ForgeTemplate(
        id="W7",
        domain="Writing",
        name="Brand Voice Guidelines",
        description="Comprehensive brand voice system with vocabulary, examples, and QA checklist",
        triggers=[
            "brand voice", "tone of voice", "brand guidelines",
            "writing style guide", "brand communication standards",
            "brand tone", "voice guidelines",
        ],
        structure="""\
Role: Brand strategist defining a distinctive, consistent brand communication system.

OUTPUT SECTIONS (in order):

1. BRAND PERSONALITY FOUNDATION
   3–5 traits, each with:
   • Trait name
   • Definition (what it means for this brand specifically)
   • How it shows in communication (observable, not abstract)

2. VOCABULARY FRAMEWORK
   • 15–20 "DO USE" words/phrases with rationale
   • 10–15 "DO NOT USE" words with why and what to say instead (Avoid → Use)

3. TONE EXAMPLES BY CHANNEL
   Per channel (Email / Social / Support / Docs / Marketing):
   2–3 example sentences demonstrating the right tone

4. AUDIENCE SEGMENTATION
   3–4 audience segments:
   Per segment: Tone adjustments | Vocabulary level | Example message

5. CONSISTENCY CHECKPOINTS
   5–7 quality-assurance questions writers can self-check against

6. QUICK REFERENCE CARD
   • 3 core voice words
   • 5 brand personality traits
   • 10 do's and don'ts
   • 5 non-negotiable rules
""",
    ),

    "W8": ForgeTemplate(
        id="W8",
        domain="Writing",
        name="Academic Paper Outline",
        description="Thesis-anchored academic paper structure with argument flow and evidence map",
        triggers=[
            "academic paper", "write a paper", "research paper structure",
            "thesis paper", "scholarly article", "academic writing",
            "write academic paper",
        ],
        structure="""\
Role: Academic writing specialist helping produce rigorous, publishable papers.

OUTPUT SECTIONS (in order):

1. THESIS STATEMENT
   • Bold, arguable, specific, original contribution
   • States the argument, not just the topic

2. HIERARCHICAL STRUCTURE
   Introduction → Literature Review → Body (2–4 sections) → Counterarguments → Conclusion

3. PER-SECTION DETAIL
   For each section:
   • Title and purpose
   • Key arguments to make
   • Citation placeholders: [CITE: type/year/claim]
   • Evidence requirements
   • Why this section follows the previous (transition rationale)

4. ARGUMENT FLOW
   Explicit logical transitions between each section

5. EVIDENCE MAP  (summary table)
   Section | Evidence Type | Quantity | Priority Level
""",
    ),

    "W9": ForgeTemplate(
        id="W9",
        domain="Writing",
        name="Social Media Content Mix",
        description="Multi-platform strategy with post templates, hashtags, and posting schedule",
        triggers=[
            "social media strategy", "posting templates", "social media content plan",
            "multi-platform strategy", "social content",
            "social media posts", "social media plan",
        ],
        structure="""\
Role: Social media strategist building a cohesive multi-platform content programme.

OUTPUT SECTIONS (in order):

1. PLATFORM SELECTION  (3–5 platforms)
   Per platform: Justification for inclusion | Audience fit | Content strengths

2. CONTENT PILLARS  (4–6 themes)
   Per pillar: Name | Description | Why it resonates | Content formats it suits

3. POST TEMPLATES PER PLATFORM
   Per template: Opening hook | Body structure | CTA | Variable placeholders {topic}/{pain_point}/{benefit}

4. HASHTAG STRATEGY
   • 15–20 core hashtags
   • 30–40 niche hashtags
   • Research methodology for hashtag discovery

5. ENGAGEMENT TACTICS
   • Response time targets
   • Community engagement formats (polls, questions, UGC prompts)

6. POSTING SCHEDULE
   Weekly calendar with optimal posting times per platform

7. CONTENT DISTRIBUTION
   Percentages: Educational vs Promotional | Video vs Static | Original vs Curated

8. MEASUREMENT FRAMEWORK + 30-60-90 DAY MILESTONES
""",
    ),

    "W10": ForgeTemplate(
        id="W10",
        domain="Writing",
        name="Grant Proposal Template",
        description="Full grant proposal from executive summary through budget justification",
        triggers=[
            "grant proposal", "grant application", "funding proposal",
            "nonprofit proposal", "request for funding", "write a grant",
            "grant writing",
        ],
        structure="""\
Role: Grant proposal strategist with experience writing successful funding applications.

OUTPUT SECTIONS (in order):

1. EXECUTIVE SUMMARY
   Project title | Duration | Amount requested | Problem | Solution | Outcomes | Organisational capability

2. STATEMENT OF NEED
   • Problem definition with statistics
   • Current landscape and gaps
   • Consequences of inaction
   • Target population description

3. PROJECT DESCRIPTION
   • Goals (broad directional)
   • SMART objectives (specific, measurable, time-bound)
   • Methodology: activities, timeline, Gantt outline
   • Staff qualifications relevant to the project

4. EVALUATION PLAN
   • Logic model (inputs → activities → outputs → outcomes)
   • Performance indicators per objective
   • Data collection methods and frequency
   • Analysis plan and reporting schedule

5. BUDGET & JUSTIFICATION
   • Summary table by category
   • Line-item justification for major expenses
   • Sustainability plan post-grant period

6. ORGANISATIONAL CAPACITY
   • Track record and credentials
   • Relevant past projects and outcomes

7. IMPACT & SUSTAINABILITY

8. LETTERS OF SUPPORT  (guidance on who to request and what to ask for)
""",
    ),

    "W11": ForgeTemplate(
        id="W11",
        domain="Writing",
        name="White Paper Generator",
        description="Executive-grade white paper with case studies, ROI projections, and CTAs",
        triggers=[
            "white paper", "thought leadership", "industry report",
            "executive report", "authoritative document", "whitepaper",
            "write white paper",
        ],
        structure="""\
Role: White paper strategist producing authoritative, conversion-oriented long-form content.

OUTPUT SECTIONS (in order):

1. EXECUTIVE SUMMARY  (250–300 words)
   Problem | Solution | Financial outcomes | Third-party validation

2. INDUSTRY ANALYSIS  (400–500 words)
   Market size and trends with 3–5 data sources

3. PROBLEM STATEMENT  (350–400 words)
   Quantified business impact | Legacy solution limitations

4. PROPRIETARY SOLUTION  (500–600 words)
   Innovation | Mechanism | Architecture overview | Competitive differentiation

5. CASE STUDIES  (2–3)
   Per case: Vertical | Company size | Baseline | Timeline | Quantified results | Decision-maker quote

6. IMPLEMENTATION ROADMAP
   Phases | Milestones | Resource requirements | Risk mitigation

7. ROI PROJECTIONS
   1 / 3 / 5-year cost-benefit analysis | Assumptions | Sensitivity analysis | Payback period

8. CONCLUSION & CTA
   Summary of key argument + specific next step for the reader
""",
    ),

    "W12": ForgeTemplate(
        id="W12",
        domain="Writing",
        name="Copywriting Conversion Toolkit",
        description="High-converting copy: headlines, value props, bullets, social proof, CTAs",
        triggers=[
            "landing page copy", "sales page", "conversion copy",
            "high-converting copy", "a/b test copy",
            "sales copy", "persuasive copy", "copywriting",
        ],
        structure="""\
Role: Conversion copywriter optimising every element of a sales or landing page.

OUTPUT SECTIONS (in order):

1. HEADLINE VARIATIONS  (5 options, each using a different psychological lever)
   • Benefit-driven
   • Curiosity gap
   • Numbers and specificity
   • Problem agitation
   • Social proof anchor

2. VALUE PROPOSITION STATEMENTS  (3 variations)

3. BENEFIT BULLETS  (6–8)
   Mix: functional benefits + emotional payoffs
   Each addresses an implicit objection

4. SOCIAL PROOF ELEMENTS  (4 types)
   Testimonial format | Key statistic | Authority endorsement | User milestone

5. URGENCY MECHANISMS  (3 levels)
   Low intensity | Medium intensity | High intensity

6. CTA VARIATIONS  (5 options)
   Benefit-focused | Action-focused | Low-commitment | Urgency-based | Risk-reversal
   Each: button text + supporting microcopy + psychological principle

7. A/B TESTING GUIDANCE
   Testing sequence (headlines first → CTAs → value props) | Min sample size | Significance threshold
""",
    ),

    "W13": ForgeTemplate(
        id="W13",
        domain="Writing",
        name="Interview Question Builder",
        description="Structured interview guide with competency rubric and evaluation framework",
        triggers=[
            "interview questions", "hiring questions", "interview guide",
            "candidate assessment", "interview template",
            "write interview questions", "job interview questions",
        ],
        structure="""\
Role: Interview guide designer and talent acquisition strategist.

OUTPUT SECTIONS (in order):

1. OPENING & CONTEXT SETTING
   • Welcome script
   • Structure overview for candidate
   • Role context framing

2. CORE COMPETENCY QUESTIONS  (4–5 questions)
   Per question:
   • Open-ended behavioural question
   • 2–3 follow-up probes
   • Behavioural indicators to listen for
   • Description of strong vs weak response

3. SCENARIO-BASED ASSESSMENTS  (2–3 realistic scenarios)
   Per scenario:
   • Situation description
   • "What would you do?" question
   • "What would you do differently?" follow-up
   • "How would you measure success?" follow-up

4. EVALUATION RUBRIC
   5–6 competencies, each with:
   • 5-point scale with behavioural anchors at 1, 3, and 5
   • Scoring weight (must total 100%)

5. CLOSING SCRIPT
   Candidate questions | What's next | Timeline | Appreciation
""",
    ),

    "W14": ForgeTemplate(
        id="W14",
        domain="Writing",
        name="Content Repurposing Plan",
        description="90-day multi-format content distribution plan maximising content ROI",
        triggers=[
            "repurpose content", "content distribution",
            "extend content reach", "content across platforms",
            "maximize content", "content repurposing", "repurpose my content",
        ],
        structure="""\
Role: Content repurposing strategist maximising reach and shelf-life of existing content.

OUTPUT SECTIONS (in order):

1. SOURCE CONTENT ASSESSMENT
   • Evergreen value rating
   • Natural breakpoints and extractable sections
   • Key insights worth amplifying

2. FORMAT ADAPTATIONS  (5+ formats)
   Per format: Platform | Optimal length | Adaptation strategy | Content structure | Audience angle | Technical requirements | Distribution timing | Success metrics

3. AUDIENCE VARIATIONS  (2–3 segments)
   Per segment: Messaging angle | Format preferences | Pain points addressed | CTA variants | Tone adjustments

4. 90-DAY DISTRIBUTION CALENDAR
   • Launch sequence (original → derivatives)
   • Cross-promotion strategy
   • Posting cadence per platform
   • Seasonal timing opportunities

5. REPURPOSING QUICK-WIN OPPORTUNITIES
   Easiest, highest-ROI adaptations to execute first
""",
    ),

    "W15": ForgeTemplate(
        id="W15",
        domain="Writing",
        name="Crisis Communication Protocol",
        description="Crisis response templates, stakeholder messaging, and reputation recovery plan",
        triggers=[
            "crisis communication", "pr crisis", "incident response",
            "reputation management", "emergency announcement", "crisis messaging",
            "crisis pr", "damage control",
        ],
        structure="""\
Role: Crisis communications expert managing stakeholder trust under pressure.

OUTPUT SECTIONS (in order):

1. RESPONSE TEMPLATES  (3–4 with [PLACEHOLDER] slots)
   • Initial acknowledgment (within 30 min of incident)
   • Stakeholder-specific communications
   • Update / escalation message
   • Resolution and recovery announcement

2. STAKEHOLDER MESSAGING GUIDE
   Per group (Employees / Customers / Investors / Media / Regulators / Community):
   Tone | Key messages | Channels | Frequency | What to withhold (and why)

3. FAQ DOCUMENT
   8–12 anticipated public/media questions with consistent, aligned answers

4. TIMELINE & ESCALATION PROTOCOL
   • 0–30 min: first response and internal escalation
   • 30 min–2 hr: stakeholder notifications
   • 2–24 hr: sustained communications
   • 24–72 hr: narrative management
   • 72 hr+: recovery and reputation rebuild
   Each phase: approved actions | decision authority | triggers for escalation

5. REPUTATION RECOVERY STRATEGY
   Phase 1 – Containment | Phase 2 – Stabilisation | Phase 3 – Restoration
   Per phase: actions + success metrics
""",
    ),
}