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

# Small prototype limits to avoid rate-limit issues
MAX_SOURCES = 1
MAX_COMPANIES_PER_SOURCE = 5
MAX_TOTAL_COMPANIES = 5


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
        description=(
            "Confidence that this company is genuinely supported "
            "by the authoritative source as a relevant waste hauler."
        )
    )

    evidence: str


class SourceExtractionResult(BaseModel):
    source_name: str
    source_url: str
    companies: list[CompanyCandidate]


# ---------------------------------------------------------
# AGENT
# ---------------------------------------------------------

company_extraction_agent = Agent(
    name="Waste Hauler Company Extraction Agent",

    model=MODEL,

    instructions="""
You extract real private-sector waste-hauling companies from authoritative
government or regulatory sources.

You will receive ONE previously validated source.

Your task is to identify actual companies supported by that source.

TARGET COMPANY TYPES:

- roll-off hauling
- dumpster service
- residential waste collection
- commercial waste collection
- front-load service
- rear-load service
- recycling hauling
- permitted private waste hauling
- licensed private waste hauling
- franchised private waste collection

DO NOT RETURN:

- government sanitation departments
- municipalities or counties themselves
- landfills with no hauling operation
- transfer stations with no hauling operation
- equipment manufacturers
- brokers with no hauling operation
- hazardous-only operators
- waste-tire-only operators
- obvious duplicates or parser artifacts

RULES:

1. Use the supplied authoritative source as the primary evidence.

2. You may use web search to locate the actual list, PDF, permit page,
   or supporting page.

3. Do not invent companies.

4. Do not invent websites, phone numbers, locations, or service lines.

5. If a field cannot be verified, return null or an empty list.

6. Return no more than the requested maximum number of companies.

7. Prefer distinct private hauling companies.

8. Confidence should reflect how strongly the authoritative source supports
   the company's inclusion.

9. Keep evidence concise and specific.

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
    name = name.lower().strip()

    name = re.sub(
        r"\b(llc|l\.l\.c\.|inc|incorporated|corp|corporation|ltd)\b",
        "",
        name,
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
Extract a maximum of {MAX_COMPANIES_PER_SOURCE} real waste-hauling companies
from this validated source.

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

SOURCE RATIONALE:
{source["rationale"]}

The authoritative source must be the primary evidence for inclusion.

Return at most {MAX_COMPANIES_PER_SOURCE} companies.
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

    for source in test_sources:

        extraction = await extract_source(source)

        print(
            f"\nAgent returned "
            f"{len(extraction.companies)} companies."
        )

        all_companies.extend(extraction.companies)

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

            if company.confidence > existing.confidence:
                unique_companies[key] = company

    final_companies = list(unique_companies.values())
    final_companies = final_companies[:MAX_TOTAL_COMPANIES]

    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

    output = {
        "sources_processed": len(test_sources),
        "companies_before_deduplication": len(all_companies),
        "companies_after_deduplication": len(final_companies),
        "companies": [
            company.model_dump()
            for company in final_companies
        ],
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

    print("\nCOMPANY EXTRACTION COMPLETE")
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

        print(f"{i}. {company.company_name}")
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
