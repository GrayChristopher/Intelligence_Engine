import asyncio
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from agents import Agent, Runner, WebSearchTool


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "discovered_sources.json"

DATA_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------
# STRUCTURED OUTPUT SCHEMA
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
        "OUT_OF_SCOPE"
    ]

    likely_contains_haulers: bool

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that this is a real, authoritative source relevant to hauler discovery."
    )

    rationale: str


class SourceDiscoveryResult(BaseModel):
    state: str
    sources: list[HaulerSource]


# ---------------------------------------------------------
# SOURCE DISCOVERY AGENT
# ---------------------------------------------------------

source_agent = Agent(
    name="Waste Hauler Source Discovery Agent",

    model="gpt-5.6-luna",

    instructions="""
You are a source-discovery research agent supporting an ICP intelligence
system for a waste-hauler software company.

Your job is to discover authoritative public sources that identify
waste-hauling companies in a requested US state.

SEARCH BROADLY, BUT CLASSIFY EACH SOURCE BY ICP RELEVANCE.

---------------------------------------------------------
ICP DEFINITIONS
---------------------------------------------------------

CORE

Sources containing operators involved in one or more of:

- roll-off hauling
- residential waste collection
- commercial waste collection
- front-load operations
- rear-load operations
- dumpster service
- recycling hauling
- mixed waste-hauling operations
- franchised municipal waste collection
- licensed or permitted solid-waste hauling

ADJACENT

Sources containing operators involved in:

- portable toilet service
- septic service
- related liquid-waste operations
- adjacent field-service operators that may overlap with the target market

OUT_OF_SCOPE

Sources that are primarily:

- hazardous-waste-only operators
- waste-tire-only operators
- landfill-only facilities
- transfer-station-only facilities
- government sanitation departments
- equipment manufacturers
- waste brokers with no hauling operation
- generic directories with no authoritative licensing or permit basis

---------------------------------------------------------
SOURCE PRIORITY
---------------------------------------------------------

Prioritize:

1. State government sources
2. County government sources
3. Municipal government sources
4. Government PDFs
5. Government permit/license databases
6. Official franchise or approved-hauler lists

Avoid:

- SEO listicles
- generic business directories
- lead-generation databases
- unsupported company lists
- sources with unclear provenance

---------------------------------------------------------
RULES
---------------------------------------------------------

For every source:

- identify the jurisdiction
- identify the government or regulatory authority
- identify the source type
- provide the source URL
- classify ICP relevance as CORE, ADJACENT, or OUT_OF_SCOPE
- determine whether it likely contains actual hauler records
- provide a confidence score
- explain briefly why it matters

Do not invent sources.

Do not suppress out-of-scope discoveries if they are legitimate authoritative
sources. Return them and classify them correctly.

If the evidence is ambiguous, lower confidence rather than guessing.

Return structured data matching the required output schema.
""",

    tools=[
        WebSearchTool()
    ],

    output_type=SourceDiscoveryResult,
)


# ---------------------------------------------------------
# RUN AGENT
# ---------------------------------------------------------

async def main():

    state = input(
        "\nEnter a US state to research: "
    ).strip()

    if not state:
        raise ValueError("A state is required.")

    print(
        f"\nResearching authoritative waste-hauler sources for {state}...\n"
    )

    result = await Runner.run(
        source_agent,
        f"""
Find authoritative public waste-hauler data sources for:

STATE: {state}

Search broadly across state, county, and municipal government sources.

Return strong sources even if some are ultimately classified
OUT_OF_SCOPE.

The objective is broad source discovery followed by accurate
ICP classification.
"""
    )

    output = result.final_output

    # -----------------------------------------------------
    # SAVE STRUCTURED OUTPUT
    # -----------------------------------------------------

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            output.model_dump(),
            f,
            indent=2,
            ensure_ascii=False
        )

    # -----------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------

    core = [
        s for s in output.sources
        if s.icp_relevance == "CORE"
    ]

    adjacent = [
        s for s in output.sources
        if s.icp_relevance == "ADJACENT"
    ]

    out_of_scope = [
        s for s in output.sources
        if s.icp_relevance == "OUT_OF_SCOPE"
    ]

    print("\nSOURCE DISCOVERY COMPLETE")
    print("=" * 60)

    print(f"\nState: {output.state}")
    print(f"Total sources found: {len(output.sources)}")
    print(f"CORE: {len(core)}")
    print(f"ADJACENT: {len(adjacent)}")
    print(f"OUT_OF_SCOPE: {len(out_of_scope)}")

    print(
        f"\nSaved structured output to:\n{OUTPUT_FILE}\n"
    )

    for i, source in enumerate(
        output.sources,
        start=1
    ):

        print(f"{i}. {source.source_name}")
        print(f"   ICP relevance: {source.icp_relevance}")
        print(f"   Jurisdiction: {source.jurisdiction}")
        print(f"   Authority: {source.authority}")
        print(f"   Type: {source.source_type}")
        print(f"   URL: {source.source_url}")
        print(
            f"   Contains haulers: "
            f"{source.likely_contains_haulers}"
        )
        print(f"   Confidence: {source.confidence:.2f}")
        print(f"   Why: {source.rationale}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
