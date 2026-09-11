import asyncio
import json
import random
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from agents import Agent, Runner, WebSearchTool
from openai import RateLimitError


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "discovered_sources.json"

DATA_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

MODEL = "gpt-5.6-luna"

MAX_RETRIES = 6

# Automatic wait times after a 429.
# Jitter is added so retries do not always hit at the same moment.
BACKOFF_SECONDS = [
    15,
    30,
    45,
    60,
    90,
    120,
]


# ---------------------------------------------------------
# STRUCTURED OUTPUT
# ---------------------------------------------------------

class HaulerSource(BaseModel):
    jurisdiction: str
    state: str
    source_name: str
    source_url: str
    source_type: str
    authority: str

    icp_relevance: Literal[
        "CORE",
        "ADJACENT",
        "OUT_OF_SCOPE",
    ]

    extractability: Literal[
        "DIRECT_LIST",
        "DATABASE",
        "HUB",
        "REQUIREMENTS_PAGE",
        "UNKNOWN",
    ]

    likely_contains_haulers: bool

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    extractability_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    rationale: str


class SourceDiscoveryResult(BaseModel):
    state: str
    sources: list[HaulerSource]


# ---------------------------------------------------------
# AGENT
# ---------------------------------------------------------

source_agent = Agent(
    name="Waste Hauler Source Discovery Agent",

    model=MODEL,

    instructions="""
You are a research agent building a structured database of authoritative
waste-hauler data sources in the United States.

The user gives you one US state.

Find approximately 8-15 HIGH-VALUE authoritative sources.

Quality matters more than quantity.

Focus on state, county, and municipal sources that could identify actual
private waste-hauling companies.

Do not waste research effort collecting many weak or redundant sources.


=========================================================
ICP RELEVANCE
=========================================================

CORE

Private operators involved in:

- roll-off hauling
- dumpster service
- residential waste collection
- commercial waste collection
- front-load collection
- rear-load collection
- recycling hauling
- mixed solid-waste hauling
- franchised municipal collection
- licensed or permitted solid-waste hauling


ADJACENT

Operators involved in:

- portable toilets
- septic
- liquid waste
- grease hauling
- related field-service businesses with meaningful overlap


OUT_OF_SCOPE

Sources primarily covering:

- hazardous-only operators
- tire-only operators
- landfill-only facilities
- transfer-only facilities
- government sanitation departments
- equipment manufacturers
- brokers with no hauling operation
- generic commercial directories


=========================================================
EXTRACTABILITY
=========================================================

DIRECT_LIST

The source itself visibly lists identifiable private companies.

Examples:

- licensed hauler PDF
- approved hauler list
- franchise hauler list
- permitted transporter list
- government webpage listing operators


DATABASE

An official searchable or downloadable database containing identifiable
company/operator records.

Examples:

- permit registry
- license database
- government dataset
- searchable operator database


HUB

An authoritative landing page or report page that links to other datasets,
reports, PDFs, or databases but does not itself contain the company records.

Example:

A state "Waste Management Database Reports" page containing links to
multiple underlying reports.


REQUIREMENTS_PAGE

An authoritative page explaining permit, licensing, franchise, or
application requirements but not providing an actual operator list.


UNKNOWN

Use only when there is insufficient evidence to confidently classify
extractability.


=========================================================
SOURCE PRIORITY
=========================================================

Prefer:

1. State government databases
2. County licensed-hauler lists
3. County franchise lists
4. Municipal approved-hauler lists
5. Government PDFs containing operators
6. Permit/license databases
7. Official recycling-hauler lists


Avoid:

- generic directories
- Yelp
- Yellow Pages
- lead databases
- SEO articles
- unsupported commercial lists


=========================================================
IMPORTANT DISTINCTION
=========================================================

ICP relevance and extractability are DIFFERENT.

For example:

A state waste-management report hub may be highly relevant to the ICP,
but its extractability should be HUB rather than DIRECT_LIST.

A county licensed-hauler PDF containing company names should usually be:

ICP relevance = CORE
Extractability = DIRECT_LIST


=========================================================
RULES
=========================================================

For every source:

- verify that the source appears legitimate
- identify jurisdiction
- identify authority
- return the real URL
- classify ICP relevance
- classify extractability
- determine whether actual hauler companies are likely present
- assign overall confidence
- assign extractability confidence
- provide a short rationale

Do not invent URLs.

Do not invent sources.

Do not label a landing page DIRECT_LIST just because it links to a list.

Do not label a permit instructions page DIRECT_LIST unless actual operators
are visibly listed.

Return weak or irrelevant authoritative sources only when useful for
demonstrating classification.

Prioritize a compact set of strong sources rather than exhaustive research.

Return structured output only.
""",

    tools=[
        WebSearchTool()
    ],

    output_type=SourceDiscoveryResult,
)


# ---------------------------------------------------------
# RATE-LIMIT-AWARE RUNNER
# ---------------------------------------------------------

async def run_with_retry(state: str):

    prompt = f"""
Research authoritative public sources for private waste-hauling companies.

STATE: {state}

Find approximately 8-15 strong sources across state, county, and municipal
government.

Prioritize sources that can ultimately identify actual private hauling
companies.

Be especially careful to distinguish:

DIRECT_LIST
DATABASE
HUB
REQUIREMENTS_PAGE

Do not perform exhaustive web research. Focus on the best authoritative
sources you can verify.
"""

    for attempt in range(MAX_RETRIES):

        try:

            print(
                f"Agent attempt {attempt + 1}/{MAX_RETRIES}..."
            )

            result = await Runner.run(
                source_agent,
                prompt,
            )

            return result.final_output

        except RateLimitError:

            if attempt == MAX_RETRIES - 1:
                raise

            base_wait = BACKOFF_SECONDS[
                min(attempt, len(BACKOFF_SECONDS) - 1)
            ]

            jitter = random.randint(1, 8)

            wait_time = base_wait + jitter

            print()
            print("OpenAI rate limit reached.")
            print(
                f"Automatically waiting {wait_time} seconds "
                "before retrying..."
            )
            print()

            await asyncio.sleep(wait_time)

        except Exception as exc:

            # Some SDK/API layers may wrap a 429 instead of exposing
            # RateLimitError directly.
            error_text = str(exc).lower()

            if (
                "429" in error_text
                or "rate limit" in error_text
                or "tokens per min" in error_text
            ):

                if attempt == MAX_RETRIES - 1:
                    raise

                base_wait = BACKOFF_SECONDS[
                    min(attempt, len(BACKOFF_SECONDS) - 1)
                ]

                jitter = random.randint(1, 8)

                wait_time = base_wait + jitter

                print()
                print("OpenAI rate limit detected.")
                print(
                    f"Automatically waiting {wait_time} seconds "
                    "before retrying..."
                )
                print()

                await asyncio.sleep(wait_time)

            else:
                raise


# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------

def print_summary(output: SourceDiscoveryResult):

    relevance_counts = {
        "CORE": 0,
        "ADJACENT": 0,
        "OUT_OF_SCOPE": 0,
    }

    extractability_counts = {
        "DIRECT_LIST": 0,
        "DATABASE": 0,
        "HUB": 0,
        "REQUIREMENTS_PAGE": 0,
        "UNKNOWN": 0,
    }

    for source in output.sources:
        relevance_counts[source.icp_relevance] += 1
        extractability_counts[source.extractability] += 1

    print()
    print("=" * 72)
    print("SOURCE DISCOVERY COMPLETE")
    print("=" * 72)

    print(f"\nState: {output.state}")
    print(f"Total sources: {len(output.sources)}")

    print("\nICP RELEVANCE")
    print("-" * 72)
    print(f"CORE:         {relevance_counts['CORE']}")
    print(f"ADJACENT:     {relevance_counts['ADJACENT']}")
    print(f"OUT_OF_SCOPE: {relevance_counts['OUT_OF_SCOPE']}")

    print("\nEXTRACTABILITY")
    print("-" * 72)
    print(
        f"DIRECT_LIST:       "
        f"{extractability_counts['DIRECT_LIST']}"
    )
    print(
        f"DATABASE:          "
        f"{extractability_counts['DATABASE']}"
    )
    print(
        f"HUB:               "
        f"{extractability_counts['HUB']}"
    )
    print(
        f"REQUIREMENTS_PAGE: "
        f"{extractability_counts['REQUIREMENTS_PAGE']}"
    )
    print(
        f"UNKNOWN:           "
        f"{extractability_counts['UNKNOWN']}"
    )

    print()
    print("SOURCES")
    print("=" * 72)

    for i, source in enumerate(output.sources, start=1):

        print()
        print(f"{i}. {source.source_name}")

        print(
            f"   ICP:            "
            f"{source.icp_relevance}"
        )

        print(
            f"   Extractability: "
            f"{source.extractability}"
        )

        print(
            f"   Jurisdiction:   "
            f"{source.jurisdiction}"
        )

        print(
            f"   Authority:      "
            f"{source.authority}"
        )

        print(
            f"   Source type:    "
            f"{source.source_type}"
        )

        print(
            f"   Contains haulers: "
            f"{source.likely_contains_haulers}"
        )

        print(
            f"   Confidence:     "
            f"{source.confidence:.2f}"
        )

        print(
            f"   Extract conf:   "
            f"{source.extractability_confidence:.2f}"
        )

        print(
            f"   URL:            "
            f"{source.source_url}"
        )

        print(
            f"   Why:            "
            f"{source.rationale}"
        )


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

async def main():

    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print("SOURCE DISCOVERY")
    print("=" * 72)

    state = input(
        "\nEnter a US state to research: "
    ).strip()

    if not state:
        raise ValueError(
            "A US state is required."
        )

    print()
    print(
        f"Researching authoritative hauler sources for {state}..."
    )
    print(
        f"Model: {MODEL}"
    )
    print()

    output = await run_with_retry(
        state
    )

    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output.model_dump(),
            file,
            indent=2,
            ensure_ascii=False,
        )

    print_summary(
        output
    )

    print()
    print("=" * 72)
    print(
        f"Saved: {OUTPUT_FILE}"
    )
    print("=" * 72)
    print()


if __name__ == "__main__":
    asyncio.run(main())
