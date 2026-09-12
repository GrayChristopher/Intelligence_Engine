import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from agents import Agent, Runner, WebSearchTool
from pydantic import BaseModel, Field

from config import MODEL, MODE, SETTINGS


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INPUT_FILE = DATA_DIR / "discovered_companies.json"
OUTPUT_FILE = DATA_DIR / "enriched_companies.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class ResearchResult(BaseModel):
    company_name: str
    location: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    service_lines: list[str] = []
    size_signal: Optional[str] = None
    size_signal_type: Optional[str] = None
    research_confidence: float = Field(ge=0.0, le=1.0)
    evidence: Optional[str] = None


def load_companies():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")
    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_checkpoint(state, companies_available, companies_researched, companies, processed):
    payload = {
        "state": state,
        "mode": MODE,
        "model": MODEL,
        "companies_available": companies_available,
        "companies_researched": companies_researched,
        "companies": companies,
        "processed": processed,
    }
    temp_file = OUTPUT_FILE.with_suffix(".json.tmp")
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)
    os.replace(temp_file, OUTPUT_FILE)


def clean_list(values):
    seen = set()
    result = []
    for value in values or []:
        text = str(value).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def build_prompt(state: str, company: dict) -> str:
    return f"""
You are researching a waste-service company for an ICP intelligence system.

STATE:
{state}

SOURCE-BACKED COMPANY RECORD:

Company:
{company.get('company_name')}

Known location:
{company.get('location')}

Known phone:
{company.get('phone')}

Known website:
{company.get('website')}

Known service lines:
{company.get('service_lines')}

Authoritative source:
{company.get('source_name')}

Source URL:
{company.get('source_url')}

Source evidence:
{company.get('source_evidence')}

Research this specific company using public web sources.

GOALS:
1. Verify or improve the company website.
2. Verify or improve phone/location when possible.
3. Identify defensible service lines.
4. Find ONE useful operational size or scale signal.

Good size signals include:
- number of locations
- service territory
- counties served
- cities served
- markets served
- states served
- fleet size
- truck count
- employee count
- branch count
- major municipal contracts
- years in operation when it helps establish scale
- explicit company statements indicating operational reach

SOURCE PRIORITY:
1. Official company website
2. Government records
3. Regulatory records
4. Other credible first-party or authoritative sources

RULES:
- Do not invent facts.
- Do not guess employee or fleet counts.
- Do not infer size merely from website quality.
- Unknown values should remain null.
- Preserve the exact company identity.
- Do not substitute a similarly named company.
- Do not discard source-backed service lines merely because research finds additional services.
- evidence should briefly explain the strongest factual support found.
- research_confidence should reflect the reliability of the researched record.

Return only information you can reasonably support.
"""


def create_agent():
    return Agent(
        name="Waste Hauler Company Research Agent",
        instructions=(
            "Research private waste-service companies using public web evidence. "
            "Prioritize official and authoritative sources. Never invent missing "
            "company information."
        ),
        model=MODEL,
        tools=[WebSearchTool()],
        output_type=ResearchResult,
    )


async def research_company(agent, state: str, company: dict):
    return await asyncio.wait_for(
        Runner.run(agent, build_prompt(state, company)),
        timeout=SETTINGS["enrichment_timeout"],
    )


def merge_company(original: dict, research: dict):
    """
    Preserve the authoritative discovery record and add research on top of it.
    Discovery provenance is never replaced by research output.
    """
    merged = dict(original)

    merged["company_name"] = original.get("company_name")

    for field in ["location", "phone", "website"]:
        value = research.get(field)
        if value:
            merged[field] = value

    original_services = clean_list(original.get("service_lines", []))
    researched_services = clean_list(research.get("service_lines", []))
    merged["service_lines"] = clean_list(original_services + researched_services)

    merged["size_signal"] = research.get("size_signal")
    merged["size_signal_type"] = research.get("size_signal_type")
    merged["research_confidence"] = float(
        research.get("research_confidence", 0.0) or 0.0
    )
    merged["research_evidence"] = research.get("evidence")

    # Canonical discovery provenance. Keep these exact names throughout
    # downstream validation and scoring.
    merged["source_name"] = original.get("source_name")
    merged["source_url"] = original.get("source_url")
    merged["source_evidence"] = original.get("source_evidence")
    merged["discovery_confidence"] = float(
        original.get("discovery_confidence", 0.0) or 0.0
    )

    return merged


def is_daily_rate_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "requests per day" in text
        or "requests_per_day" in text
        or "rpd" in text
        or ("rate limit" in text and "day" in text)
    )


async def main():
    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print(f"COMPANY RESEARCH | {MODE.upper()} MODE")
    print("=" * 72)

    payload = load_companies()
    state = payload.get("state", "UNKNOWN")
    companies = payload.get("companies", [])
    selected = companies[: SETTINGS["max_enrichment_companies"]]

    print()
    print(f"State: {state}")
    print(f"Companies available: {len(companies)}")
    print(f"Companies selected for research: {len(selected)}")
    print(f"Model: {MODEL}")
    print()

    if not selected:
        print("No companies available for research.")
        return

    agent = create_agent()
    enriched_companies = []
    processed = []
    max_attempts = SETTINGS["max_attempts"]
    daily_limit_hit = False

    for index, company in enumerate(selected, start=1):
        company_name = company.get("company_name", "UNKNOWN")

        print()
        print("-" * 72)
        print(f"COMPANY {index}/{len(selected)}")
        print(company_name)
        print("-" * 72)

        success = False

        for attempt in range(1, max_attempts + 1):
            print()
            print(f"Attempt {attempt}/{max_attempts}")

            try:
                result = await research_company(agent, state, company)
                research = result.final_output.model_dump()
                merged = merge_company(company, research)

                enriched_companies.append(merged)
                processed.append(
                    {
                        "company_name": company_name,
                        "status": "ENRICHED",
                        "research_confidence": research.get(
                            "research_confidence", 0.0
                        ),
                    }
                )

                print("Research completed.")
                print(f"Website: {merged.get('website') or 'UNKNOWN'}")
                print(f"Phone: {merged.get('phone') or 'UNKNOWN'}")
                print(f"Size signal: {merged.get('size_signal') or 'UNKNOWN'}")
                print(
                    f"Confidence: {merged.get('research_confidence', 0):.2f}"
                )
                success = True
                break

            except asyncio.TimeoutError:
                print("Research timed out.")

            except Exception as exc:
                message = str(exc)
                print(f"Research failed: {message[:300]}")
                if is_daily_rate_limit(exc):
                    print()
                    print("DAILY MODEL RATE LIMIT REACHED")
                    print("Completed research has been checkpointed.")
                    print("Remaining companies will retain their source-backed records.")
                    daily_limit_hit = True
                    break

            if attempt < max_attempts:
                wait_seconds = SETTINGS["retry_wait"]
                print(f"Retrying in {wait_seconds} seconds...")
                await asyncio.sleep(wait_seconds)

        if not success:
            fallback = dict(company)
            fallback["size_signal"] = None
            fallback["size_signal_type"] = None
            fallback["research_confidence"] = 0.0
            fallback["research_evidence"] = None

            # Normalize canonical discovery provenance even on fallback.
            fallback["source_name"] = company.get("source_name")
            fallback["source_url"] = company.get("source_url")
            fallback["source_evidence"] = company.get("source_evidence")
            fallback["discovery_confidence"] = float(
                company.get("discovery_confidence", 0.0) or 0.0
            )

            enriched_companies.append(fallback)
            processed.append(
                {
                    "company_name": company_name,
                    "status": "ORIGINAL_RETAINED",
                    "research_confidence": 0.0,
                }
            )

            print()
            print("Research unavailable. Original source-backed record retained.")

        save_checkpoint(
            state=state,
            companies_available=len(companies),
            companies_researched=len(selected),
            companies=enriched_companies,
            processed=processed,
        )

        if daily_limit_hit:
            # Preserve all unprocessed source-backed records so downstream
            # deterministic validation can still operate.
            remaining = selected[index:]
            for remaining_company in remaining:
                fallback = dict(remaining_company)
                fallback["size_signal"] = None
                fallback["size_signal_type"] = None
                fallback["research_confidence"] = 0.0
                fallback["research_evidence"] = None
                fallback["source_name"] = remaining_company.get("source_name")
                fallback["source_url"] = remaining_company.get("source_url")
                fallback["source_evidence"] = remaining_company.get("source_evidence")
                fallback["discovery_confidence"] = float(
                    remaining_company.get("discovery_confidence", 0.0) or 0.0
                )
                enriched_companies.append(fallback)
                processed.append(
                    {
                        "company_name": remaining_company.get(
                            "company_name", "UNKNOWN"
                        ),
                        "status": "ORIGINAL_RETAINED",
                        "research_confidence": 0.0,
                    }
                )

            save_checkpoint(
                state=state,
                companies_available=len(companies),
                companies_researched=len(selected),
                companies=enriched_companies,
                processed=processed,
            )
            break

        if index < len(selected):
            await asyncio.sleep(SETTINGS["inter_company_delay"])

    successful = sum(
        1 for item in processed if item.get("status") == "ENRICHED"
    )
    retained = sum(
        1 for item in processed if item.get("status") == "ORIGINAL_RETAINED"
    )

    print()
    print("=" * 72)
    print("COMPANY RESEARCH COMPLETE")
    print("=" * 72)
    print()
    print(f"Companies available: {len(companies)}")
    print(f"Companies researched/enqueued: {len(selected)}")
    print(f"Successfully enriched: {successful}")
    print(f"Original records retained: {retained}")
    print()

    for index, company in enumerate(enriched_companies, start=1):
        print(f"{index}. {company.get('company_name')}")
        print(f"   Website: {company.get('website') or 'UNKNOWN'}")
        print(f"   Size signal: {company.get('size_signal') or 'UNKNOWN'}")
        print(
            f"   Research confidence: "
            f"{company.get('research_confidence', 0):.2f}"
        )
        print()

    print(f"Saved: {OUTPUT_FILE.relative_to(BASE_DIR)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
