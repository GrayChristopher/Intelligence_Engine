# Hauler Intelligence Engine

A prototype market-intelligence pipeline for discovering, researching, validating, and ranking private waste-hauling companies by geography.

The system combines agentic research for ambiguous discovery/research tasks with deterministic Python for validation, routing, and ICP scoring.

Core design principle:
Use AI where the research path is ambiguous. Use deterministic systems where reproducibility, trust, and business rules matter.

WHAT IT DOES

Given a U.S. state, the pipeline:

1. Uses AI-assisted web research to discover authoritative public data sources.
2. Classifies those sources by ICP relevance and extractability.
3. Extracts source-backed private waste-service companies.
4. Researches company websites, service lines, and scale signals.
5. Validates records using deterministic rules.
6. Scores and ranks companies against the target ICP.
7. Outputs ranked JSON and CSV datasets.

ARCHITECTURE

STATE INPUT
    ↓
01 AI SOURCE DISCOVERY
    ↓
02 DETERMINISTIC SOURCE ROUTING
    ↓
03 AI COMPANY EXTRACTION
    ↓
04 AI COMPANY RESEARCH / ENRICHMENT
    ↓
05 DETERMINISTIC VALIDATION
    ↓
06 DETERMINISTIC ICP SCORING
    ↓
RANKED JSON + CSV

WHY HYBRID?

The research problem is inherently messy.

Different states and municipalities publish hauler information in different formats:

- permit lists
- franchise lists
- regulatory databases
- PDFs
- municipal vendor pages
- public reporting portals
- government hubs linking to additional records

Hard-coding every possible source would create a brittle ingestion layer.

The agentic stages handle ambiguity:
- finding relevant sources
- interpreting source structure
- extracting company evidence
- researching missing company information

The deterministic stages handle trust:
- source routing
- validation thresholds
- ICP rules
- record acceptance
- scoring
- ranking

In short:

The agent handles ambiguity. Python handles trust.

PIPELINE STAGES

01 — AI Source Discovery

File:
01_source_discovery_agent.py

Input example:
Florida

The agent searches for authoritative public sources that may contain real private waste-service companies.

Preferred sources include:
- state regulatory agencies
- county or municipal government
- approved hauler lists
- franchise holder lists
- permit holder lists
- public waste-management databases
- government PDFs and reports

Each source is classified by:
- ICP relevance
- source type
- likelihood of containing real haulers
- source confidence
- extractability confidence

Example source types:
DIRECT_LIST
DATABASE
HUB
REQUIREMENTS_PAGE
CONTRACT_RECORDS
UNKNOWN

Output:
data/discovered_sources.json

02 — Deterministic Source Routing

File:
02_validate_sources.py

Sources are routed using deterministic business rules.

Possible routes:
EXTRACTABLE
RESOLUTION
REVIEW
REJECTED

A high-confidence government page that directly lists licensed haulers may be routed to EXTRACTABLE.

A government portal that only links to deeper datasets may be routed to RESOLUTION.

This prevents the extraction agent from wasting time on sources that do not directly contain usable company records.

Outputs:
data/extractable_sources.json
data/resolution_sources.json
data/review_sources.json
data/rejected_sources.json

03 — AI Company Extraction

File:
03_company_extraction_agent.py

The agent reads approved extractable sources and identifies real private waste-service companies.

Target company types include:
- roll-off hauling
- dumpster hauling
- residential waste collection
- commercial waste collection
- recycling hauling
- construction debris hauling

Adjacent services may include:
- portable toilets
- septic
- liquid waste
- restroom trailers

The system excludes:
- government sanitation departments
- landfill-only operations
- transfer-only operations
- equipment manufacturers
- brokers without hauling operations
- hazardous-waste-only operators

Every company record must contain source-backed evidence.

Output:
data/discovered_companies.json

04 — AI Company Research

File:
04_company_research_agent.py

The research agent enriches extracted companies using public web evidence.

It attempts to verify or improve:
- website
- phone
- location
- service lines

It also looks for one defensible operational scale signal, such as:
- counties served
- cities served
- geographic service area
- branch locations
- markets served
- fleet size
- employee count
- municipal contracts
- multi-state operations

Unknown values remain unknown.

The system does not invent missing enrichment.

If the research stage fails because of an API or web-service issue, the original authoritative source-backed record is retained.

Output:
data/enriched_companies.json

05 — Deterministic Validation

File:
05_validate_companies.py

Company records are validated using fixed rules rather than LLM judgment.

Validation considers:
- company identity
- authoritative source evidence
- discovery confidence
- service fit
- contactability
- scale evidence
- research confidence

Possible outcomes:
VALIDATED
REVIEW
REJECTED

Missing enrichment does not automatically mean poor fit.

For example:
No verified fleet size

is treated as:
UNKNOWN

not:
SMALL COMPANY

This avoids turning missing data into false negative business signals.

Output:
data/validated_companies.json

06 — Deterministic ICP Scoring

File:
06_score_companies.py

Validated companies are scored against the ICP.

The model currently uses four dimensions:

Service Fit: 40 points
Operational Complexity: 20 points
Scale Signal: 20 points
Data Confidence: 20 points
Total: 100 points

Service Fit
Measures alignment with core waste-hauling services.

Operational Complexity
Rewards companies with multiple relevant service lines.

Scale Signal
Rewards defensible evidence of operational scale.

Missing scale evidence receives no scale points, but does not reduce service-fit scoring.

Data Confidence
Measures the strength of source evidence, discovery confidence, contact data, and successful research.

Outputs:
data/ranked_companies.json
data/ranked_companies.csv

DEMO VS FULL MODE

The engine uses a centralized configuration file:
config.py

Two operating modes are available.

DEMO MODE

Default:
HAULER_MODE=demo

Designed for fast iteration and live walkthroughs.

Typical limits:
4 source targets
2 extraction sources
5 companies per source
5 companies researched

FULL MODE

Run with:
HAULER_MODE=full python run_demo.py

Full mode expands the working limits for broader research.

Typical configuration:
12 source targets
10 extraction sources
25 companies per source
100 companies researched

These values are configurable and are not architectural limits.

RUNNING THE ENGINE

Install Dependencies:
pip install -r requirements.txt

Set the OpenAI API key:
export OPENAI_API_KEY="your-key"

In Google Colab, the key can be loaded securely using environment variables or getpass.

Run the Entire Pipeline

Demo mode:
python run_demo.py

Full mode:
HAULER_MODE=full python run_demo.py

The first stage asks:
Enter a US state to research:

Example:
Florida

Start From a Specific Stage

If earlier outputs already exist:
python run_demo.py --from-stage 03

Available stages:
01
02
03
04
05
06

Show Existing Results Without API Calls

python run_demo.py --summary-only

This makes no AI or web-research calls.

It displays the latest pipeline state, including:
Sources discovered
Sources extractable
Companies extracted
Companies researched
Companies enriched
Companies validated
Companies ranked
Top ICP results

This is useful for demos when external API availability or rate limits are unpredictable.

EXAMPLE RUN

A Florida prototype run demonstrated the end-to-end workflow:

State
  ↓
authoritative sources discovered
  ↓
extractable sources routed
  ↓
real companies extracted
  ↓
public research/enrichment
  ↓
deterministic validation
  ↓
deterministic ICP ranking

The system successfully identified source-backed private operators, enriched available records, retained valid originals when enrichment was unavailable, and produced ranked JSON and CSV outputs.

FAILURE TOLERANCE

External research systems are not deterministic.

The pipeline therefore includes:
- bounded retries
- request timeouts
- checkpointing
- preservation of successful prior outputs
- graceful fallback to source-backed records

If enrichment fails, the system does not discard a company simply because an optional research call failed.

The authoritative record remains available for deterministic validation.

GEOGRAPHIC SCALABILITY

The original problem with a traditional scraper-based approach is that public waste data is geographically fragmented.

One state may publish licensed hauler PDFs, while another may expose county franchise lists, and another may only expose regulatory databases or municipal portals.

This prototype moves source acquisition into an agentic layer so the system can begin from STATE rather than PREPROGRAMMED URL.

The downstream schema remains consistent even when the upstream source landscape changes.

The architecture is state-generic, but public-source availability and quality will vary by geography.

PRODUCTION EVOLUTION

This repository is a working prototype, not the final production architecture.

A production version would likely add:

Source Resolution
Automatically follow HUB sources and identify the underlying extractable dataset.

Caching
Avoid repeating expensive source discovery and company research unnecessarily.

Queue-Based Execution
Move long-running research jobs into background workers.

Provider-Aware Rate Limiting
Manage concurrency and API throughput without manual intervention.

Source Freshness
Track when public datasets were last checked and automatically refresh stale records.

Monitoring and Observability

Track:
- agent success rate
- extraction yield
- enrichment success
- source quality
- validation rejection rates
- token usage
- research cost
- latency

Commercial Data Benchmarking

Public data should not automatically be assumed to be the optimal production data source.

At scale, I would benchmark:
commercial enrichment
vs.
public-source research
vs.
hybrid acquisition

against:
cost per verified ICP account
coverage
accuracy
refresh cost

Human-in-the-Loop Review

Low-confidence records could be routed for manual review rather than automatically accepted or rejected.

Confidence-Based Model Escalation

A production system could use lower-cost models for routine research and escalate only ambiguous records to stronger models.

DESIGN PHILOSOPHY

This prototype intentionally does not make every stage agentic.

LLMs are useful for:
research
interpretation
source discovery
heterogeneous extraction
ambiguous web investigation

Traditional code is better for:
business rules
validation
thresholds
scoring
ranking
repeatability
auditing

The objective is not to maximize AI usage.

The objective is to use the right execution model for each part of the system.

KEY FILES

config.py
run_demo.py

01_source_discovery_agent.py
02_validate_sources.py
03_company_extraction_agent.py
04_company_research_agent.py
05_validate_companies.py
06_score_companies.py

data/

OUTPUT

Final ranked datasets:
data/ranked_companies.json
data/ranked_companies.csv

STATUS

Working prototype demonstrating:
- geography-driven source discovery
- agentic public-data research
- source extractability classification
- evidence-backed company extraction
- resilient company enrichment
- deterministic validation
- deterministic ICP scoring
- demo and full execution modes
- checkpointed failure tolerance

The architecture is designed to demonstrate how an initially manual, geography-specific research process can evolve into a scalable market-intelligence system.
