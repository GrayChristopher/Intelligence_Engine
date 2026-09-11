# Hauler Intelligence Engine

An agentic market intelligence pipeline for discovering, researching, validating, and ranking waste haulers by geography.

The engine accepts a **U.S. state as its starting input** and dynamically researches where authoritative hauler data exists. It then extracts companies, researches available firmographic signals, validates the resulting records, and ranks them against a defined ICP.

The architecture intentionally combines **agentic AI research** with **deterministic Python controls**.

> **The agent handles ambiguity. Python handles trust.**

---

## Why I Built This

The original TrashLab ICP exercise required a scored list of 150+ Texas waste haulers using public data and available tools.

With no provided paid data, enrichment, or API budget, the initial system used known public sources and deterministic Python to produce the requested Texas dataset.

That approach is inexpensive and reproducible, but it exposes a scaling constraint:

```text
New geography
      ↓
Manually find authoritative sources
      ↓
Understand each source
      ↓
Configure ingestion
      ↓
Extract companies
      ↓
Normalize data
```

The Hauler Intelligence Engine explores what that architecture can become when an **AI/API research layer** is available.

Instead of beginning with a preconfigured source URL, the system begins with:

```text
STATE / MARKET
```

The engine then determines where to look.

---

## Architecture

```text
U.S. STATE
    ↓
01_source_discovery_agent.py
    ↓
AI SOURCE DISCOVERY
Find authoritative public hauler sources
    ↓
02_validate_sources.py
    ↓
DETERMINISTIC SOURCE ROUTING
Evaluate relevance + extractability
    ↓
03_company_extraction_agent.py
    ↓
AI COMPANY EXTRACTION
Extract source-backed private operators
    ↓
04_company_research_agent.py
    ↓
AI COMPANY RESEARCH
Research contact + service + scale signals
    ↓
05_validate_companies.py
    ↓
DETERMINISTIC VALIDATION
Apply evidence + ICP guardrails
    ↓
06_score_companies.py
    ↓
DETERMINISTIC ICP SCORING
Rank validated companies
    ↓
RANKED JSON + CSV
```

The pipeline separates **research decisions** from **business decisions**.

AI is used where the path is ambiguous.

Deterministic code is used where the result should be reproducible and auditable.

---

## 1. Source Discovery

`01_source_discovery_agent.py`

The pipeline begins with a user-supplied U.S. state.

```text
Enter a US state to research:
```

The discovery agent searches for authoritative public sources that may contain real private waste-service operators.

Priority sources include:

- State regulatory agencies
- County and municipal governments
- Approved hauler lists
- Franchise holder lists
- Permit holder lists
- Public waste-management databases
- Government PDFs and reports

Each discovered source is evaluated for:

- ICP relevance
- Source type
- Likelihood of containing haulers
- Source confidence
- Extractability confidence

Source types include:

```text
DIRECT_LIST
DATABASE
HUB
REQUIREMENTS_PAGE
CONTRACT_RECORDS
UNKNOWN
```

The objective is not simply to find waste-related webpages.

The objective is to identify **authoritative sources capable of producing useful market intelligence**.

**Output:**

```text
data/discovered_sources.json
```

---

## 2. Source Routing

`02_validate_sources.py`

The discovery agent can identify potentially useful sources, but the agent does not decide which sources automatically enter extraction.

That decision is handled by deterministic Python rules.

```text
DISCOVERED SOURCE
       ↓
ICP relevance
       ↓
Source type
       ↓
Contains haulers?
       ↓
Confidence thresholds
       ↓
ROUTE
```

Possible routes:

| Route | Meaning |
|---|---|
| `EXTRACTABLE` | Source directly contains usable company records |
| `RESOLUTION` | Relevant source hub requiring another step |
| `REVIEW` | Potentially useful but does not meet automatic extraction rules |
| `REJECTED` | Source is outside the target ICP |

For example:

```text
CORE + DIRECT_LIST + high confidence
                ↓
           EXTRACTABLE
```

while:

```text
CORE + DATABASE + low extractability confidence
                ↓
              REVIEW
```

This prevents an AI-discovered source from automatically becoming trusted pipeline input.

**Outputs:**

```text
data/extractable_sources.json
data/resolution_sources.json
data/review_sources.json
data/rejected_sources.json
```

---

## 3. Company Extraction

`03_company_extraction_agent.py`

The extraction agent processes sources approved by the deterministic routing layer.

It searches those sources for real private waste-service companies and converts heterogeneous public records into a standardized company schema.

Core service targets include:

- Roll-off hauling
- Dumpster hauling
- Residential waste collection
- Commercial waste collection
- Recycling hauling
- Construction debris hauling

Relevant adjacent services may include:

- Portable toilets
- Septic
- Liquid waste
- Restroom trailers

The engine excludes obvious non-ICP entities such as:

- Government sanitation departments
- Landfill-only operations
- Transfer-only facilities
- Equipment manufacturers
- Brokers without hauling operations
- Clearly unrelated specialty operators

Every extracted company retains **source-backed evidence**.

The system does not rely on the model simply asserting that a company exists or fits the ICP.

**Output:**

```text
data/discovered_companies.json
```

---

## 4. Company Research & Enrichment

`04_company_research_agent.py`

Once companies have been extracted from authoritative sources, the research agent attempts to improve the available record using public web evidence.

Research targets include:

```text
Website
Phone
Location
Service lines
Operational scale signal
```

Useful scale signals can include:

- Counties served
- Cities served
- Geographic service territory
- Branch locations
- Markets served
- Fleet size when explicitly supported
- Employee count when explicitly supported
- Municipal contracts
- Multi-state operations

The research layer follows an important rule:

> **Unknown is preferable to fabricated.**

If a field cannot be defensibly verified, it can remain unknown.

If an optional research request fails because of an external service or API issue, the original authoritative source-backed record is retained rather than discarded.

**Output:**

```text
data/enriched_companies.json
```

---

## 5. Deterministic Validation

`05_validate_companies.py`

The validation layer determines whether company records are trustworthy enough to proceed to ICP scoring.

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

A core principle of the validator is:

> **Missing evidence is not negative evidence.**

For example, if public research cannot verify fleet size:

```text
Scale signal = UNKNOWN
```

The system does **not** infer:

```text
Company = SMALL
```

This prevents incomplete enrichment from creating false-negative ICP decisions.

**Output:**

```text
data/validated_companies.json
```

---

## 6. ICP Scoring

`06_score_companies.py`

Validated companies are ranked using a deterministic 100-point ICP model.

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

Rewards operators with multiple relevant service lines.

### Scale Signal — 20 Points

Rewards defensible evidence of operational scale or geographic reach.

### Data Confidence — 20 Points

Measures the strength of:

- Source evidence
- Discovery confidence
- Contactability
- Successful research

Missing scale evidence receives no scale points, but it does not reduce the company's underlying service-fit score.

**Outputs:**

```text
data/ranked_companies.json
data/ranked_companies.csv
```

---

## Demo Mode

The engine includes a bounded Demo Mode for development and live walkthroughs.

Run:

```bash
python run_demo.py
```

The pipeline asks for a state:

```text
Enter a US state to research:
```

Demo Mode runs the **real pipeline** with deliberately reduced volume.

Typical configuration:

```text
Source targets:          4
Extraction sources:      2
Companies per source:    5
Companies researched:    5
```

This allows the complete architecture to be demonstrated without requiring a large research job.

Demo Mode is not a simulated dataset.

The agentic stages still perform real research against the selected geography.

---

## Full Mode

The same architecture can run with larger operating limits.

```bash
HAULER_MODE=full python run_demo.py
```

Typical Full Mode configuration:

```text
Source targets:          12
Extraction sources:      10
Companies per source:    25
Companies researched:    100
```

These values are configurable in:

```text
config.py
```

They are operating limits rather than architectural limits.

Production scale would require additional infrastructure beyond simply increasing these values.

---

## Running the Engine

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Set API Credentials

```bash
export OPENAI_API_KEY="your-key"
```

Credentials should be stored as environment variables and are excluded from source control.

### Run Demo Mode

```bash
python run_demo.py
```

### Run Full Mode

```bash
HAULER_MODE=full python run_demo.py
```

### Resume From a Specific Stage

Completed upstream outputs can be reused:

```bash
python run_demo.py --from-stage 03
```

Available stages:

```text
01
02
03
04
05
06
```

### View Existing Results Without API Calls

```bash
python run_demo.py --summary-only
```

Summary Mode makes no new AI research calls.

It reports the current pipeline state and ranked output from completed runs.

---

## Failure Tolerance

Agentic research depends on external APIs and web services, so those stages are inherently less predictable than local deterministic code.

The pipeline therefore includes:

- Bounded retries
- Request timeouts
- Checkpointing
- Preservation of completed outputs
- Graceful fallback to source-backed records

The intended behavior is:

```text
Research succeeds
        ↓
Use enriched record
```

or:

```text
Research unavailable
        ↓
Preserve authoritative record
        ↓
Continue where evidence allows
```

A temporary enrichment failure should not destroy valid upstream data.

---

## Why Hybrid Instead of Fully Agentic?

This prototype intentionally does **not** turn every pipeline stage into an AI agent.

### AI is useful for:

```text
Source discovery
Web research
Source interpretation
Heterogeneous extraction
Company research
Ambiguous investigation
```

These tasks involve uncertainty and research paths that cannot always be predetermined.

### Deterministic Python is useful for:

```text
Business rules
Confidence thresholds
Validation
Routing
Scoring
Ranking
Auditing
```

These tasks should behave consistently when given the same inputs.

The objective is not to maximize AI usage.

The objective is to use the appropriate execution model for each problem.

---

## From Hard-Coded Sources to Market-Driven Discovery

The architectural difference between the original Texas prototype and this engine can be summarized simply:

### Original Approach

```text
KNOWN TEXAS SOURCE
        ↓
Known parser
        ↓
Extract
        ↓
Validate
        ↓
Score
```

### Agentic Approach

```text
STATE / MARKET
        ↓
Discover where the data lives
        ↓
Evaluate the source
        ↓
Extract companies
        ↓
Research companies
        ↓
Validate
        ↓
Score
```

The first architecture is highly effective when the source universe is already known.

The second explores how to reduce the manual research required when entering new markets.

---

## Production Evolution

This repository is a **working prototype**, not a proposed production deployment as-is.

A production implementation would likely add several capabilities.

### Source Resolution

Automatically investigate `HUB` sources and locate the underlying extractable datasets.

### Caching

Avoid repeating source discovery and company research when valid results already exist.

### Source Freshness

Track when authoritative datasets were last checked and schedule refreshes accordingly.

### Queue-Based Execution

Move long-running research jobs into managed workers rather than synchronous execution.

### Provider-Aware Rate Limiting

Control request throughput, concurrency, retries, and model/provider limits.

### Observability

Track metrics such as:

```text
Source discovery success
Extraction yield
Enrichment success
Validation outcomes
Research latency
Token usage
API cost
Cost per verified account
```

### Human-in-the-Loop Review

Route ambiguous or low-confidence records to manual review rather than forcing an automated decision.

### Confidence-Based Model Escalation

Use cost-efficient models for routine research and escalate only difficult records when additional reasoning is justified.

### Commercial Data Benchmarking

Public-source research should not automatically be assumed to be the optimal production acquisition strategy.

At scale, I would compare:

```text
Commercial data
vs.
Public-source research
vs.
Hybrid acquisition
```

using metrics such as:

```text
Cost per verified ICP account
Coverage
Accuracy
Refresh cost
Research latency
```

The production architecture should ultimately be chosen based on business requirements and economics rather than the prototype implementation.

---

## Validation

The architecture has been tested against multiple U.S. states without adding state-specific source configurations.

Testing has demonstrated:

- Dynamic discovery of different authoritative sources by geography
- Classification of direct lists, databases, and other source types
- Deterministic routing of AI-discovered sources
- Source-backed company extraction
- Public company research and enrichment
- Preservation of valid records when optional research is unavailable
- Deterministic company validation
- Deterministic ICP scoring
- Fresh-environment repository installation and execution

Public-source availability and quality naturally vary by geography, so identical coverage is not assumed across every state.

The purpose of the prototype is to demonstrate a **geography-driven research architecture**, not to claim uniform nationwide public-data coverage.

---

## Repository Structure

```text
Intelligence_Engine/
│
├── README.md
├── requirements.txt
├── .gitignore
│
├── config.py
├── run_demo.py
│
├── 01_source_discovery_agent.py
├── 02_validate_sources.py
├── 03_company_extraction_agent.py
├── 04_company_research_agent.py
├── 05_validate_companies.py
├── 06_score_companies.py
│
└── data/
```

Generated runtime data is excluded from source control.

---

## Outputs

The final ranked account dataset is written to:

```text
data/ranked_companies.json
data/ranked_companies.csv
```

JSON provides a structured machine-readable output.

CSV provides a convenient analyst and GTM workflow output.

---

## Status

The prototype currently demonstrates:

- **State-driven source discovery**
- **Agentic public-data research**
- **Source relevance and extractability classification**
- **Evidence-backed company extraction**
- **Company research and enrichment**
- **Deterministic source routing**
- **Deterministic company validation**
- **Deterministic ICP scoring**
- **Demo and Full execution modes**
- **Checkpointed failure tolerance**
- **Geographic portability without hard-coded state sources**

The engine is a proof of how a manually configured market-research workflow can evolve into a more dynamic, agent-assisted intelligence system while retaining deterministic controls around data quality and business decisions.
