# Hauler Intelligence Engine

An agentic market intelligence pipeline for discovering, researching, validating, and ranking waste haulers by geography.

The prototype combines **AI-driven research** with **deterministic validation and scoring**. Agentic workflows handle ambiguous research tasks, while Python handles business rules, validation, and ICP ranking.

> **The agent handles ambiguity. Python handles trust.**

---

## Pipeline

```text
U.S. state
    ↓
01_source_discovery_agent.py
    ↓
AI discovers authoritative public hauler sources
    ↓
02_validate_sources.py
    ↓
Source relevance + extractability routing
    ↓
03_company_extraction_agent.py
    ↓
Source-backed private hauler records
    ↓
04_company_research_agent.py
    ↓
Website + contact + service + scale research
    ↓
05_validate_companies.py
    ↓
Deterministic validation
    ↓
06_score_companies.py
    ↓
100-point ICP scoring
    ↓
Ranked JSON + CSV
```

---

## 1. Source Discovery

`01_source_discovery_agent.py` accepts a U.S. state and uses agentic web research to locate authoritative public sources containing waste-hauler intelligence.

The agent prioritizes sources such as:

- State regulatory agencies
- Municipal and county governments
- Licensed or permitted hauler lists
- Franchise holder lists
- Commercial recycling lists
- Government databases
- Public PDFs and reports

Each source is classified by **ICP relevance** and **extractability**.

```text
DIRECT_LIST
DATABASE
HUB
REQUIREMENTS_PAGE
CONTRACT_RECORDS
UNKNOWN
```

A Florida test discovered authoritative sources including private roll-off franchise haulers, permitted hauler records, commercial recycling haulers, and government waste-management databases.

**Output:** `data/discovered_sources.json`

---

## 2. Source Routing

`02_validate_sources.py` applies deterministic rules to decide what happens to each discovered source.

```text
Discovered source
        ↓
ICP relevance
        ↓
Extractability
        ↓
Confidence thresholds
        ↓
EXTRACTABLE / RESOLUTION / REVIEW / REJECTED
```

| Route | Purpose |
|---|---|
| `EXTRACTABLE` | Contains usable company records |
| `RESOLUTION` | Relevant hub requiring deeper source discovery |
| `REVIEW` | Potentially useful but insufficiently clear |
| `REJECTED` | Out of scope or unsuitable |

This distinction matters because a source can be highly relevant to the ICP while still being unsuitable for direct company extraction.

In the Florida test, **3 sources were approved for direct extraction**, while a government database hub was correctly routed for resolution.

**Outputs:**

```text
data/extractable_sources.json
data/resolution_sources.json
data/review_sources.json
data/rejected_sources.json
```

---

## 3. Company Extraction

`03_company_extraction_agent.py` researches approved sources and extracts real private waste-service operators.

Target services include:

- Roll-off hauling
- Dumpster hauling
- Commercial waste collection
- Residential waste collection
- Recycling hauling
- Construction debris hauling
- Portable toilets
- Septic and liquid waste services

Every company must retain **source-backed evidence** connecting it to the authoritative source.

The engine excludes obvious non-ICP records such as government sanitation departments, landfill-only operations, equipment manufacturers, and brokers without hauling operations.

### Florida Test

```text
3 extractable sources available
        ↓
2 sources processed in Demo Mode
        ↓
10 companies extracted
        ↓
0 duplicates
        ↓
10 source-backed company records
```

Example companies discovered included:

- Action Recycling
- Anderson Rentals
- Central Florida Dumpsters
- Coastal Waste & Recycling
- Comfort House
- Atlantic Trash & Transfer
- Express Waste of Miami
- Everglades Waste Removal Services
- Envirowaste Services Group
- Trashco

**Output:** `data/discovered_companies.json`

---

## 4. Company Research & Enrichment

`04_company_research_agent.py` performs public research on extracted companies.

The agent attempts to verify or improve:

```text
Website
Phone
Location
Service lines
Operational scale signal
```

Scale signals can include:

- Geographic service territory
- Counties or cities served
- Branch locations
- Markets served
- Fleet size
- Employee count
- Municipal contracts
- Multi-state operations

The system does **not fabricate missing enrichment**.

If research fails or an external API is throttled, the original authoritative source-backed company record is retained.

### Florida Test

```text
5 companies researched
        ↓
3 successfully enriched
        ↓
2 research calls unavailable
        ↓
2 original source-backed records retained
        ↓
5 records continue through pipeline
```

This prevents an optional enrichment failure from becoming a false rejection.

**Output:** `data/enriched_companies.json`

---

## 5. Deterministic Validation

`05_validate_companies.py` determines whether researched records are trustworthy enough to enter the scoring layer.

Validation considers:

- Company identity
- Authoritative source evidence
- Discovery confidence
- Service fit
- Contactability
- Scale evidence
- Research confidence

Possible outcomes:

```text
VALIDATED
REVIEW
REJECTED
```

A key rule is:

> **Missing data is unknown, not negative evidence.**

For example, a company without a verified fleet-size signal is treated as:

```text
Scale: UNKNOWN
```

not:

```text
Company is small
```

This prevents incomplete public data from creating false-negative ICP decisions.

### Florida Test

```text
5 companies evaluated
        ↓
5 VALIDATED
0 REVIEW
0 REJECTED
```

**Output:** `data/validated_companies.json`

---

## 6. ICP Scoring

`06_score_companies.py` applies a deterministic 100-point ICP model.

| Scoring Dimension | Points |
|---|---:|
| Service Fit | 40 |
| Operational Complexity | 20 |
| Scale Signal | 20 |
| Data Confidence | 20 |
| **Total** | **100** |

### Service Fit — 40 Points

Measures alignment with core waste-hauling services.

### Operational Complexity — 20 Points

Rewards companies operating across multiple relevant service lines.

### Scale Signal — 20 Points

Rewards defensible evidence of operational scale or geographic reach.

### Data Confidence — 20 Points

Measures the strength of source evidence, discovery confidence, contactability, and successful research.

Missing scale evidence receives **0 scale points**, but does not reduce the company's underlying service-fit score.

**Outputs:**

```text
data/ranked_companies.json
data/ranked_companies.csv
```

---

## Demo Mode vs. Full Mode

Runtime settings are centralized in `config.py`.

### Demo Mode

Demo Mode is optimized for fast testing and live walkthroughs.

```text
Source target:          4
Extraction sources:     2
Companies per source:   5
Companies researched:   5
```

Run:

```bash
python run_demo.py
```

### Full Mode

Full Mode expands the working limits for broader market research.

```text
Source target:          12
Extraction sources:     10
Companies per source:   25
Companies researched:   100
```

Run:

```bash
HAULER_MODE=full python run_demo.py
```

These are configurable operating limits, not architectural limits.

---

## Running the Engine

Install dependencies:

```bash
pip install -r requirements.txt
```

Set an OpenAI API key:

```bash
export OPENAI_API_KEY="your-key"
```

Run the complete pipeline:

```bash
python run_demo.py
```

The engine will prompt:

```text
Enter a US state to research:
```

To restart from a specific stage:

```bash
python run_demo.py --from-stage 03
```

To display the latest results **without making any AI or web calls**:

```bash
python run_demo.py --summary-only
```

---

## Failure Tolerance

Agentic web research depends on external services and is inherently less predictable than local deterministic code.

The pipeline therefore includes:

- Bounded retries
- Request timeouts
- Checkpointing
- Preservation of completed outputs
- Graceful fallback to authoritative source-backed records

```text
Research succeeds
        ↓
Use enriched record

Research unavailable
        ↓
Retain source-backed record
        ↓
Continue deterministic validation
```

A temporary research failure does not destroy valid upstream data.

---

## Why Agentic?

The original hauler ICP prototype used manually configured Texas public sources.

That architecture works well once the sources are known, but geographic expansion creates a new problem:

```text
New state
    ↓
Find authoritative sources manually
    ↓
Inspect each source
    ↓
Determine whether it contains haulers
    ↓
Build or modify extraction logic
    ↓
Normalize records
```

This prototype moves the ambiguous portion upstream:

```text
State
    ↓
Agentic source discovery
    ↓
Source classification
    ↓
Agentic extraction / research
    ↓
Standardized records
    ↓
Deterministic validation
    ↓
Deterministic scoring
```

The downstream business logic remains stable even when the upstream source landscape changes.

---

## Design Philosophy

This system intentionally does **not** make every step an AI agent.

### AI is used for:

```text
Source discovery
Research
Interpretation
Heterogeneous extraction
Ambiguous web investigation
```

### Deterministic Python is used for:

```text
Business rules
Validation
Thresholds
Scoring
Ranking
Repeatability
Auditing
```

The objective is not to maximize AI usage.

The objective is to use AI where reasoning and flexibility create value while keeping consequential business rules reproducible and auditable.

---

## Production Evolution

This is a **working prototype**, not a proposed production deployment as-is.

A production implementation would likely add:

- Automated resolution of `HUB` sources
- Source and research caching
- Source freshness monitoring
- Queue-based execution
- Provider-aware rate limiting
- Cost and token observability
- Human-in-the-loop review
- Confidence-based model escalation
- Larger-scale source-quality evaluation

I would also benchmark public-source research against commercial enrichment providers before deciding what should be built versus bought.

The relevant production metrics would include:

```text
Cost per verified ICP account
Coverage
Accuracy
Refresh cost
Research latency
```

---

## Repository Structure

```text
config.py
run_demo.py

01_source_discovery_agent.py
02_validate_sources.py
03_company_extraction_agent.py
04_company_research_agent.py
05_validate_companies.py
06_score_companies.py

data/
├── discovered_sources.json
├── extractable_sources.json
├── resolution_sources.json
├── review_sources.json
├── rejected_sources.json
├── discovered_companies.json
├── enriched_companies.json
├── validated_companies.json
├── ranked_companies.json
└── ranked_companies.csv
```

---

## Final Output

The pipeline produces a ranked ICP dataset in both machine-readable and analyst-friendly formats:

```text
data/ranked_companies.json
data/ranked_companies.csv
```

---

## Status

The prototype currently demonstrates:

- **Geography-driven source discovery**
- **Agentic public-data research**
- **Source extractability classification**
- **Evidence-backed company extraction**
- **Resilient company enrichment**
- **Deterministic validation**
- **Deterministic ICP scoring**
- **Demo and Full execution modes**
- **Checkpointed failure tolerance**

The result is a working proof of how a manually configured, geography-specific hauler research process can evolve into a more scalable market intelligence system.
