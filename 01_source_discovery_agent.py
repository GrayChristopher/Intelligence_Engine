import asyncio
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from agents import Agent, Runner, WebSearchTool
from openai import RateLimitError


# =========================================================
# CONFIG
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "discovered_sources.json"

DATA_DIR.mkdir(exist_ok=True)

MODEL = "gpt-5.6-luna"

MAX_ATTEMPTS = 2
ATTEMPT_TIMEOUT_SECONDS = 90
RETRY_WAIT_SECONDS = 10


# =========================================================
# STRUCTURED OUTPUT
# =========================================================

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


# =========================================================
# AGENT
# =========================================================

source_agent = Agent(

    name="Hauler Source Discovery Agent",

    model=MODEL,

    instructions="""
You are the source-discovery layer of a waste-hauler intelligence system.

The user provides one US state.

Your job is NOT to perform exhaustive research.

Find EXACTLY FOUR high-value authoritative public sources that could help
identify private waste-hauling companies in that state.

The purpose is to quickly identify the strongest source types for a
downstream company-extraction pipeline.


=========================================================
SOURCE PRIORITY
=========================================================

Strongly prefer:

1. Government licensed-hauler lists
2. Government approved-hauler lists
3. Government franchise-hauler lists
4. Government permit/license databases
5. Government PDFs directly listing operators
6. State, county, or municipal operator databases

Quality matters much more than geographic completeness.


=========================================================
ICP RELEVANCE
=========================================================

CORE

Private companies involved in:

- roll-off hauling
- dumpster service
- commercial waste collection
- residential waste collection
- front-load collection
- rear-load collection
- recycling hauling
- mixed solid-waste hauling
- franchised municipal collection
- licensed/permitted solid-waste hauling


ADJACENT

Private operators involved in:

- portable toilets
- septic
- liquid waste
- grease hauling
- closely related field-service operations


OUT_OF_SCOPE

Primarily:

- hazardous-only operators
- tire-only operators
- landfill-only facilities
- transfer-only facilities
- government sanitation departments
- equipment manufacturers
- brokers without hauling operations
- generic business directories


=========================================================
EXTRACTABILITY
=========================================================

DIRECT_LIST

The source directly contains identifiable private companies.

Examples:

- licensed hauler list
- approved hauler list
- franchise list
- government PDF listing operators
- government webpage listing operators


DATABASE

An official searchable or downloadable database containing identifiable
company/operator records.

Examples:

- permit database
- license registry
- government operator database


HUB

A government landing/report page that points to other reports, datasets,
PDFs, or databases but does NOT itself provide the actual company list.


REQUIREMENTS_PAGE

A government page describing:

- permit requirements
- licensing rules
- franchise rules
- application procedures

but not actually listing operators.


UNKNOWN

Use only when there is not enough evidence to classify the source.


=========================================================
IMPORTANT
=========================================================

ICP relevance and extractability are separate.

Example:

A state waste-management database landing page can be:

ICP = CORE
Extractability = HUB

A county licensed commercial hauler PDF can be:

ICP = CORE
Extractability = DIRECT_LIST


=========================================================
RULES
=========================================================

Return EXACTLY FOUR sources.

Prioritize sources that are useful for downstream company extraction.

Prefer DIRECT_LIST and DATABASE sources.

At least TWO of the four sources should ideally be DIRECT_LIST or DATABASE.

Do not perform exhaustive statewide research.

Do not spend time collecting redundant sources.

Do not invent sources.

Do not invent URLs.

Do not use Yelp, Yellow Pages, commercial directories, SEO pages,
or lead databases.

If a source is uncertain, lower the confidence rather than inventing facts.

Keep rationale short.

Return structured output only.
""",

    tools=[
        WebSearchTool()
    ],

    output_type=SourceDiscoveryResult,
)


# =========================================================
# RUN AGENT
# =========================================================

async def discover_sources(state: str):

    prompt = f"""
STATE: {state}

Find exactly FOUR strong authoritative public sources for private
waste-hauling company discovery.

This is a FAST discovery pass.

Prioritize sources that can directly feed company extraction:

- licensed hauler lists
- approved hauler lists
- franchise lists
- permit databases
- government PDFs containing operator names

Avoid exhaustive research.

Return exactly four sources.
"""

    for attempt in range(1, MAX_ATTEMPTS + 1):

        print()
        print(
            f"Discovery attempt {attempt}/{MAX_ATTEMPTS}..."
        )

        try:

            result = await asyncio.wait_for(

                Runner.run(
                    source_agent,
                    prompt,
                ),

                timeout=ATTEMPT_TIMEOUT_SECONDS,
            )

            return result.final_output

        except asyncio.TimeoutError:

            print()
            print(
                f"Attempt exceeded "
                f"{ATTEMPT_TIMEOUT_SECONDS} seconds."
            )

            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(
                    "Source discovery timed out."
                )

            print(
                f"Retrying in {RETRY_WAIT_SECONDS} seconds..."
            )

            await asyncio.sleep(
                RETRY_WAIT_SECONDS
            )

        except RateLimitError:

            print()
            print(
                "OpenAI rate limit reached."
            )

            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(
                    "Source discovery was blocked by the API rate limit."
                )

            print(
                f"Retrying in {RETRY_WAIT_SECONDS} seconds..."
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

                print()
                print(
                    "OpenAI rate limit detected."
                )

                if attempt == MAX_ATTEMPTS:
                    raise RuntimeError(
                        "Source discovery was blocked by the API rate limit."
                    )

                print(
                    f"Retrying in {RETRY_WAIT_SECONDS} seconds..."
                )

                await asyncio.sleep(
                    RETRY_WAIT_SECONDS
                )

            else:
                raise


# =========================================================
# SAVE
# =========================================================

def save_output(
    output: SourceDiscoveryResult
):

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


# =========================================================
# DISPLAY
# =========================================================

def print_results(
    output: SourceDiscoveryResult
):

    print()
    print("=" * 72)
    print("SOURCE DISCOVERY COMPLETE")
    print("=" * 72)

    print()
    print(
        f"State: {output.state}"
    )

    print(
        f"Sources discovered: "
        f"{len(output.sources)}"
    )

    print()

    for number, source in enumerate(
        output.sources,
        start=1,
    ):

        print("-" * 72)

        print(
            f"{number}. "
            f"{source.source_name}"
        )

        print(
            f"Jurisdiction:   "
            f"{source.jurisdiction}"
        )

        print(
            f"Authority:      "
            f"{source.authority}"
        )

        print(
            f"ICP:            "
            f"{source.icp_relevance}"
        )

        print(
            f"Extractability: "
            f"{source.extractability}"
        )

        print(
            f"Contains haulers: "
            f"{source.likely_contains_haulers}"
        )

        print(
            f"Confidence:     "
            f"{source.confidence:.2f}"
        )

        print(
            f"Extract conf:   "
            f"{source.extractability_confidence:.2f}"
        )

        print(
            f"URL:            "
            f"{source.source_url}"
        )

        print(
            f"Why:            "
            f"{source.rationale}"
        )

        print()

    print("-" * 72)

    print()
    print(
        f"Saved to: {OUTPUT_FILE}"
    )

    print()


# =========================================================
# MAIN
# =========================================================

async def main():

    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print("FAST SOURCE DISCOVERY")
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
        f"Finding high-value hauler sources "
        f"for {state}..."
    )

    print(
        f"Model: {MODEL}"
    )

    output = await discover_sources(
        state
    )

    save_output(
        output
    )

    print_results(
        output
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )
