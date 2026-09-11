import asyncio
import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from agents import Agent, Runner, WebSearchTool
from openai import RateLimitError


# =========================================================
# CONFIG
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "discovered_companies.json"
OUTPUT_FILE = DATA_DIR / "enriched_companies.json"

MODEL = "gpt-5.6-luna"

MAX_COMPANIES = 5
MAX_ATTEMPTS = 2
ATTEMPT_TIMEOUT_SECONDS = 75
RETRY_WAIT_SECONDS = 15
INTER_COMPANY_DELAY_SECONDS = 5


# =========================================================
# STRUCTURED OUTPUT
# =========================================================

class EnrichedCompany(BaseModel):

    company_name: str

    location: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None

    service_lines: list[str] = Field(
        default_factory=list
    )

    size_signal: Optional[str] = None

    size_signal_type: Optional[str] = None

    research_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    evidence: str


# =========================================================
# RESEARCH AGENT
# =========================================================

research_agent = Agent(

    name="Waste Hauler Company Research Agent",

    model=MODEL,

    instructions="""
You are the company-research layer of a waste-hauler intelligence system.

You receive ONE company that was already identified from an authoritative
government source.

Your job is to VERIFY existing information and FILL IMPORTANT GAPS.

Do not replace good source-backed data merely to produce different data.


=========================================================
RESEARCH PRIORITIES
=========================================================

Research, when reasonably verifiable:

1. Official company website
2. Business location
3. Phone number
4. Waste-hauling service lines
5. ONE useful size or operational-scale signal


=========================================================
SERVICE LINES
=========================================================

Examples include:

- roll-off
- dumpster rental
- residential waste
- commercial waste
- front-load
- rear-load
- recycling
- construction debris
- portable toilet
- septic
- liquid waste

Only include service lines supported by evidence.


=========================================================
SIZE / SCALE SIGNAL
=========================================================

Look for ONE defensible signal of operational scale.

Examples:

- number of locations
- geographic service area
- fleet/truck count
- employee count
- number of markets served
- number of branches
- municipal contracts
- multi-county coverage
- multi-state operations
- explicit company scale description

Prefer concrete evidence.

Do NOT invent employee counts, fleet counts, revenue, or locations.

If no reliable scale signal can be found, return null.


=========================================================
SOURCE QUALITY
=========================================================

Prefer:

1. Official company website
2. Government source
3. Official municipal/county records
4. Other credible first-party sources

Avoid using generic directories when better evidence exists.


=========================================================
IMPORTANT RULES
=========================================================

Do not invent facts.

Do not guess missing values.

Unknown is acceptable.

Preserve existing information when it is already supported and you cannot
find stronger contradictory evidence.

Do not confuse similarly named companies.

The evidence field should briefly explain what was actually verified.

Return structured output only.
""",

    tools=[
        WebSearchTool()
    ],

    output_type=EnrichedCompany,
)


# =========================================================
# NORMALIZATION
# =========================================================

def normalize_url(value):

    if not value:
        return None

    value = value.strip()

    if value.upper() == "UNKNOWN":
        return None

    return value


def normalize_phone(value):

    if not value:
        return None

    value = value.strip()

    if value.upper() == "UNKNOWN":
        return None

    return value


# =========================================================
# CHECKPOINT
# =========================================================

def save_checkpoint(
    state,
    enriched_companies,
    processed,
):

    payload = {
        "state": state,
        "processed": processed,
        "companies": enriched_companies,
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
        )


# =========================================================
# RESEARCH ONE COMPANY
# =========================================================

async def research_company(
    state,
    company,
):

    company_name = company.get(
        "company_name",
        "UNKNOWN",
    )

    existing_location = (
        company.get("location")
        or "UNKNOWN"
    )

    existing_phone = (
        company.get("phone")
        or "UNKNOWN"
    )

    existing_website = (
        company.get("website")
        or "UNKNOWN"
    )

    existing_services = (
        company.get("service_lines")
        or []
    )

    source_name = (
        company.get("source_name")
        or "UNKNOWN"
    )

    source_url = (
        company.get("source_url")
        or "UNKNOWN"
    )

    source_evidence = (
        company.get("evidence")
        or "UNKNOWN"
    )

    prompt = f"""
Research and enrich this waste-hauling company.

STATE:
{state}

COMPANY:
{company_name}

EXISTING LOCATION:
{existing_location}

EXISTING PHONE:
{existing_phone}

EXISTING WEBSITE:
{existing_website}

EXISTING SERVICE LINES:
{existing_services}

AUTHORITATIVE DISCOVERY SOURCE:
{source_name}

SOURCE URL:
{source_url}

SOURCE EVIDENCE:
{source_evidence}

Verify the existing information and fill useful gaps.

Find ONE defensible size/scale signal if possible.

Do not invent missing information.

Do not confuse this company with another similarly named company.

Unknown values are acceptable.
"""

    for attempt in range(
        1,
        MAX_ATTEMPTS + 1,
    ):

        print(
            f"   Research attempt "
            f"{attempt}/{MAX_ATTEMPTS}..."
        )

        try:

            result = await asyncio.wait_for(

                Runner.run(
                    research_agent,
                    prompt,
                ),

                timeout=ATTEMPT_TIMEOUT_SECONDS,
            )

            return result.final_output

        except asyncio.TimeoutError:

            print(
                "   Research attempt timed out."
            )

            if attempt == MAX_ATTEMPTS:
                return None

            print(
                f"   Retrying in "
                f"{RETRY_WAIT_SECONDS} seconds..."
            )

            await asyncio.sleep(
                RETRY_WAIT_SECONDS
            )

        except RateLimitError:

            print(
                "   OpenAI rate limit reached."
            )

            if attempt == MAX_ATTEMPTS:
                return None

            print(
                f"   Retrying in "
                f"{RETRY_WAIT_SECONDS} seconds..."
            )

            await asyncio.sleep(
                RETRY_WAIT_SECONDS
            )

        except Exception as exc:

            text = str(exc).lower()

            if (
                "429" in text
                or "rate limit" in text
                or "tokens per min" in text
            ):

                print(
                    "   OpenAI rate limit detected."
                )

                if attempt == MAX_ATTEMPTS:
                    return None

                print(
                    f"   Retrying in "
                    f"{RETRY_WAIT_SECONDS} seconds..."
                )

                await asyncio.sleep(
                    RETRY_WAIT_SECONDS
                )

            else:

                print(
                    f"   Research error: {exc}"
                )

                return None

    return None


# =========================================================
# MERGE
# =========================================================

def merge_company(
    original,
    enriched,
):

    if enriched is None:

        result = dict(original)

        result["size_signal"] = None
        result["size_signal_type"] = None
        result["research_confidence"] = 0.0
        result["research_evidence"] = (
            "Research unavailable; retained "
            "authoritative extraction record."
        )

        return result

    result = dict(original)

    # Preserve the company identity from extraction.
    result["company_name"] = original.get(
        "company_name"
    )

    # Fill or verify useful fields.
    if enriched.location:
        result["location"] = enriched.location

    if enriched.phone:
        result["phone"] = normalize_phone(
            enriched.phone
        )

    if enriched.website:
        result["website"] = normalize_url(
            enriched.website
        )

    if enriched.service_lines:
        result["service_lines"] = (
            enriched.service_lines
        )

    result["size_signal"] = (
        enriched.size_signal
    )

    result["size_signal_type"] = (
        enriched.size_signal_type
    )

    result["research_confidence"] = (
        enriched.research_confidence
    )

    # Keep original discovery evidence separate.
    result["research_evidence"] = (
        enriched.evidence
    )

    return result


# =========================================================
# MAIN
# =========================================================

async def main():

    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print("COMPANY RESEARCH / ENRICHMENT")
    print("=" * 72)

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"Missing input file: {INPUT_FILE}"
        )

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8",
    ) as file:

        payload = json.load(file)

    state = payload.get(
        "state",
        "UNKNOWN",
    )

    companies = payload.get(
        "companies",
        [],
    )

    selected_companies = companies[
        :MAX_COMPANIES
    ]

    print()
    print(
        f"State: {state}"
    )

    print(
        f"Companies available: "
        f"{len(companies)}"
    )

    print(
        f"Companies selected for research: "
        f"{len(selected_companies)}"
    )

    print()

    enriched_companies = []
    processed = []

    # =====================================================
    # PROCESS SEQUENTIALLY
    # =====================================================

    for index, company in enumerate(
        selected_companies,
        start=1,
    ):

        company_name = company.get(
            "company_name",
            "UNKNOWN",
        )

        print("=" * 72)

        print(
            f"COMPANY {index}/"
            f"{len(selected_companies)}"
        )

        print(
            company_name
        )

        print("=" * 72)

        result = await research_company(
            state,
            company,
        )

        merged = merge_company(
            company,
            result,
        )

        enriched_companies.append(
            merged
        )

        if result is None:

            status = "RETAINED_ORIGINAL"

            print()
            print(
                "   Research unavailable."
            )

            print(
                "   Original extraction record retained."
            )

        else:

            status = "ENRICHED"

            print()
            print(
                f"   Website: "
                f"{merged.get('website') or 'UNKNOWN'}"
            )

            print(
                f"   Phone: "
                f"{merged.get('phone') or 'UNKNOWN'}"
            )

            print(
                f"   Location: "
                f"{merged.get('location') or 'UNKNOWN'}"
            )

            print(
                f"   Services: "
                f"{', '.join(merged.get('service_lines', [])) or 'UNKNOWN'}"
            )

            print(
                f"   Size signal: "
                f"{merged.get('size_signal') or 'UNKNOWN'}"
            )

            print(
                f"   Research confidence: "
                f"{merged.get('research_confidence', 0):.2f}"
            )

        processed.append(
            {
                "company_name": company_name,
                "status": status,
            }
        )

        save_checkpoint(
            state,
            enriched_companies,
            processed,
        )

        if (
            index
            < len(selected_companies)
        ):

            print()
            print(
                f"Waiting "
                f"{INTER_COMPANY_DELAY_SECONDS} "
                f"seconds before next company..."
            )

            print()

            await asyncio.sleep(
                INTER_COMPANY_DELAY_SECONDS
            )

    # =====================================================
    # FINAL OUTPUT
    # =====================================================

    final_payload = {
        "state": state,
        "companies_available": len(companies),
        "companies_researched": len(
            selected_companies
        ),
        "processed": processed,
        "companies": enriched_companies,
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            final_payload,
            file,
            indent=2,
            ensure_ascii=False,
        )

    # =====================================================
    # SUMMARY
    # =====================================================

    enriched_count = sum(
        1
        for item in processed
        if item["status"] == "ENRICHED"
    )

    retained_count = sum(
        1
        for item in processed
        if item["status"] == "RETAINED_ORIGINAL"
    )

    print()
    print("=" * 72)
    print("COMPANY RESEARCH COMPLETE")
    print("=" * 72)

    print()
    print(
        f"Companies researched: "
        f"{len(selected_companies)}"
    )

    print(
        f"Successfully enriched: "
        f"{enriched_count}"
    )

    print(
        f"Original records retained: "
        f"{retained_count}"
    )

    print()

    print(
        f"Saved to: {OUTPUT_FILE}"
    )

    print()


if __name__ == "__main__":

    asyncio.run(
        main()
    )
