import asyncio
from pydantic import BaseModel, Field
from agents import Agent, Runner, WebSearchTool


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

    likely_contains_haulers: bool

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that this is an authoritative source containing waste hauler records."
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

    instructions="""
You are a research agent responsible for discovering authoritative
public sources containing waste-hauler company information.

The user will provide a US state.

Search the web for sources that identify companies that are:

- licensed waste haulers
- permitted waste haulers
- approved waste haulers
- franchised waste haulers
- commercial solid-waste haulers
- roll-off haulers
- residential waste haulers
- commercial waste haulers
- recycling haulers

PRIORITIZE:

1. State government sources
2. County government sources
3. Municipal government sources
4. Government PDFs
5. Government permit/license databases

AVOID:

- generic business directories
- SEO listicles
- lead-generation websites
- unsupported company lists
- sources with unclear provenance

For every source:

- identify the jurisdiction
- identify the authority
- identify the type of source
- provide the source URL
- determine whether it likely contains actual hauler records
- provide a confidence score
- briefly explain why the source is useful

Do not invent sources.

If evidence is insufficient, lower the confidence score.

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

    print(f"\nResearching authoritative waste-hauler sources for {state}...\n")

    result = await Runner.run(
        source_agent,
        f"""
Find authoritative public waste-hauler data sources for:

STATE: {state}

Search broadly across state, county, and municipal government sources.

Return the strongest sources you can verify.
"""
    )

    output = result.final_output

    print("\nSOURCE DISCOVERY COMPLETE")
    print("=" * 60)

    print(f"\nState: {output.state}")
    print(f"Sources found: {len(output.sources)}\n")

    for i, source in enumerate(output.sources, start=1):

        print(f"{i}. {source.source_name}")
        print(f"   Jurisdiction: {source.jurisdiction}")
        print(f"   Authority: {source.authority}")
        print(f"   Type: {source.source_type}")
        print(f"   URL: {source.source_url}")
        print(f"   Contains haulers: {source.likely_contains_haulers}")
        print(f"   Confidence: {source.confidence:.2f}")
        print(f"   Why: {source.rationale}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
