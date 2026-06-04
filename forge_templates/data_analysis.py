"""
FORGE – Data Analysis domain templates  [D1 – D15]
"""

from .base import ForgeTemplate

DATA_ANALYSIS_TEMPLATES: dict[str, ForgeTemplate] = {

    "D1": ForgeTemplate(
        id="D1",
        domain="Data Analysis",
        name="Statistical Analysis Report",
        description="Descriptive stats, distribution analysis, outlier detection, and test recommendations",
        triggers=[
            "statistical analysis", "analyze data statistically",
            "descriptive statistics", "distribution analysis", "outlier detection",
            "statistics report", "analyze dataset", "statistical report",
        ],
        structure="""\
Role: Data statistician with expertise in exploratory data analysis and statistical inference.

OUTPUT SECTIONS (in order):

1. DATASET OVERVIEW
   • Number of observations and variables
   • Variable types (continuous, categorical, ordinal, datetime)
   • Data collection context and known limitations

2. DESCRIPTIVE STATISTICS TABLE
   Per variable: Mean | Median | Mode | Std Dev | Variance | Min | Max | Skewness | Kurtosis | Missing %

3. DISTRIBUTION ANALYSIS
   • Distribution type assessment per key variable
   • Normality testing approach (Shapiro-Wilk / K-S / visual Q-Q)
   • Goodness-of-fit considerations

4. OUTLIER DETECTION
   • IQR method results
   • Z-score method results
   • Impact of identified outliers on key statistics
   • Treatment recommendations (remove / transform / winsorise / retain)

5. HYPOTHESIS TESTING RECOMMENDATIONS
   • Appropriate tests per analytical question
   • Assumptions to verify before each test
   • Effect size considerations

6. KEY FINDINGS & INTERPRETATION

7. NEXT STEPS
   Recommended analyses based on initial findings
""",
    ),

    "D2": ForgeTemplate(
        id="D2",
        domain="Data Analysis",
        name="Data Quality Assessment",
        description="Comprehensive data quality audit with remediation roadmap",
        triggers=[
            "data quality", "data audit", "data cleaning", "missing values",
            "duplicates in data", "data integrity", "clean my data",
            "data issues", "dirty data",
        ],
        structure="""\
Role: Data quality auditor specialising in enterprise data governance.

OUTPUT SECTIONS (in order):

1. EXECUTIVE SUMMARY
   • Overall data quality score (0–100)
   • Count of critical issues requiring immediate action

2. DETAILED FINDINGS  (per issue type)
   Issue types: Missing values | Duplicates | Format inconsistencies | Type mismatches | Anomalies | Referential integrity violations
   Per issue: Description | Location (table/column) | Severity (Critical/High/Med/Low) | Root cause hypothesis | Affected record count and % | Sample examples

3. PRIORITISED REMEDIATION STRATEGIES
   Ranked by: business impact × effort (use 2×2 matrix)
   Per strategy: Approach | Complexity | Expected data quality improvement

4. IMPACT ASSESSMENT
   Cost of: No action vs Partial remediation vs Full remediation
   (Express in terms of downstream model accuracy, reporting reliability, compliance risk)

5. RISK MATRIX
   Data quality risk × business process affected

6. PHASED IMPLEMENTATION ROADMAP
   Week 1–2 (critical) | Month 1 (high) | Month 2–3 (medium) | Ongoing (monitoring)
""",
    ),

    "D3": ForgeTemplate(
        id="D3",
        domain="Data Analysis",
        name="Visualization Recommendation Engine",
        description="Chart selection guide with design spec, interactivity, and tool recommendations",
        triggers=[
            "what chart", "visualization", "best chart type",
            "how to visualize", "data visualization", "dashboard design",
            "which chart", "chart recommendation", "visualise",
        ],
        structure="""\
Role: Data visualisation consultant with expertise in perceptual design and BI tooling.

OUTPUT SECTIONS (in order):

1. ANALYSIS
   • Core analytical question being answered
   • Data characteristics: type | volume | dimensionality | time component
   • Audience technical level and context (executive / analyst / operational)

2. PRIMARY CHART RECOMMENDATION
   • Chart type with detailed rationale
   • Why it is best for this specific data and question

3. ALTERNATIVE OPTIONS  (2–3)
   Per alternative: chart type | trade-offs vs primary | when to prefer it

4. DESIGN SPECIFICATION
   • Colour palette (accessible, purposeful)
   • Typography hierarchy
   • Axis and scale choices
   • Data encoding decisions (position / length / colour / size)

5. INTERACTIVE FEATURES
   • Filtering, tooltips, brushing, drill-down recommendations
   • Implementation complexity per feature

6. TOOL RECOMMENDATION
   • Best tool(s) with rationale (e.g., Tableau, D3.js, Matplotlib, Plotly)
   • Data aggregation/preparation required before charting

7. LAYOUT SKETCH
   Text-based wireframe of the final visualisation layout
""",
    ),

    "D4": ForgeTemplate(
        id="D4",
        domain="Data Analysis",
        name="SQL Query Optimization",
        description="SQL performance analysis with optimised rewrite, indexes, and execution plan guide",
        triggers=[
            "optimize sql", "slow query", "sql performance", "rewrite sql",
            "improve database query", "query execution plan",
            "sql optimisation", "query optimization", "slow sql",
        ],
        structure="""\
Role: Database performance consultant specialising in query tuning and execution plan analysis.

OUTPUT SECTIONS (in order):

1. ORIGINAL QUERY ANALYSIS
   • Plain-language explanation of what the query does
   • Identified bottlenecks: full table scans | N+1 patterns | missing indexes | subquery issues | implicit conversions

2. OPTIMISED QUERY
   • Rewritten SQL with inline comments explaining each optimisation

3. PERFORMANCE IMPROVEMENTS
   • Estimated performance gain (%)
   • List of optimisation techniques applied

4. INDEX RECOMMENDATIONS
   • CREATE INDEX statements with rationale per index
   • Notes on index maintenance overhead

5. EXECUTION PLAN GUIDANCE
   • How to obtain and read the execution plan
   • What the optimised plan should look like vs original

6. ALTERNATIVE APPROACHES  (2–3)
   Per alternative: approach description | SQL code | pros | cons

7. ADDITIONAL CONSIDERATIONS
   Schema changes | Caching opportunities | Application-level optimisations
""",
    ),

    "D5": ForgeTemplate(
        id="D5",
        domain="Data Analysis",
        name="Predictive Modeling Blueprint",
        description="End-to-end ML strategy: features, algorithms, validation, tuning, and evaluation",
        triggers=[
            "machine learning model", "build a model", "prediction system",
            "ml strategy", "modeling approach", "classification", "regression",
            "build ml model", "predictive model", "machine learning",
        ],
        structure="""\
Role: Senior ML engineer designing production-ready predictive systems.

OUTPUT SECTIONS (in order):

1. FEATURE ENGINEERING
   • Numerical features: scaling, binning, interaction terms
   • Categorical features: encoding strategies (OHE, target encoding, embeddings)
   • Feature selection methods (correlation, importance, RFECV)
   • Missing value treatment strategy
   • Outlier handling approach
   • Domain-specific feature ideas

2. ALGORITHM SELECTION FRAMEWORK
   • Decision tree by problem type (classification vs regression vs ranking)
   • When to use: linear models | trees | ensembles | neural networks
   • Recommended algorithm(s) with justification for this use case

3. MODEL VALIDATION APPROACH
   • Train / validation / test split rationale
   • Cross-validation strategy (k-fold, stratified, time-series aware)
   • Out-of-distribution detection
   • Class imbalance handling (SMOTE, class weights, threshold tuning)

4. HYPERPARAMETER TUNING
   • Strategy: Grid vs Random vs Bayesian optimisation
   • Priority hyperparameters per model family
   • Early stopping criteria
   • Compute budget allocation

5. EVALUATION METRICS
   Classification: Precision | Recall | F1 | ROC-AUC | PR-AUC
   Regression: RMSE | MAE | R² | MAPE
   Business-aligned metric definition
   Fairness and calibration considerations
""",
    ),

    "D6": ForgeTemplate(
        id="D6",
        domain="Data Analysis",
        name="Business Intelligence Dashboard Spec",
        description="Complete BI dashboard specification: KPIs, drill-downs, refresh, and tech spec",
        triggers=[
            "bi dashboard", "dashboard specification", "kpi dashboard",
            "analytics dashboard", "business dashboard",
            "design dashboard", "build dashboard", "dashboard spec",
        ],
        structure="""\
Role: BI architect designing dashboards that drive executive and operational decisions.

OUTPUT SECTIONS (in order):

1. KPI DEFINITIONS
   Per metric: Name | Formula | Data source | Units and precision | Target | Warning threshold | Owner

2. METRIC CALCULATION LOGIC
   Step-by-step with field mappings | Aggregation method | Time periods | Null handling | Rounding rules

3. DATA REFRESH FREQUENCIES
   Per source: Frequency | Justification | SLA | Late-arriving data handling | Retention policy

4. DRILL-DOWN HIERARCHIES
   Navigation paths (e.g., Company → Region → Store → SKU)
   Dimensions available per level | Filtering logic | Performance notes

5. USER INTERACTION REQUIREMENTS
   Filters | Exports | Alerts and subscriptions | Scheduling | Mobile requirements

6. VISUAL DESIGN
   Card hierarchy | Chart types per metric | Colour coding conventions (green/amber/red)
   Critical metrics prominence | Progressive disclosure strategy

7. TECHNICAL SPECIFICATIONS
   Data volume and query performance targets | Concurrency | Caching strategy | Security and row-level access
""",
    ),

    "D7": ForgeTemplate(
        id="D7",
        domain="Data Analysis",
        name="Time Series Analysis Framework",
        description="Seasonality detection, forecasting model selection, and anomaly detection pipeline",
        triggers=[
            "time series", "forecasting", "temporal data", "seasonal patterns",
            "trend analysis", "anomaly detection", "predict future values",
            "time series analysis", "forecast demand",
        ],
        structure="""\
Role: Time-series specialist combining classical statistical methods with modern ML approaches.

OUTPUT SECTIONS (in order):

1. DATA ASSESSMENT
   • Stationarity tests: ADF, KPSS
   • ACF / PACF pattern interpretation
   • Data quality: gaps, irregular frequency, multiple seasonalities

2. SEASONALITY ANALYSIS
   • FFT to identify dominant frequencies
   • Seasonal strength measurement
   • Recommended seasonal periods with confidence

3. DECOMPOSITION SELECTION
   • Additive vs multiplicative rationale
   • STL decomposition vs classical: which and why
   • Visualisation guidance

4. FORECASTING RECOMMENDATION BY HORIZON
   • Short (1–7 periods): recommended model + justification
   • Medium (8–90 periods): recommended model + justification
   • Long (90+ periods): recommended model + justification
   • Multi-seasonal: TBATS / Prophet considerations

5. ANOMALY DETECTION FRAMEWORK
   • Statistical: Z-score | IQR | Grubbs' test
   • ML: Isolation Forest on residuals
   • Classification: spike vs level-shift vs pattern-break

6. IMPLEMENTATION ROADMAP
   Libraries/tools | Pseudocode for key steps | Validation strategy

7. SUCCESS CRITERIA
   Forecast accuracy targets (MAPE, RMSE) | Anomaly precision/recall targets
""",
    ),

    "D8": ForgeTemplate(
        id="D8",
        domain="Data Analysis",
        name="Cohort Analysis Design",
        description="Cohort strategy, retention metrics, LTV, and segmentation analysis",
        triggers=[
            "cohort analysis", "user cohorts", "retention analysis",
            "churn analysis", "customer lifetime value",
            "behavioral segments", "retention rate", "ltv analysis",
        ],
        structure="""\
Role: Cohort analysis specialist translating user behaviour data into retention strategy.

OUTPUT SECTIONS (in order):

1. COHORT DEFINITION STRATEGIES  (4–5 approaches)
   • Temporal cohorts (acquisition month/week)
   • Behavioural cohorts (first action taken)
   • Demographic / firmographic cohorts
   • Geographic cohorts
   Per approach: use case | when to prefer it | data requirements

2. BEHAVIOURAL METRICS FRAMEWORK  (8–10 metrics)
   Categories: Engagement | Monetisation | Growth
   Per metric: Name | Formula | Interpretation guide | Visualisation approach

3. RETENTION & CHURN CALCULATIONS
   • Day N retention formula and heatmap structure
   • Churn rate definition and rolling calculation
   • LTV formula with discount rate consideration

4. SEGMENTATION & LIFECYCLE ANALYSIS  (3–4 techniques)
   • RFM segmentation
   • Survival analysis (Kaplan-Meier)
   • Markov chain transition models
   • Activation milestone analysis

5. IMPLEMENTATION ROADMAP
   Phase 1: Basic retention table → Phase 2: Segmentation → Phase 3: Predictive
""",
    ),

    "D9": ForgeTemplate(
        id="D9",
        domain="Data Analysis",
        name="Python Data Pipeline Generator",
        description="Production-grade ETL pipeline with error handling, logging, and test patterns",
        triggers=[
            "data pipeline", "etl", "data engineering", "automate data processing",
            "build pipeline", "ingest data", "transform data",
            "python pipeline", "data ingestion",
        ],
        structure="""\
Role: Python data engineering architect designing production-ready ETL pipelines.

OUTPUT SECTIONS (in order):

1. ETL ORCHESTRATOR
   • Main class/function with type hints and docstrings
   • Configuration loading
   • Pipeline execution flow

2. EXTRACTION MODULE
   • Connectors for: databases (SQLAlchemy) | REST APIs | flat files (CSV/JSON/Parquet)
   • Incremental vs full-load strategy

3. TRANSFORMATION MODULE
   • Reusable transformation functions with type hints
   • Data validation step
   • Schema enforcement

4. LOADING MODULE
   • Target system handlers (DB / data warehouse / object storage)
   • Upsert vs insert strategy

5. ERROR HANDLING
   • Custom exception hierarchy
   • Retry logic with exponential backoff
   • Graceful degradation and dead-letter queue pattern

6. LOGGING
   • Structured logging (JSON) with contextual fields
   • Pipeline run metrics (rows extracted/transformed/loaded, duration)

7. CONFIGURATION MANAGEMENT
   • Environment-based config with validation (Pydantic)

8. SCHEDULING INTEGRATION
   • APScheduler / Airflow / Prefect compatibility notes

9. UNIT TEST PATTERNS
   • Mock strategies for external dependencies
   • Fixture examples

10. README
    Architecture diagram (text) | Setup | Config reference | Troubleshooting
""",
    ),

    "D10": ForgeTemplate(
        id="D10",
        domain="Data Analysis",
        name="Competitive Analysis Framework (Data)",
        description="Quantitative competitive intelligence with scoring model and strategic recs",
        triggers=[
            "data-driven competitive analysis", "competitive scoring model",
            "competitive intelligence framework", "benchmark competitors",
            "quantitative competitive analysis",
        ],
        structure="""\
Role: Competitive intelligence specialist building data-driven competitive models.

OUTPUT SECTIONS (in order):

1. COMPETITOR IDENTIFICATION
   • Direct competitors | Indirect competitors | Emerging threats
   With: offerings | target segments | market entry date

2. BENCHMARKING METRICS
   Categories: Financial performance | Product/service quality | Customer experience | Market reach | Operational efficiency | Brand/reputation
   Define formula and data source for each metric

3. MARKET POSITIONING ANALYSIS
   • 2×2 positioning map on two critical dimensions
   • White-space gaps and opportunities

4. DATA COLLECTION METHODOLOGIES
   • Primary (surveys, mystery shopping)
   • Secondary (filings, reviews, job postings as signals)
   • Digital signals (web traffic, app rankings, social share of voice)
   • Update cadence recommendation

5. COMPARATIVE SCORING SYSTEM
   • Weighted 1–10 scale with weight rationale per dimension
   • Competitive strength index formula
   • Trend indicators (improving / stable / declining per competitor)

6. STRATEGIC RECOMMENDATIONS
   3–5 actionable recommendations based on competitive gaps
""",
    ),

    "D11": ForgeTemplate(
        id="D11",
        domain="Data Analysis",
        name="Data Governance Policy",
        description="Data classification, RBAC, lineage, compliance mapping, and governance structure",
        triggers=[
            "data governance", "data policy", "data classification",
            "access control", "data compliance", "gdpr policy",
            "data lineage", "data governance framework",
        ],
        structure="""\
Role: Data governance architect designing enterprise-grade data management policies.

OUTPUT SECTIONS (in order):

1. DATA CLASSIFICATION SCHEME
   Tiers: Public | Internal | Confidential | Restricted
   Per tier: Classification criteria | Handling requirements | Reclassification process

2. ACCESS CONTROL FRAMEWORK
   • RBAC architecture (roles, permissions, data assets)
   • Principle of least privilege enforcement
   • Access request and review process
   • Segregation of duties matrix
   • Audit logging requirements

3. DATA LINEAGE DOCUMENTATION
   • Metadata standards
   • Data flow documentation templates
   • Retention periods per classification
   • Dependency and impact analysis process

4. COMPLIANCE MAPPING
   Traceability matrix: GDPR | CCPA | HIPAA | SOC 2 | ISO 27001
   Per regulation: applicable data | controls required | assessment frequency | remediation process

5. IMPLEMENTATION ROADMAP
   Foundation (month 1) | Classification (month 2) | Controls (month 3) | Monitoring (ongoing)

6. GOVERNANCE STRUCTURE
   • Data Owner, Data Steward, Data Custodian roles
   • Governance committee cadence and decision rights
""",
    ),

    "D12": ForgeTemplate(
        id="D12",
        domain="Data Analysis",
        name="A/B Testing Methodology",
        description="Statistically rigorous experiment design: sample size, duration, controls, interpretation",
        triggers=[
            "a/b test", "split test", "experiment design",
            "statistical significance", "sample size for experiment",
            "hypothesis test for product", "ab testing", "ab test",
            "run experiment",
        ],
        structure="""\
Role: A/B testing statistician ensuring experimental rigour and valid inference.

OUTPUT SECTIONS (in order):

1. SAMPLE SIZE CALCULATIONS
   • Formula with all parameters shown
   • Baseline conversion rate assumption
   • Minimum detectable effect (MDE) and justification
   • α (0.05) and power (0.80) settings with option to tighten
   • Concrete examples for 3 scenarios (conservative / base / optimistic)

2. STATISTICAL SIGNIFICANCE THRESHOLDS
   • α justification (one-tailed vs two-tailed choice with reasoning)
   • Multiple comparison corrections (Bonferroni / Benjamini-Hochberg) if running multiple variants
   • p-value decision rules (reject / fail to reject H₀)

3. TEST DURATION RECOMMENDATIONS
   • Factors: daily traffic | day-of-week effects | novelty effect | business cycles
   • Minimum duration guidelines
   • Early stopping risks (peeking problem)

4. EXTERNAL VARIABLE CONTROLS
   • Confounding variables to monitor
   • Blocking and stratification strategy
   • Randomisation unit (user vs session vs page)
   • Bias detection monitoring (SRM test)

5. RESULT INTERPRETATION GUIDELINES
   • Decision matrix: significant + positive | significant + negative | not significant
   • CI vs p-value comparison
   • Practical vs statistical significance distinction
   • How to document null results
""",
    ),

    "D13": ForgeTemplate(
        id="D13",
        domain="Data Analysis",
        name="Data Storytelling Structure",
        description="Narrative data presentation framework for executive and stakeholder audiences",
        triggers=[
            "data presentation", "present data", "data story",
            "data narrative", "communicate data insights", "data slide deck",
            "data storytelling", "tell story with data",
        ],
        structure="""\
Role: Data storytelling strategist translating complex analysis into compelling narratives.

OUTPUT SECTIONS (in order):

1. INSIGHT HIERARCHY
   • Executive "So What": the single most important business implication
   • Secondary "Why It Matters": supporting context
   • Tertiary "How We Know": evidence and methodology

2. CONTEXT-SETTING FRAMEWORK
   • Business context: what decision is this data informing?
   • Data scope: what period, segments, and sources?
   • Analytical approach: how was the analysis done?
   • Limitations and caveats upfront
   • Success metrics definition

3. EVIDENCE ORGANISATION  (5 layers)
   1. Headline number (the one number that matters)
   2. Comparative context (vs last period / benchmark / target)
   3. Statistical measures (confidence, sample size)
   4. Segment breakdowns
   5. Raw data / appendix

4. RECOMMENDATION PRESENTATION STRUCTURE
   Opportunity statement → Proposed action → Supporting evidence → Implementation roadmap → Risk mitigation → Quick wins vs strategic plays

5. VISUAL INTEGRATION GUIDELINES
   • Headline chart (the one that carries the story)
   • Supporting visuals (max 3 per section)
   • Colour use: purposeful, accessible, consistent
   • Annotation strategy: what to label directly on charts
   • Progressive disclosure: summary slide → detail slides

6. NARRATIVE FLOW TEMPLATE
   Slide 1: Framing | Slide 2: Context | Slide 3: Executive insight | Slides 4–6: Evidence | Slide 7: Recommendations | Slide 8: Action plan
""",
    ),

    "D14": ForgeTemplate(
        id="D14",
        domain="Data Analysis",
        name="Customer Segmentation Model",
        description="Clustering methodology, segment profiles, and actionable marketing strategy per segment",
        triggers=[
            "customer segmentation", "segment customers",
            "customer personas from data", "clustering customers",
            "identify customer groups", "customer segments",
            "rfm analysis", "customer clustering",
        ],
        structure="""\
Role: Customer segmentation data scientist bridging analytics and marketing strategy.

OUTPUT SECTIONS (in order):

1. CLUSTERING METHODOLOGY SELECTION
   • Algorithm comparison: K-means vs Hierarchical vs DBSCAN vs Gaussian Mixture
   • Justification for chosen approach given data characteristics
   • Cluster count determination: elbow method + silhouette score interpretation

2. SEGMENT PROFILES  (per segment)
   • Segment name (memorable, descriptive)
   • Description in plain language
   • Size (% of customers) and value metrics (revenue %, LTV)
   • Demographic profile
   • Behavioural characteristics (purchase frequency, channels, timing)
   • Distinguishing factors vs other segments

3. ACTIONABLE BUSINESS RECOMMENDATIONS  (per segment)
   • Marketing strategy (messaging, channels, offers)
   • Retention initiatives
   • Growth and upsell opportunities
   • Customer experience enhancements
   • Product/service tailoring recommendations
""",
    ),

    "D15": ForgeTemplate(
        id="D15",
        domain="Data Analysis",
        name="Data Analysis Workflow Automation",
        description="End-to-end automated analysis pipeline from ingestion to alerting and reporting",
        triggers=[
            "automate analysis", "analytics workflow", "automated reporting",
            "alerting pipeline", "data workflow automation",
            "automate reporting", "automated analytics",
        ],
        structure="""\
Role: Data engineering architect designing automated, observable analytics workflows.

OUTPUT STAGES (in order, each with: inputs → process → outputs → success/failure criteria):

1. INGESTION STAGE
   Source definitions | Schedule | Validation rules | Expected schema

2. QUALITY ASSURANCE STAGE
   Schema validation | Completeness checks | Outlier detection | Profiling thresholds

3. PROCESSING STAGE
   Transformation steps (ordered) | Aggregation logic | Derived metric calculations

4. ANALYSIS STAGE
   Statistical tests to run | Segmentation logic | Trend analysis methods

5. ALERTING STAGE
   Alert condition definitions | Tiered thresholds (warning / critical) | Notification routing (email / Slack / PagerDuty)

6. REPORTING STAGE
   Report generation logic | Distribution channels | Conditional formatting rules | Scheduling

7. ERROR HANDLING  (applies to all stages)
   Retry logic (attempts + backoff) | Failure notifications | Quarantine / dead-letter procedures

DECISION BRANCHES:
   Each stage must include explicit IF/THEN/ELSE logic for: data quality failures | threshold breaches | schema mismatches
""",
    ),
}