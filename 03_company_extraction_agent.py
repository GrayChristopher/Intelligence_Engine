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

INPUT_FILE = DATA_DIR / "extractable_sources.json"
OUTPUT_FILE = DATA_DIR / "discovered_companies.json"

MODEL = "gpt-5.6-luna"

# Keep the live demo fast.
MAX_SOURCES = 2
MAX_COMPANIES_PER_SOURCE = 5

MAX_ATTEMPTS_PER_SOURCE = 2
ATTEMPT_TIMEOUT_SECONDS = 90
RETRY_WAIT_SECONDS = 15

# Small pause between successful source calls.
INTER_SOURCE_DELAY_SECONDS = 5


# =========================================================
# STRUCTURED OUTPUT
# =========================================================

class CompanyRecord(BaseModel):

    company_name: str

    location: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None

    service_lines: list[str] = Field(
        default_factory=list
    )

    source_name: str
    source_url: str

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    evidence: str


class CompanyExtractionResult(BaseModel):

    source_name: str
    source_url: str

    companies: list[CompanyRecord]


# =========================================================
# EXTRACTION AGENT
# =========================================================

company_agent = Agent(

    name="Waste Hauler Company Extraction Agent",

    model=MODEL,

    instructions="""
You are the company-extraction layer of a waste-hauler intelligence system.

You will receive ONE authoritative government source that has already been
classified as suitable for company extraction.

Your job is to identify actual PRIVATE hauling companies supported by that
source.

The source URL should be treated as the primary evidence.


=========================================================
TARGET COMPANIES
=========================================================

Include private operators involved in:

- roll-off hauling
- dumpster service
- commercial waste collection
- residential waste collection
- front-load collection
- rear-load collection
- recycling hauling
- mixed solid-waste hauling
- franchised municipal collection
- permitted or licensed solid-waste hauling


=========================================================
DO NOT INCLUDE
=========================================================

Exclude:

- government sanitation departments
- landfills with no hauling operation
- transfer stations with no hauling operation
- equipment manufacturers
- waste brokers with no hauling operation
- hazardous-waste-only operators
- tire-only operators
- clearly unrelated businesses


=========================================================
DATA RULES
=========================================================

Use the authoritative source as the basis for company identification.

Do not invent companies.

Do not invent phone numbers.

Do not invent websites.

Do not invent service lines.

If a field cannot be reasonably verified, return null or an empty list.

A company can still be returned when phone or website is unknown.

For every company, provide short evidence explaining why the company
belongs in the result.

Evidence should identify what the authoritative source supports.

Do not infer detailed company capabilities unless supported by evidence.

Return no more than the requested maximum number of companies.

If the source cannot be reliably accessed or does not actually contain
company records, return an empty company list rather than guessing.

Return structured output only.
""",

    tools=[
        WebSearchTool()
    ],

    output_type=CompanyExtractionResult,
)


# =========================================================
# NORMALIZATION / DEDUPE
# =========================================================

def normalize_text(value):

    if not value:
        return ""

    value = value.lower().strip()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def company_key(company):

    name = normalize_text(
        company.get("company_name")
    )

    location = normalize_text(
        company.get("location")
    )

    return f"{name}|{location}"


def deduplicate_companies(companies):

    unique = {}
    duplicates = 0

    for company in companies:

        key = company_key(company)

        if not key:
            continue

        if key in unique:

            duplicates += 1

            # Keep whichever record has higher confidence.
            if (
                company.get("confidence", 0)
                > unique[key].get("confidence", 0)
            ):
                unique[key] = company

        else:
            unique[key] = company

    return list(unique.values()), duplicates


# =========================================================
# CHECKPOINT
# =========================================================

def save_checkpoint(
    state,
    companies,
    processed_sources,
):

    payload = {
        "state": state,
        "processed_sources": processed_sources,
        "companies": companies,
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
# EXTRACT ONE SOURCE
# =========================================================

async def extract_source(
    state,
    source,
):

    source_name = source.get(
        "source_name",
        "UNKNOWN",
    )

    source_url = source.get(
        "source_url",
        "",
    )

    jurisdiction = source.get(
        "jurisdiction",
        "UNKNOWN",
    )

    authority = source.get(
        "authority",
        "UNKNOWN",
    )

    prompt = f"""
Extract private waste-hauling companies from this authoritative source.

STATE:
{state}

SOURCE NAME:
{source_name}

SOURCE URL:
{source_url}

JURISDICTION:
{jurisdiction}

AUTHORITY:
{authority}

SOURCE CLASSIFICATION:
{source.get("extractability")}

Return at most {MAX_COMPANIES_PER_SOURCE} companies.

Use the supplied authoritative source as the primary evidence.

Do not guess.

If the source does not actually provide identifiable companies,
return an empty company list.
"""

    for attempt in range(
        1,
        MAX_ATTEMPTS_PER_SOURCE + 1,
    ):

        print()
        print(
            f"   Extraction attempt "
            f"{attempt}/{MAX_ATTEMPTS_PER_SOURCE}..."
        )

        try:

            result = await asyncio.wait_for(

                Runner.run(
                    company_agent,
                    prompt,
                ),

                timeout=ATTEMPT_TIMEOUT_SECONDS,
            )

            return result.final_output

        except asyncio.TimeoutError:

            print(
                "   Attempt timed out."
            )

            if (
                attempt
                == MAX_ATTEMPTS_PER_SOURCE
            ):
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

            if (
                attempt
                == MAX_ATTEMPTS_PER_SOURCE
            ):
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

                if (
                    attempt
                    == MAX_ATTEMPTS_PER_SOURCE
                ):
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
                    f"   Extraction error: {exc}"
                )

                return None

    return None


# =========================================================
# MAIN
# =========================================================

async def main():

    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print("COMPANY EXTRACTION")
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

    sources = payload.get(
        "sources",
        [],
    )

    if not sources:

        print()
        print(
            "No extractable sources were provided."
        )

        return

    selected_sources = sources[
        :MAX_SOURCES
    ]

    print()
    print(
        f"State: {state}"
    )

    print(
        f"Extractable sources available: "
        f"{len(sources)}"
    )

    print(
        f"Sources selected for this run: "
        f"{len(selected_sources)}"
    )

    print(
        f"Maximum companies per source: "
        f"{MAX_COMPANIES_PER_SOURCE}"
    )

    all_companies = []

    processed_sources = []

    # =====================================================
    # PROCESS SOURCES SEQUENTIALLY
    # =====================================================

    for index, source in enumerate(
        selected_sources,
        start=1,
    ):

        print()
        print("=" * 72)

        print(
            f"SOURCE {index}/"
            f"{len(selected_sources)}"
        )

        print(
            source.get(
                "source_name",
                "UNKNOWN",
            )
        )

        print(
            source.get(
                "source_url",
                "",
            )
        )

        print("=" * 72)

        result = await extract_source(
            state,
            source,
        )

        processed_record = {
            "source_name": source.get(
                "source_name"
            ),
            "source_url": source.get(
                "source_url"
            ),
        }

        if result is None:

            print()
            print(
                "   Source extraction failed "
                "or timed out."
            )

            processed_record[
                "status"
            ] = "FAILED"

            processed_record[
                "companies_found"
            ] = 0

            processed_sources.append(
                processed_record
            )

            save_checkpoint(
                state,
                all_companies,
                processed_sources,
            )

            continue

        companies = [
            company.model_dump()
            for company
            in result.companies
        ]

        print()
        print(
            f"   Companies found: "
            f"{len(companies)}"
        )

        for company in companies:

            all_companies.append(
                company
            )

            print(
                f"   + "
                f"{company['company_name']}"
            )

        processed_record[
            "status"
        ] = "SUCCESS"

        processed_record[
            "companies_found"
        ] = len(companies)

        processed_sources.append(
            processed_record
        )

        # Save after every successful source.
        save_checkpoint(
            state,
            all_companies,
            processed_sources,
        )

        # Small breathing room between API calls.
        if (
            index
            < len(selected_sources)
        ):

            print()
            print(
                f"Waiting "
                f"{INTER_SOURCE_DELAY_SECONDS} "
                f"seconds before next source..."
            )

            await asyncio.sleep(
                INTER_SOURCE_DELAY_SECONDS
            )

    # =====================================================
    # DEDUPE
    # =====================================================

    before_dedupe = len(
        all_companies
    )

    unique_companies, duplicates = (
        deduplicate_companies(
            all_companies
        )
    )

    after_dedupe = len(
        unique_companies
    )

    # =====================================================
    # FINAL SAVE
    # =====================================================

    final_payload = {
        "state": state,
        "processed_sources": processed_sources,
        "companies_before_dedup": before_dedupe,
        "duplicates_removed": duplicates,
        "companies_after_dedup": after_dedupe,
        "companies": unique_companies,
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

    print()
    print("=" * 72)
    print("COMPANY EXTRACTION COMPLETE")
    print("=" * 72)

    print()
    print(
        f"State: {state}"
    )

    print(
        f"Sources processed: "
        f"{len(processed_sources)}"
    )

    print(
        f"Companies before dedupe: "
        f"{before_dedupe}"
    )

    print(
        f"Duplicates removed: "
        f"{duplicates}"
    )

    print(
        f"Companies after dedupe: "
        f"{after_dedupe}"
    )

    print()

    for number, company in enumerate(
        unique_companies,
        start=1,
    ):

        print(
            f"{number}. "
            f"{company['company_name']}"
        )

        print(
            f"   Location: "
            f"{company.get('location') or 'UNKNOWN'}"
        )

        print(
            f"   Phone: "
            f"{company.get('phone') or 'UNKNOWN'}"
        )

        print(
            f"   Website: "
            f"{company.get('website') or 'UNKNOWN'}"
        )

        print(
            f"   Services: "
            f"{', '.join(company.get('service_lines', [])) or 'UNKNOWN'}"
        )

        print(
            f"   Confidence: "
            f"{company.get('confidence', 0):.2f}"
        )

        print(
            f"   Source: "
            f"{company.get('source_name')}"
        )

        print(
            f"   Evidence: "
            f"{company.get('evidence')}"
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
