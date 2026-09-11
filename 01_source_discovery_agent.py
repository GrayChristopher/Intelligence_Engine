import asyncio
import json
import os
from pathlib import Path
from typing import Literal

from agents import Agent, Runner, WebSearchTool
from pydantic import BaseModel, Field

from config import MODEL, MODE, SETTINGS


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "discovered_sources.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# STRUCTURED OUTPUT
# =========================================================

class SourceRecord(BaseModel):
    source_name: str

    jurisdiction: str

    authority: str

    source_url: str

    description: str

    icp_relevance: Literal[
        "CORE",
        "ADJACENT",
        "OUT_OF_SCOPE",
    ]

    source_type: Literal[
        "DIRECT_LIST",
        "DATABASE",
        "HUB",
        "REQUIREMENTS_PAGE",
        "CONTRACT_RECORDS",
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

    reasoning: str


class DiscoveryResult(BaseModel):
    state: str

    sources: list[SourceRecord]


# =========================================================
# PROMPT
# =========================================================

def build_prompt(state: str) -> str:

    source_target = SETTINGS["source_target"]

    return f"""
You are a source-discovery agent for a waste-hauler
market intelligence system.

Research authoritative public sources for:

STATE: {state}

Find approximately {source_target} high-value sources
that could help identify real private waste-hauling
companies operating in this state.

PRIMARY ICP:

- roll-off dumpster hauling
- residential waste collection
- commercial waste collection
- front-load / rear-load hauling
- recycling hauling
- construction debris hauling

ADJACENT ICP:

- portable toilet operators
- septic operators
- liquid waste operators
- restroom trailer operators

PRIORITIZE AUTHORITATIVE SOURCES:

1. State regulatory agencies
2. County or municipal government
3. Franchise / permit holder lists
4. Licensed hauler lists
5. Approved vendor or contractor lists
6. Public databases
7. Government PDFs or reports

AVOID:

- generic directories
- Yelp
- Angi
- lead-generation sites
- SEO listicles
- business aggregators when authoritative sources exist

For each source classify ICP relevance:

CORE
Source directly relates to private waste/recycling/
roll-off hauling.

ADJACENT
Relevant adjacent waste-service operators.

OUT_OF_SCOPE
Not useful for the ICP.

Also classify extractability:

DIRECT_LIST
The source directly contains company/operator records.

DATABASE
A searchable public database likely containing
company/operator records.

HUB
An index, portal, or landing page that points to other
records but does not itself directly list haulers.

REQUIREMENTS_PAGE
A regulations/instructions page without a usable list.

CONTRACT_RECORDS
Government contracting records that may contain
operators but require additional interpretation.

UNKNOWN
Structure cannot be confidently determined.

Set likely_contains_haulers=true only when there is good
reason to believe the source actually contains identifiable
private operators.

Do not invent sources or URLs.

Return the strongest sources you can verify.
"""


# =========================================================
# AGENT
# =========================================================

def create_agent():

    return Agent(
        name="Waste Hauler Source Discovery Agent",

        instructions=(
            "Research authoritative public sources for "
            "private waste hauling companies. "
            "Prefer government and regulatory evidence. "
            "Be conservative. Do not invent URLs or "
            "source characteristics."
        ),

        model=MODEL,

        tools=[
            WebSearchTool(),
        ],

        output_type=DiscoveryResult,
    )


# =========================================================
# RUN WITH TIMEOUT
# =========================================================

async def run_attempt(
    agent,
    state: str,
):

    prompt = build_prompt(state)

    return await asyncio.wait_for(
        Runner.run(
            agent,
            prompt,
        ),
        timeout=SETTINGS["source_timeout"],
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print(
        f"SOURCE DISCOVERY | {MODE.upper()} MODE"
    )
    print("=" * 72)

    print()
    print(f"Model: {MODEL}")
    print(
        f"Source target: "
        f"{SETTINGS['source_target']}"
    )
    print()

    state = input(
        "Enter a US state to research: "
    ).strip()

    if not state:
        print("ERROR: State cannot be blank.")
        return

    print()
    print(
        f"Researching authoritative "
        f"waste-hauler sources in {state}..."
    )

    agent = create_agent()

    max_attempts = SETTINGS["max_attempts"]

    final_result = None

    for attempt in range(
        1,
        max_attempts + 1,
    ):

        print()
        print(
            f"Attempt {attempt}/{max_attempts}"
        )

        try:

            result = await run_attempt(
                agent,
                state,
            )

            final_result = result.final_output

            print("Discovery succeeded.")

            break

        except asyncio.TimeoutError:

            print(
                "Request timed out."
            )

        except Exception as exc:

            message = str(exc)

            print(
                f"Discovery attempt failed: "
                f"{message[:300]}"
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

    if final_result is None:

        print()
        print(
            "ERROR: Source discovery failed "
            "after all attempts."
        )

        print(
            "Existing output was not overwritten."
        )

        return

    payload = final_result.model_dump()

    payload["state"] = state

    payload["mode"] = MODE

    payload["model"] = MODEL

    payload["source_target"] = SETTINGS[
        "source_target"
    ]

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

    sources = payload.get(
        "sources",
        [],
    )

    print()
    print("=" * 72)
    print("SOURCE DISCOVERY COMPLETE")
    print("=" * 72)

    print()
    print(f"State: {state}")
    print(
        f"Sources discovered: "
        f"{len(sources)}"
    )

    print()

    for index, source in enumerate(
        sources,
        start=1,
    ):

        print(
            f"{index}. "
            f"{source['source_name']}"
        )

        print(
            f"   Jurisdiction: "
            f"{source['jurisdiction']}"
        )

        print(
            f"   Authority: "
            f"{source['authority']}"
        )

        print(
            f"   ICP: "
            f"{source['icp_relevance']}"
        )

        print(
            f"   Extractability: "
            f"{source['source_type']}"
        )

        print(
            f"   Likely contains haulers: "
            f"{source['likely_contains_haulers']}"
        )

        print(
            f"   Confidence: "
            f"{source['confidence']:.2f}"
        )

        print(
            f"   Extractability confidence: "
            f"{source['extractability_confidence']:.2f}"
        )

        print(
            f"   URL: "
            f"{source['source_url']}"
        )

        print()

    print(
        f"Saved: "
        f"{OUTPUT_FILE.relative_to(BASE_DIR)}"
    )

    print()


if __name__ == "__main__":
    asyncio.run(main())
