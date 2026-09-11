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

    extractability: Literal[
        "DIRECT_LIST",
        "DATABASE",
        "HUB",
        "REQUIREMENTS_PAGE",
        "UNKNOWN"
    ]

    likely_contains_haulers: bool

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confidence that this is a real authoritative source "
            "and that the source classification is correct."
        )
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
You are a source-discovery research agent supporting a waste-hauler
intelligence system.

The user will provide a US state.

Your job is to discover authoritative public sources that can identify
waste-hauling companies in that state.

You must evaluate TWO separate dimensions for every source:

1. ICP relevance
2. Extractability

---------------------------------------------------------
ICP RELEVANCE
---------------------------------------------------------

CORE

Sources containing private operators involved in one or more of:

- roll-off hauling
- dumpster service
- residential waste collection
- commercial waste collection
- front-load operations
- rear-load operations
- recycling hauling
- mixed solid-waste hauling
- franchised municipal waste collection
- licensed or permitted private solid-waste hauling

ADJACENT

Sources containing operators involved in:

- portable toilet service
- septic service
- liquid waste hauling
- grease hauling
- related field-service operations that may overlap with the ICP

OUT_OF_SCOPE

Sources primarily containing:

- hazardous-waste-only operators
- waste-tire-only operators
- landfill-only facilities
- transfer-station-only facilities
- government sanitation departments
- equipment manufacturers
- waste brokers with no hauling operation
- generic business directories with no authoritative permit/license basis


---------------------------------------------------------
EXTRACTABILITY
---------------------------------------------------------

DIRECT_LIST

Use when the source directly presents identifiable companies, such as:

- approved hauler list
- licensed hauler list
- permitted hauler list
- franchise hauler list
- government PDF containing company names
- government webpage containing company names

This is the strongest source type for downstream company extraction.


DATABASE

Use when the source is a searchable or downloadable government database
that contains identifiable operator/company records.

Examples:

- permit database
- license database
- registry
- downloadable government dataset


HUB

Use when the source is mainly a landing page or report hub that points to
other reports, databases, PDFs, or datasets, but does not itself directly
contain the company records needed downstream.

Example:

- "Waste Management Database Reports" page linking to multiple datasets


REQUIREMENTS_PAGE

Use when the source explains:

- permit requirements
- franchise requirements
- licensing procedures
- application processes

but does not appear to contain an actual list of companies.


UNKNOWN

Use only when the source is authoritative but there is not enough evidence
to confidently determine its extractability.


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
- classify ICP relevance
- classify extractability
- determine whether it likely contains actual hauler records
- provide a confidence score
- explain briefly why the source matters

Do not invent sources.

Do not suppress legitimate authoritative sources merely because they are
out of scope. Return them and classify them correctly.

Do not classify a generic landing page as DIRECT_LIST merely because it
links to company data elsewhere.

Do not classify a requirements page as DIRECT_LIST unless actual company
records are visible on that source.

If evidence is ambiguous, use UNKNOWN or lower confidence rather than
guessing.

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

The goal is to discover strong source candidates and correctly distinguish:

- ICP relevance
- whether the source directly supports downstream company extraction

Return legitimate sources even when they are ultimately classified
ADJACENT, OUT_OF_SCOPE, HUB, REQUIREMENTS_PAGE, or UNKNOWN.
"""
    )

    output = result.final_output

    # -----------------------------------------------------
    # SAVE STRUCTURED OUTPUT
    # -----------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output.model_dump(),
            f,
            indent=2,
            ensure_ascii=False
        )

    # -----------------------------------------------------
    # SUMMARY COUNTS
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # PRINT SUMMARY
    # -----------------------------------------------------

    print("\nSOURCE DISCOVERY COMPLETE")
    print("=" * 70)

    print(f"\nState: {output.state}")
    print(f"Total sources found: {len(output.sources)}")

    print("\nICP RELEVANCE")
    print("-" * 70)
    print(f"CORE:         {relevance_counts['CORE']}")
    print(f"ADJACENT:     {relevance_counts['ADJACENT']}")
    print(f"OUT_OF_SCOPE: {relevance_counts['OUT_OF_SCOPE']}")

    print("\nEXTRACTABILITY")
    print("-" * 70)
    print(f"DIRECT_LIST:       {extractability_counts['DIRECT_LIST']}")
    print(f"DATABASE:          {extractability_counts['DATABASE']}")
    print(f"HUB:               {extractability_counts['HUB']}")
    print(f"REQUIREMENTS_PAGE: {extractability_counts['REQUIREMENTS_PAGE']}")
    print(f"UNKNOWN:           {extractability_counts['UNKNOWN']}")

    print(
        f"\nSaved structured output to:\n{OUTPUT_FILE}\n"
    )

    # -----------------------------------------------------
    # PRINT SOURCES
    # -----------------------------------------------------

    for i, source in enumerate(
        output.sources,
        start=1
    ):

        print(f"{i}. {source.source_name}")
        print(f"   ICP relevance:  {source.icp_relevance}")
        print(f"   Extractability: {source.extractability}")
        print(f"   Jurisdiction:   {source.jurisdiction}")
        print(f"   Authority:      {source.authority}")
        print(f"   Type:           {source.source_type}")
        print(f"   URL:            {source.source_url}")
        print(
            f"   Contains haulers: "
            f"{source.likely_contains_haulers}"
        )
        print(f"   Confidence:     {source.confidence:.2f}")
        print(f"   Why:            {source.rationale}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
