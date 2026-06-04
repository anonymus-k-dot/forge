"""
FORGE – Marketing domain templates  [M1 – M15]
"""

from .base import ForgeTemplate

MARKETING_TEMPLATES: dict[str, ForgeTemplate] = {

    "M1": ForgeTemplate(
        id="M1",
        domain="Marketing",
        name="Landing Page Hero",
        description="Above-the-fold hero section copy with headline, subheadline, CTA, and bullets",
        triggers=[
            "landing page hero", "above the fold", "hero section",
            "homepage copy", "hero copy", "website headline",
            "above the fold copy",
        ],
        structure="""\
Role: SaaS copywriter writing above-the-fold sections that convert visitors into leads.

OUTPUT SECTIONS (in order):

1. HEADLINE  (8–12 words max)
   • Transformation-focused or benefit-focused — never feature-focused
   • Make a clear, specific promise the visitor will believe

2. SUBHEADLINE  (1–2 sentences, 15–20 words)
   • Expand the headline with specificity
   • Answer the visitor's implicit "so what?" and "for whom?"

3. CTA BUTTON TEXT  (2–4 words)
   • Action verb tied to outcome (not generic "Get Started" or "Learn More")
   • 2–3 variations to A/B test

4. SUPPORTING BULLET POINTS  (exactly 3)
   • Benefit-focused, not feature-listing
   • 6–10 words each
   • Parallel grammatical structure
   • Each addresses a different customer outcome

5. TRUST SIGNAL PLACEMENT GUIDANCE
   What social proof element to place directly below the CTA (review count, logo bar, or testimonial snippet)
""",
    ),

    "M2": ForgeTemplate(
        id="M2",
        domain="Marketing",
        name="Ad Headline Variants",
        description="Multi-platform ad headlines with psychological angles and A/B testing plan",
        triggers=[
            "ad headlines", "write ads", "google ads", "meta ads",
            "linkedin ads", "paid campaign copy", "ad copywriting",
            "facebook ads", "ad copy", "write an ad",
        ],
        structure="""\
Role: Performance advertising copywriter maximising click-through rate across paid channels.

OUTPUT SECTIONS (in order):

1. HEADLINE VARIATIONS  (5–7 options)
   Each uses a distinct psychological lever:
   • Urgency / Scarcity
   • Social proof / Authority
   • Clear value proposition
   • Exclusivity / In-group
   • Curiosity / Open loop
   • FOMO (Fear of Missing Out)
   • Specificity / Data point

   Per headline:
   • Headline text
   • Platform optimised for (Google / Meta / LinkedIn / TikTok)
   • Persuasion angle used
   • Why it works for this audience
   • Character count (Google: max 30 | Meta: max 27 primary | LinkedIn: max 150)

2. A/B TESTING PLAN
   • Which 2 variants to test first and why
   • Success metric (CTR target per platform)
   • Minimum impressions before declaring winner
""",
    ),

    "M3": ForgeTemplate(
        id="M3",
        domain="Marketing",
        name="Email Subject Lines",
        description="10 subject line variants with psychological drivers and spam risk scoring",
        triggers=[
            "email subject lines", "improve open rates", "subject line copy",
            "email marketing subject", "email open rate",
            "subject line", "write subject lines",
        ],
        structure="""\
Role: Email marketing copywriter engineering subject lines for maximum deliverability and opens.

OUTPUT SECTIONS:

10 SUBJECT LINE VARIATIONS
   Mix: 2–3 curiosity-driven | 2–3 benefit-focused | 2 urgency-based | 2 personalised | 1 social-proof
   
   Per subject line:
   • Subject line text (40–60 characters, mobile-optimised)
   • Psychological driver (what emotion/motivation it triggers)
   • Spam risk: Low / Medium / High (with reason if Medium/High)
   • Performance tier prediction: Top / Mid / Test
   • Mobile preview text pairing (50–90 characters)

RULES APPLIED:
   • Zero spam trigger words (free, limited time, act now, ALL CAPS, excessive punctuation)
   • Each line delivers on its promise — no bait-and-switch
   • Variety in opening word (no 5 lines starting with "How")
""",
    ),

    "M4": ForgeTemplate(
        id="M4",
        domain="Marketing",
        name="Social Media Hooks",
        description="Platform-specific scroll-stopping opening lines with character counts",
        triggers=[
            "social media hooks", "scroll-stopping", "post opener",
            "first line of post", "engagement hook", "social media copy",
            "hook for post", "opening line",
        ],
        structure="""\
Role: Social media copywriter engineering opening lines that stop the scroll.

OUTPUT SECTIONS:

1. X / TWITTER HOOKS  (3 options, under 280 characters each)
   Style: high energy | pattern interrupt | bold claim | relatable tension | wit
   Per hook: text + character count + why it stops the scroll

2. LINKEDIN HOOKS  (2 options, under 280 characters each)
   Style: credible data point | contrarian professional insight | industry truth | personal revelation
   Per hook: text + character count + why it works on LinkedIn

3. INSTAGRAM / TIKTOK HOOKS  (2 options)
   Style: visual curiosity gap | "POV:" opener | challenge/transformation setup
   Per hook: text + character count + content type it suits

RULES:
   • Authentic — delivers on what it implies
   • No clickbait — the hook must connect to the post content
   • No "I" as the first word
""",
    ),

    "M5": ForgeTemplate(
        id="M5",
        domain="Marketing",
        name="Value Proposition Statements",
        description="Three positioning statement variants using standard formula with differentiation angles",
        triggers=[
            "value proposition", "positioning statement", "how to position",
            "differentiation statement", "competitive positioning",
            "product positioning", "value prop",
        ],
        structure="""\
Role: Brand strategist crafting positioning statements that carve a defensible market position.

OUTPUT SECTIONS:

3 POSITIONING STATEMENT VARIATIONS
   Formula: "For [target customer] who [customer need/pain], [product] is a [category] that [key benefit]. Unlike [primary alternative], we [primary differentiation]."

   Per variation:
   • Full positioning statement
   • Strategic focus: which angle this emphasises (e.g., speed / reliability / simplicity / cost)
   • Competitive advantage: the specific, defensible claim being made
   • Best use context: where to deploy this statement (website / sales / investor deck)

VARIATION ANGLES TO COVER:
   • Variation 1: Efficiency / Speed / ROI focused
   • Variation 2: Quality / Reliability / Trust focused
   • Variation 3: Innovation / Transformation / Future-state focused

CLOSING NOTE:
   Recommendation on which variation to lead with and why
""",
    ),

    "M6": ForgeTemplate(
        id="M6",
        domain="Marketing",
        name="Product Taglines",
        description="10 taglines across 5 styles: benefit, action, emotional, wordplay, and aspirational",
        triggers=[
            "product tagline", "brand slogan", "memorable phrase",
            "product slogan", "brand tagline", "catchy phrase",
            "tagline", "slogan",
        ],
        structure="""\
Role: Creative copywriter crafting taglines that attach instantly to memory.

OUTPUT: 10 TAGLINES ACROSS 5 STYLES  (7 words maximum each)

2 BENEFIT-FOCUSED
   Emphasise what the product does in outcome terms

2 ACTION-ORIENTED
   Inspire the audience to take or feel action

2 EMOTIONAL
   Evoke a feeling or aspiration without mentioning the product explicitly

2 CLEVER WORDPLAY
   Use puns, alliteration, double meanings, or linguistic surprise

2 ASPIRATIONAL
   Paint the transformation or higher purpose

Per tagline:
   • Tagline text
   • Style category
   • Appeal explanation: why it is memorable and what makes it work
   • Brand personality fit note (does it suit bold / serious / playful / premium?)
""",
    ),

    "M7": ForgeTemplate(
        id="M7",
        domain="Marketing",
        name="CTA Button Copy",
        description="Goal-specific CTA variants with microcopy and psychological rationale",
        triggers=[
            "cta copy", "button text", "call to action",
            "convert more clicks", "button copy", "micro-copy",
            "cta optimization", "cta button", "call to action copy",
        ],
        structure="""\
Role: Conversion micro-copy specialist turning hesitation into action.

For EACH conversion goal, provide 3 CTA VARIATIONS:

VARIATION 1 — Action + Gain
   • Button text (2–4 words)
   • Supporting microcopy (20–30 words below button): addresses the implicit fear
   • Psychological principle: [specify, e.g., Loss Aversion / Reciprocity / Social Proof]

VARIATION 2 — Trust + Reassurance
   • Button text
   • Supporting microcopy: specific concrete reassurance (timeline / guarantee / privacy / social proof)
   • Psychological principle

VARIATION 3 — Curiosity + Low Commitment
   • Button text
   • Supporting microcopy: makes the ask feel smaller
   • Psychological principle

PER GOAL, IDENTIFY:
   The fear beneath the conversion goal (e.g., "sign up" → fear of spam; "buy" → fear of regret; "book a call" → fear of sales pressure)
   Address this fear in every microcopy variation.
""",
    ),

    "M8": ForgeTemplate(
        id="M8",
        domain="Marketing",
        name="Feature Benefit Converter",
        description="Feature-to-customer-outcome translation with emotional pitch and conversational framing",
        triggers=[
            "feature to benefit", "convert features", "product features",
            "benefit selling", "turn features into benefits",
            "features to benefits", "translate features",
        ],
        structure="""\
Role: Customer benefit translator making product capabilities feel personally relevant.

For EACH feature, provide:

1. "SO WHAT?" EXPLANATION  (customer's perspective)
   • What problem this solves
   • What pain this removes
   • What desire this fulfils

2. BENEFIT ONE-LINER
   Punchy, outcome-focused, single memorable sentence
   (Not "Feature X does Y" but "You can now Z")

3. CONVERSATIONAL SALES PITCH  (2–3 sentences)
   • Start with the customer's situation/struggle
   • Show the transformation enabled
   • End with how the customer feels after using it

RULES:
   • Zero jargon — translate all technical terms
   • Lead with empathy, not capability
   • One emotional resonance point per feature
   • Never use "allows you to" or "enables users to"
""",
    ),

    "M9": ForgeTemplate(
        id="M9",
        domain="Marketing",
        name="Pain Point Agitation",
        description="Four-part pain-to-dream-state copy structure with emotional authenticity",
        triggers=[
            "pain point copy", "problem aware", "agitate pain",
            "customer frustrations", "empathetic copy", "problem-solution copy",
            "pain point", "customer pain",
        ],
        structure="""\
Role: Pain point copywriter who writes from deep empathy, not manipulation.

OUTPUT: 4 SECTIONS  (150–200 words each)

1. SURFACE PROBLEM
   What customers complain about to a friend — in their exact language
   Active voice | Short sentences | No marketing speak

2. UNDERLYING FRUSTRATION
   The emotional core beneath the stated problem
   Does this make them feel: inadequate / stuck / embarrassed / exhausted / powerless / unseen?
   Name it directly and honestly

3. COST OF INACTION
   Specific, concrete consequences:
   • Time lost (quantify if possible)
   • Opportunities missed
   • Relationships or outcomes affected
   • Confidence or capability eroded
   NOT vague doom — specific, believable stakes

4. DREAM STATE
   Sensory, emotional vision of success — what it feels like, not just looks like
   Contrast current frustration with this future state directly
   End with the customer as the hero of their own story

TONE: Authentic | Conversational | Never manipulative | Deliver hope, not fear
""",
    ),

    "M10": ForgeTemplate(
        id="M10",
        domain="Marketing",
        name="Objection Handling Responses",
        description="Sales objection responses with acknowledge-reframe-evidence structure and probe questions",
        triggers=[
            "sales objections", "handle objection", "rebut objection",
            "objection response", "when prospect says", "sales script",
            "objection handling",
        ],
        structure="""\
Role: Sales coach building objection handling frameworks rooted in empathy and evidence.

For EACH objection, provide:

1. ACKNOWLEDGE  (1–3 sentences)
   Validate the concern without dismissing it
   Opens with empathy, not counter-argument
   Example opener structure: "That's a completely valid concern. Many [role] we talk with feel the same way initially..."

2. REFRAME  (2–3 perspectives)
   Alternative ways to see the situation that shift context — not contradiction
   Each reframe: new lens + why it changes the picture

3. EVIDENCE  (specific proof points)
   • Metric or statistic with real numbers
   • Case study (type of customer + outcome)
   • Research or third-party validation

4. STRATEGIC QUESTIONS  (2–3 questions)
   Uncover the underlying concern rather than fight the surface objection
   Move the conversation toward the buyer's real situation

PROSPECT TYPE VARIATIONS:
   • Budget-conscious version
   • Risk-averse version
   • Feature-comparison focused version

PSYCHOLOGICAL DRIVER:
   Name the real fear beneath each stated objection
""",
    ),

    "M11": ForgeTemplate(
        id="M11",
        domain="Marketing",
        name="Testimonial Request Email",
        description="Authentic testimonial request with story-eliciting questions and non-pushy tone",
        triggers=[
            "request testimonial", "ask for review", "testimonial email",
            "get customer feedback", "review request email",
            "testimonial request", "ask for testimonial",
        ],
        structure="""\
Role: Customer success communicator eliciting genuine stories (not polished marketing copy).

EMAIL STRUCTURE:

1. PERSONALISED OPENING
   Reference a specific achievement or usage moment of this customer (not generic)

2. THREE SPECIFIC REFLECTION QUESTIONS
   Q1: "What problem were you trying to solve before you found us?" (before-state)
   Q2: "What's been the most unexpected or meaningful win since using [product]?" (outcome)
   Q3: "What would you tell a friend or colleague who was considering it?" (recommendation)

3. FORMAT OPTIONS OFFERED
   "Reply directly to this email" OR "Fill out this quick form [link]"

4. WARM CLOSING
   Express genuine interest in their story (not their marketing value)

TONE RULES:
   • Conversational, not corporate
   • Specific, not form-letter
   • Seeking a story, not a sales quote
   • No pressure — make opting out comfortable
   • Length: short (under 150 words for the ask itself)
""",
    ),

    "M12": ForgeTemplate(
        id="M12",
        domain="Marketing",
        name="Case Study Outline",
        description="Marketing case study structure with title options, pull-quote guidance, and visual assets",
        triggers=[
            "case study template", "case study structure", "outline a case study",
            "marketing case study", "customer story outline",
            "case study outline",
        ],
        structure="""\
Role: Case study strategist producing B2B proof assets that accelerate purchase decisions.

OUTPUT SECTIONS (in order):

1. TITLE OPTIONS  (5 variations)
   Each uses a different strategic angle:
   • Outcome-led: "[Result] in [Timeframe]"
   • Problem-led: "How [Company] Solved [Problem]"
   • Transformation: "From [Before State] to [After State]"
   • ROI-focused: "[%] improvement in [metric] with [solution]"
   • Audience-resonant: "[Role] at [Company] finally [achieved outcome]"

2. EXECUTIVE SUMMARY TEMPLATE  (150–200 words)
   Structure: industry + problem + solution chosen + headline result + why it matters

3. CHALLENGE SECTION GUIDANCE
   • Frame the problem in the client's language
   • Include business context (stakes, constraints, previous attempts)

4. SOLUTION SECTION GUIDANCE
   • Position the approach, not just the product
   • Highlight what was unique about the implementation

5. RESULTS SECTION GUIDANCE
   • Lead with the hardest quantitative metric
   • Layer: financial + operational + experiential outcomes
   • Include a timeline of impact

6. PULL-QUOTE OPPORTUNITIES  (4–5 strategic placements)
   Per placement: what stage of the story | type of quote to elicit | example question to ask the client

7. VISUAL ASSETS GUIDE
   Recommended charts, before/after comparisons, or process diagrams

8. CTA FRAMEWORK
   Narrative close + one clear next step for the reader
""",
    ),

    "M13": ForgeTemplate(
        id="M13",
        domain="Marketing",
        name="Pricing Page Copy",
        description="SaaS pricing tiers, feature comparison matrix, persona matching, and FAQ",
        triggers=[
            "pricing page", "write pricing tiers", "subscription plans",
            "plan descriptions", "pricing copy", "saas pricing page",
            "pricing page copy",
        ],
        structure="""\
Role: SaaS pricing copywriter making plan value immediately clear and upgrade paths obvious.

OUTPUT SECTIONS (in order):

1. PLAN NAMES & DESCRIPTIONS  (3–4 tiers)
   Per plan:
   • Memorable, meaning-ful name (not Starter/Pro/Enterprise if possible)
   • One-line value proposition for this tier
   • Price placeholder: [PRICE]/mo or [PRICE]/seat/mo
   • Best-for statement (one sentence describing the ideal customer)

2. FEATURE COMPARISON MATRIX
   Markdown table with:
   • Logical feature groupings (not one long list)
   • Specific values, not checkboxes (e.g., "50 projects" not ✓)
   • Clear upgrade justifiers: highlight what unlocks at each tier
   • Honest about lower-tier limitations

3. "WHICH PLAN IS RIGHT FOR ME?" SECTION
   3–4 customer personas:
   Per persona: Company size/role description → Recommended plan → One-sentence reasoning

4. FAQ ANSWERS  (6–8 questions)
   Cover: Billing cycle options | Contract length | Cancellation | Upgrade/downgrade process | Limits and overages | Discounts (annual / nonprofit / startup) | Trial details
   Tone: honest, including lower-tier limitations — builds trust

5. MICRO-COPY
   • "Most Popular" badge copy
   • Annual discount callout
   • Money-back guarantee statement if applicable
""",
    ),

    "M14": ForgeTemplate(
        id="M14",
        domain="Marketing",
        name="Email Welcome Sequence",
        description="5-email welcome series with narrative arc, per-email structure, and progressive CTAs",
        triggers=[
            "welcome email", "welcome sequence", "onboarding emails",
            "new subscriber emails", "first email series", "email nurture",
            "welcome email series",
        ],
        structure="""\
Role: Email marketing strategist building the critical first relationship with new subscribers.

SEQUENCE NARRATIVE ARC:
   Email 1: Warm welcome + relationship foundation
   Email 2: Core value demonstration (your best insight/content)
   Email 3: Social proof and community (you're not alone)
   Email 4: Exclusivity / what they unlocked by joining
   Email 5: Action / advocacy (time to take the next step)

Per EMAIL, provide:
   • Subject line
   • Preview text (50–90 characters)
   • Body structure: [Opening] → [Core content] → [CTA section]
   • Primary CTA (one action, clearly stated)
   • P.S. line (urgency / social proof / bonus offer)
   • Send timing (Day 0 / Day 2 / Day 5 / Day 8 / Day 14 suggested)

NARRATIVE CONTINUITY:
   Each email references the previous ("Last week I mentioned...")
   Tone progressively deepens: warm introduction → trusted advisor → confident invitation to act

TONE GUIDE:
   Conversational throughout | Never corporate | Second person singular ("you")
""",
    ),

    "M15": ForgeTemplate(
        id="M15",
        domain="Marketing",
        name="Competitive Positioning",
        description="Diplomatically framed competitive messaging that leads with strengths and trade-offs",
        triggers=[
            "position against competitors", "competitive messaging",
            "differentiate from competitors", "competitive copy", "vs competitor",
            "competitor comparison", "how we compare", "competitive differentiation",
        ],
        structure="""\
Role: Competitive positioning strategist writing messaging that is confident without being combative.

CORE PRINCIPLES:
   • Lead with your strengths, not competitor weaknesses
   • Use precise fact-based claims — no hyperbole
   • Acknowledge competitors serve legitimate needs
   • Reframe your limitations as intentional trade-offs

OUTPUT SECTIONS:

1. STRENGTH-LED NARRATIVE
   • Your 3 primary differentiators in order of customer importance
   • Specific, defensible proof point for each (metric / certification / methodology)

2. COMPARISON FRAMING
   Per key competitor dimension:
   • What the competitor does well (honest acknowledgement)
   • What you do differently (not "better" — different, for a specific customer need)
   • The customer profile that should choose you vs them

3. TRADE-OFF REFRAMES
   For each limitation of your product:
   "We prioritise [X] over [Y] because our customers value [Z]"
   Turn limitations into focus signals, not weaknesses

4. FORMAT SELECTION  (choose 1–2)
   [ ] Comparison matrix for website
   [ ] Sales battlecard for AEs
   [ ] Objection handling snippets
   [ ] Website competitive page narrative copy
   [ ] Pitch deck differentiation slide

5. TONE ENFORCEMENT
   Review your output against: professional | respectful | evidence-based | customer-centric
   Flag any claims that are vague, hyperbolic, or that could invite legal challenge
""",
    ),
}