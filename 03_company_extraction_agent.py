import asyncio
import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from agents import Agent, Runner, WebSearchTool


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "accepted_sources.json"
OUTPUT_FILE = DATA_DIR / "discovered_companies.json"

MODEL = "gpt-5.6-luna"

MAX_SOURCES = 3
MAX_COMPANIES_PER_SOURCE = 10
MAX_TOTAL_COMPANIES = 25


# ---------------------------------------------------------
# STRUCTURED OUTPUT
# ---------------------------------------------------------

class CompanyCandidate(BaseModel):
    company_name: str
    location: Optional[str] = None

    phone: Optional[str] = None
    website: Optional[str] = None

    service_lines: list[str] = Field(default_factory=list)

    source_name: str
    source_url: str

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that this company is actually identified by the source as a waste-hauling operator."
    )

    evidence: str


class SourceExtractionResult(BaseModel):
    source_name: str
    source_url: str
    companies: list[CompanyCandidate]


# ---------------------------------------------------------
# EXTRACTION AGENT
# ---------------------------------------------------------

company_extraction_agent = Agent(
    name="Waste Hauler Company Extraction Agent",

    model=MODEL,

    instructions="""
You extract real waste-hauling companies from authoritative public sources.

You will receive ONE previously validated government or regulatory source.

Your job is to identify actual private-sector waste-hauling operators
supported by that source.

---------------------------------------------------------
TARGET COMPANY TYPES
---------------------------------------------------------

Prioritize companies involved in:

- roll-off hauling
- dumpster service
- residential waste collection
- commercial waste collection
- front-load service
- rear-load service
- recycling hauling
- franchised solid-waste collection
- permitted or licensed private waste hauling

---------------------------------------------------------
DO NOT RETURN
---------------------------------------------------------

Do not return:

- government sanitation departments
- counties or municipalities themselves
- landfills with no hauling operation
- transfer stations with no hauling operation
- equipment manufacturers
- brokers with no hauling operation
- hazardous-only operators
- tire-only operators
- obvious parser artifacts

---------------------------------------------------------
RESEARCH RULES
---------------------------------------------------------

1. Start with the supplied source and its URL.

2. Use web search when necessary to:
   - locate the actual list or document
   - confirm the company name
   - resolve basic details

3. Never invent a company.

4. Never invent phone numbers, websites, locations, or service lines.

5. If a field cannot be verified, return null or an empty list.

6. The supplied government source must be the primary evidence that the
   company belongs in this candidate universe.

7. Do not substitute generic Google results for source evidence.

8. Return no more than the requested maximum number of companies.

9. Prefer distinct private hauling companies over duplicate locations,
   DBAs, departments, or administrative records.

10. Confidence should represent confidence that the company genuinely
    appears to be a relevant hauler supported by the authoritative source.

Return structured output only.
""",

    tools=[
        WebSearchTool()
    ],

    output_type=SourceExtractionResult,
)


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def normalize_company_name(name: str) -> str:
    """
    Basic deterministic normalization used only for deduplication.
    """
    name = name.lower().strip()

    name = re.sub(
        r"\b(llc|l\.l\.c\.|inc|incorporated|corp|corporation|ltd)\b",
        "",
        name
    )

    name = re.sub(r"[^a-z0-9]+", " ", name)
    name = re.sub(r"\s+", " ", name)

    return name.strip()


def company_dedupe_key(company: CompanyCandidate) -> str:
    location = (company.location or "").lower().strip()

    return (
        normalize_company_name(company.company_name)
        + "|"
        + location
    )


# ---------------------------------------------------------
# EXTRACT ONE SOURCE
# ---------------------------------------------------------

async def extract_source(source: dict) -> SourceExtractionResult:

    print()
    print("-" * 70)
    print(f"Extracting: {source['source_name']}")
    print(f"URL: {source['source_url']}")
    print("-" * 70)

    prompt = f"""
Extract waste-hauling companies from this previously validated source.

SOURCE NAME:
{source["source_name"]}

SOURCE URL:
{source["source_url"]}

JURISDICTION:
{source["jurisdiction"]}

AUTHORITY:
{source["authority"]}

SOURCE TYPE:
{source["source_type"]}

ICP RELEVANCE:
{source["icp_relevance"]}

SOURCE DISCOVERY RATIONALE:
{source["rationale"]}

Return a maximum of {MAX_COMPANIES_PER_SOURCE} real companies.

The authoritative source above must be the primary evidence for inclusion.
"""

    result = await Runner.run(
        company_extraction_agent,
        prompt
    )

    return result.final_output


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

async def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing input file: {INPUT_FILE}"
        )

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        accepted_sources = json.load(f)

    if not accepted_sources:
        raise ValueError(
            "accepted_sources.json contains no sources."
        )

    test_sources = accepted_sources[:MAX_SOURCES]

    print("\nCOMPANY EXTRACTION TEST")
    print("=" * 70)

    print(f"Accepted sources available: {len(accepted_sources)}")
    print(f"Sources being tested:       {len(test_sources)}")
    print(f"Max companies per source:   {MAX_COMPANIES_PER_SOURCE}")
    print(f"Global company cap:         {MAX_TOTAL_COMPANIES}")

    all_companies = []

    # -----------------------------------------------------
    # AGENTIC EXTRACTION
    # -----------------------------------------------------

    for source in test_sources:

        extraction = await extract_source(source)

        print(
            f"\nAgent returned "
            f"{len(extraction.companies)} companies."
        )

        for company in extraction.companies:
            all_companies.append(company)

        if len(all_companies) >= MAX_TOTAL_COMPANIES:
            break

    # -----------------------------------------------------
    # DETERMINISTIC DEDUPLICATION
    # -----------------------------------------------------

    unique_companies = {}

    for company in all_companies:

        key = company_dedupe_key(company)

        if key not in unique_companies:
            unique_companies[key] = company

        else:
            existing = unique_companies[key]

            # Keep whichever record has higher confidence.
            if company.confidence > existing.confidence:
                unique_companies[key] = company

    final_companies = list(unique_companies.values())

    final_companies = final_companies[:MAX_TOTAL_COMPANIES]

    # -----------------------------------------------------
    # SAVE OUTPUT
    # -----------------------------------------------------

    output = {
        "sources_processed": len(test_sources),
        "companies_before_deduplication": len(all_companies),
        "companies_after_deduplication": len(final_companies),
        "companies": [
            company.model_dump()
            for company in final_companies
        ]
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False
        )

    # -----------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------

    print("\n")
    print("COMPANY EXTRACTION COMPLETE")
    print("=" * 70)

    print(
        f"Sources processed:              "
        f"{output['sources_processed']}"
    )

    print(
        f"Companies before deduplication: "
        f"{output['companies_before_deduplication']}"
    )

    print(
        f"Companies after deduplication:  "
        f"{output['companies_after_deduplication']}"
    )

    print(
        f"\nSaved structured output to:\n"
        f"{OUTPUT_FILE}\n"
    )

    print("DISCOVERED COMPANIES")
    print("-" * 70)

    for i, company in enumerate(
        final_companies,
        start=1
    ):

        print(
            f"{i}. {company.company_name}"
        )

        print(
            f"   Location: "
            f"{company.location or 'UNKNOWN'}"
        )

        print(
            f"   Website: "
            f"{company.website or 'UNKNOWN'}"
        )

        print(
            f"   Phone: "
            f"{company.phone or 'UNKNOWN'}"
        )

        print(
            f"   Services: "
            f"{', '.join(company.service_lines) if company.service_lines else 'UNKNOWN'}"
        )

        print(
            f"   Confidence: "
            f"{company.confidence:.2f}"
        )

        print(
            f"   Source: "
            f"{company.source_name}"
        )

        print(
            f"   Evidence: "
            f"{company.evidence}"
        )

        print()


if __name__ == "__main__":
    asyncio.run(main())
