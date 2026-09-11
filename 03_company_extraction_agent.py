import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from agents import Agent, Runner, WebSearchTool
from pydantic import BaseModel, Field

from config import MODEL, MODE, SETTINGS


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "extractable_sources.json"
OUTPUT_FILE = DATA_DIR / "discovered_companies.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# STRUCTURED OUTPUT
# =========================================================

class CompanyRecord(BaseModel):
    company_name: str

    location: Optional[str] = None

    phone: Optional[str] = None

    website: Optional[str] = None

    service_lines: list[str] = []

    source_name: str

    source_url: str

    source_evidence: str

    discovery_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )


class ExtractionResult(BaseModel):
    companies: list[CompanyRecord]


# =========================================================
# HELPERS
# =========================================================

def load_sources():

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

    return payload


def normalize_name(name: str) -> str:

    return "".join(
        character.lower()
        for character in name
        if character.isalnum()
    )


def normalize_location(location: Optional[str]) -> str:

    if not location:
        return ""

    return "".join(
        character.lower()
        for character in location
        if character.isalnum()
    )


def deduplicate(companies):

    seen = set()
    cleaned = []

    for company in companies:

        key = (
            normalize_name(
                company.get(
                    "company_name",
                    "",
                )
            ),
            normalize_location(
                company.get("location")
            ),
        )

        if not key[0]:
            continue

        if key in seen:
            continue

        seen.add(key)
        cleaned.append(company)

    return cleaned


# =========================================================
# PROMPT
# =========================================================

def build_prompt(
    state: str,
    source: dict,
) -> str:

    max_companies = SETTINGS[
        "max_companies_per_source"
    ]

    return f"""
You are a company-extraction agent for a waste-hauler
market intelligence system.

STATE:
{state}

AUTHORITATIVE SOURCE:
Name: {source.get('source_name')}
Authority: {source.get('authority')}
Jurisdiction: {source.get('jurisdiction')}
URL: {source.get('source_url')}
Description: {source.get('description')}

Your job is to identify up to {max_companies} REAL PRIVATE
waste-service companies that are supported by this source.

TARGET COMPANIES:

CORE:
- roll-off hauling
- dumpster hauling
- residential waste collection
- commercial waste collection
- front-load or rear-load hauling
- recycling hauling
- construction debris hauling

ADJACENT:
- portable toilet operators
- septic operators
- liquid waste operators
- restroom trailer operators

EXCLUDE:

- government sanitation departments
- municipalities operating their own collection
- landfill-only operators
- transfer-station-only operators
- equipment manufacturers
- dumpster brokers with no hauling operation
- hazardous-waste-only operators
- tire-only recyclers
- companies that cannot be tied to the source

RULES:

1. Every company must be supported by the authoritative
   source or by clearly related source-backed evidence.

2. Do not invent companies.

3. Do not invent phones, websites, locations, or services.

4. Unknown fields should remain null or empty.

5. source_evidence should briefly explain exactly why the
   company belongs in the dataset.

6. discovery_confidence represents confidence that this
   company is a legitimate private waste-service operator
   supported by the source.

7. Prefer quality over quantity.

Return no more than {max_companies} companies.
"""


# =========================================================
# AGENT
# =========================================================

def create_agent():

    return Agent(
        name="Waste Hauler Company Extraction Agent",

        instructions=(
            "Extract real private waste-service companies "
            "from authoritative public sources. "
            "Be conservative and evidence-driven. "
            "Do not invent company information."
        ),

        model=MODEL,

        tools=[
            WebSearchTool(),
        ],

        output_type=ExtractionResult,
    )


# =========================================================
# RUN ONE SOURCE
# =========================================================

async def process_source(
    agent,
    state: str,
    source: dict,
):

    prompt = build_prompt(
        state,
        source,
    )

    return await asyncio.wait_for(
        Runner.run(
            agent,
            prompt,
        ),
        timeout=SETTINGS[
            "extraction_timeout"
        ],
    )


# =========================================================
# CHECKPOINT
# =========================================================

def save_checkpoint(
    state: str,
    companies: list,
    processed_sources: list,
):

    payload = {
        "state": state,
        "mode": MODE,
        "model": MODEL,
        "processed_sources": processed_sources,
        "companies": deduplicate(companies),
    }

    temp_file = OUTPUT_FILE.with_suffix(
        ".json.tmp"
    )

    with open(
        temp_file,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
        )

    os.replace(
        temp_file,
        OUTPUT_FILE,
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print(
        f"COMPANY EXTRACTION | {MODE.upper()} MODE"
    )
    print("=" * 72)

    payload = load_sources()

    state = payload.get(
        "state",
        "UNKNOWN",
    )

    sources = payload.get(
        "sources",
        [],
    )

    max_sources = SETTINGS[
        "max_extraction_sources"
    ]

    selected_sources = sources[
        :max_sources
    ]

    print()
    print(f"State: {state}")
    print(
        f"Extractable sources available: "
        f"{len(sources)}"
    )
    print(
        f"Sources selected: "
        f"{len(selected_sources)}"
    )
    print(
        f"Max companies/source: "
        f"{SETTINGS['max_companies_per_source']}"
    )
    print()

    if not selected_sources:

        print(
            "No extractable sources available."
        )

        return

    agent = create_agent()

    all_companies = []
    processed_sources = []

    max_attempts = SETTINGS[
        "max_attempts"
    ]

    for index, source in enumerate(
        selected_sources,
        start=1,
    ):

        source_name = source.get(
            "source_name",
            "UNKNOWN SOURCE",
        )

        print()
        print("-" * 72)
        print(
            f"SOURCE {index}/"
            f"{len(selected_sources)}"
        )
        print(source_name)
        print("-" * 72)

        source_success = False

        for attempt in range(
            1,
            max_attempts + 1,
        ):

            print()
            print(
                f"Attempt "
                f"{attempt}/{max_attempts}"
            )

            try:

                result = await process_source(
                    agent,
                    state,
                    source,
                )

                extraction = (
                    result.final_output
                )

                companies = (
                    extraction.model_dump()
                    .get(
                        "companies",
                        [],
                    )
                )

                all_companies.extend(
                    companies
                )

                processed_sources.append(
                    {
                        "source_name": source_name,
                        "source_url": source.get(
                            "source_url"
                        ),
                        "status": "SUCCESS",
                        "companies_found": len(
                            companies
                        ),
                    }
                )

                print(
                    f"Companies found: "
                    f"{len(companies)}"
                )

                for company in companies:

                    print(
                        f"  - "
                        f"{company['company_name']}"
                    )

                source_success = True

                break

            except asyncio.TimeoutError:

                print(
                    "Extraction timed out."
                )

            except Exception as exc:

                print(
                    "Extraction failed: "
                    f"{str(exc)[:300]}"
                )

            if attempt < max_attempts:

                wait_seconds = SETTINGS[
                    "retry_wait"
                ]

                print(
                    f"Retrying in "
                    f"{wait_seconds} seconds..."
                )

                await asyncio.sleep(
                    wait_seconds
                )

        if not source_success:

            processed_sources.append(
                {
                    "source_name": source_name,
                    "source_url": source.get(
                        "source_url"
                    ),
                    "status": "FAILED",
                    "companies_found": 0,
                }
            )

            print(
                "Source failed after "
                "all attempts."
            )

        save_checkpoint(
            state,
            all_companies,
            processed_sources,
        )

        if index < len(
            selected_sources
        ):

            await asyncio.sleep(
                SETTINGS[
                    "inter_source_delay"
                ]
            )

    before_dedupe = len(
        all_companies
    )

    final_companies = deduplicate(
        all_companies
    )

    duplicates_removed = (
        before_dedupe
        - len(final_companies)
    )

    save_checkpoint(
        state,
        final_companies,
        processed_sources,
    )

    print()
    print("=" * 72)
    print("COMPANY EXTRACTION COMPLETE")
    print("=" * 72)

    print()
    print(
        f"Companies before dedupe: "
        f"{before_dedupe}"
    )

    print(
        f"Duplicates removed: "
        f"{duplicates_removed}"
    )

    print(
        f"Companies after dedupe: "
        f"{len(final_companies)}"
    )

    print()

    for index, company in enumerate(
        final_companies,
        start=1,
    ):

        print(
            f"{index}. "
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
            f"   Confidence: "
            f"{company.get('discovery_confidence', 0):.2f}"
        )

        print()

    print(
        f"Saved: "
        f"{OUTPUT_FILE.relative_to(BASE_DIR)}"
    )

    print()


if __name__ == "__main__":
    asyncio.run(main())
