import asyncio
import json
import os
from pathlib import Path
from typing import Literal

from agents import Agent, Runner, WebSearchTool
from pydantic import BaseModel, Field

from config import MODEL, MODE, SETTINGS


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "discovered_sources.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)


SourceType = Literal[
    "DIRECT_LIST",
    "DATABASE",
    "HUB",
    "REQUIREMENTS_PAGE",
    "CONTRACT_RECORDS",
    "UNKNOWN",
]

ICPRelevance = Literal[
    "CORE",
    "ADJACENT",
    "OUT_OF_SCOPE",
]


class SourceRecord(BaseModel):
    source_name: str
    jurisdiction: str
    authority: str
    icp_relevance: ICPRelevance
    source_type: SourceType
    likely_contains_haulers: bool
    confidence: float = Field(ge=0.0, le=1.0)
    extractability_confidence: float = Field(ge=0.0, le=1.0)
    url: str


class SourceDiscoveryResult(BaseModel):
    sources: list[SourceRecord]


def save_output(state, sources):
    payload = {
        "state": state,
        "mode": MODE,
        "model": MODEL,
        "source_target": SETTINGS["source_target"],
        "sources": sources,
    }

    temp_file = OUTPUT_FILE.with_suffix(".json.tmp")
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)

    os.replace(temp_file, OUTPUT_FILE)


def build_prompt(state: str) -> str:
    target = SETTINGS["source_target"]

    return f"""
You are discovering authoritative public sources for a waste-hauler market intelligence pipeline.

TARGET STATE:
{state}

TARGET:
Return up to {target} DISTINCT authoritative public sources that could help identify private waste-service operators in {state}.

The downstream system is looking for private operators involved in:
- roll-off hauling
- dumpster hauling
- residential waste collection
- commercial waste collection
- recycling hauling
- construction debris hauling
- portable toilets / restroom services
- septic / liquid waste where relevant

PRIORITIZE SOURCES THAT DIRECTLY IDENTIFY OPERATORS:
1. approved hauler lists
2. franchise hauler lists
3. permit holder lists
4. regulated transporter databases
5. government searchable registries
6. municipal / county solid-waste provider lists
7. government PDFs or spreadsheets naming operators
8. state regulatory datasets that can be resolved into company records

SEARCH BROADLY WITHIN THE STATE:
- state agencies
- counties
- large cities
- regional authorities
- environmental / solid-waste departments
- public works departments
- franchise / permit programs

SOURCE TYPE DEFINITIONS:

DIRECT_LIST
A page/PDF/spreadsheet that directly names companies/operators.

DATABASE
A searchable database, query interface, downloadable dataset, or structured registry that contains operator/company records.

HUB
A highly relevant government landing page that points to underlying data but is not itself the final extractable company list.

REQUIREMENTS_PAGE
A rules/requirements page that describes licensing or hauling requirements but does not provide a usable company list.

CONTRACT_RECORDS
Procurement, franchise, contract, or award records that may identify operators but are not a clean reusable company dataset.

UNKNOWN
Use only when the source cannot be confidently classified.

ICP RELEVANCE:

CORE
Likely to contain companies that directly operate waste hauling, collection, roll-off, dumpsters, recycling hauling, or closely related solid-waste services.

ADJACENT
Likely to contain portable restroom, septic, sludge, liquid waste, grease, or other adjacent service operators.

OUT_OF_SCOPE
Primarily landfills, transfer facilities, disposal sites, manufacturers, brokers, hazardous-only specialists, tire-only operations, or sources unlikely to identify target operators.

RULES:
- Prefer official government/regulatory sources.
- Return DISTINCT sources. Do not return multiple pages that are essentially the same dataset unless they materially differ.
- Prefer sources with actual operator/company records over generic informational pages.
- Do not invent URLs.
- Do not include private directory sites when a government source is available.
- likely_contains_haulers should be true only when the source plausibly contains identifiable private operators.
- confidence measures confidence that the source is authoritative and relevant.
- extractability_confidence measures confidence that company records can actually be obtained from the source.
- Aim for geographic diversity when useful: state-level plus multiple counties/cities rather than all sources from one jurisdiction.
- It is acceptable to return fewer than {target} sources if additional candidates would be weak, redundant, or non-authoritative.

Return the strongest available set for {state}.
"""


def create_agent():
    return Agent(
        name="Waste Hauler Source Discovery Agent",
        instructions=(
            "Discover authoritative public data sources that can support "
            "waste-hauler market intelligence. Prefer government and regulatory "
            "sources, classify source structure carefully, and never invent URLs."
        ),
        model=MODEL,
        tools=[WebSearchTool()],
        output_type=SourceDiscoveryResult,
    )


async def discover_sources(agent, state):
    return await asyncio.wait_for(
        Runner.run(agent, build_prompt(state)),
        timeout=SETTINGS["discovery_timeout"],
    )


def is_daily_rate_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "requests per day" in text
        or "requests_per_day" in text
        or "rpd" in text
        or ("rate limit" in text and "day" in text)
    )


def dedupe_sources(sources):
    seen = set()
    deduped = []

    for source in sources:
        url_key = source.get("url", "").strip().lower().rstrip("/")
        name_key = source.get("source_name", "").strip().lower()

        key = url_key or name_key
        if not key or key in seen:
            continue

        seen.add(key)
        deduped.append(source)

    return deduped


async def main():
    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print(f"SOURCE DISCOVERY | {MODE.upper()} MODE")
    print("=" * 72)
    print()
    print(f"Model: {MODEL}")
    print(f"Source target: {SETTINGS['source_target']}")
    print()

    state = input("Enter a US state to research: ").strip()

    if not state:
        raise ValueError("A state is required.")

    print()
    print(
        f"Researching authoritative waste-hauler sources in {state}..."
    )

    agent = create_agent()
    discovered = []

    for attempt in range(1, SETTINGS["max_attempts"] + 1):
        print()
        print(f"Attempt {attempt}/{SETTINGS['max_attempts']}")

        try:
            result = await discover_sources(agent, state)

            discovered = [
                source.model_dump()
                for source in result.final_output.sources
            ]

            discovered = dedupe_sources(discovered)
            discovered = discovered[: SETTINGS["source_target"]]

            print("Discovery succeeded.")
            break

        except asyncio.TimeoutError:
            print("Discovery timed out.")

        except Exception as exc:
            message = str(exc)
            print(f"Discovery failed: {message[:300]}")

            if is_daily_rate_limit(exc):
                print()
                print("DAILY MODEL RATE LIMIT REACHED")
                print("No retry will be attempted for a daily model limit.")
                break

        if attempt < SETTINGS["max_attempts"]:
            wait_seconds = SETTINGS["retry_wait"]
            print(f"Retrying in {wait_seconds} seconds...")
            await asyncio.sleep(wait_seconds)

    save_output(state, discovered)

    print()
    print("=" * 72)
    print("SOURCE DISCOVERY COMPLETE")
    print("=" * 72)
    print()
    print(f"State: {state}")
    print(f"Sources discovered: {len(discovered)}")
    print()

    for index, source in enumerate(discovered, start=1):
        print(f"{index}. {source.get('source_name')}")
        print(f"   Jurisdiction: {source.get('jurisdiction')}")
        print(f"   Authority: {source.get('authority')}")
        print(f"   ICP: {source.get('icp_relevance')}")
        print(f"   Extractability: {source.get('source_type')}")
        print(
            f"   Likely contains haulers: "
            f"{source.get('likely_contains_haulers')}"
        )
        print(f"   Confidence: {source.get('confidence', 0):.2f}")
        print(
            f"   Extractability confidence: "
            f"{source.get('extractability_confidence', 0):.2f}"
        )
        print(f"   URL: {source.get('url')}")
        print()

    print(f"Saved: {OUTPUT_FILE.relative_to(BASE_DIR)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
