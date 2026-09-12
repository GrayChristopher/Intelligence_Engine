import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional

from agents import Agent, Runner, WebSearchTool
from pydantic import BaseModel, Field

from config import MODEL, MODE, SETTINGS


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INPUT_FILE = DATA_DIR / "extractable_sources.json"
OUTPUT_FILE = DATA_DIR / "discovered_companies.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class CompanyRecord(BaseModel):
    company_name: str
    location: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    service_lines: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str


class CompanyExtractionResult(BaseModel):
    companies: list[CompanyRecord]


def load_sources():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, list):
        return "UNKNOWN", payload

    if isinstance(payload, dict):
        state = payload.get("state", "UNKNOWN")
        for key in ("sources", "items", "records"):
            if isinstance(payload.get(key), list):
                return state, payload[key]

        # Some router versions may store the routed list under "extractable".
        if isinstance(payload.get("extractable"), list):
            return state, payload["extractable"]

    return "UNKNOWN", []


def save_checkpoint(state, companies, processed_sources):
    payload = {
        "state": state,
        "mode": MODE,
        "model": MODEL,
        "companies": companies,
        "processed_sources": processed_sources,
    }

    temp_file = OUTPUT_FILE.with_suffix(".json.tmp")
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)

    os.replace(temp_file, OUTPUT_FILE)


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_company_key(company):
    name = re.sub(
        r"[^a-z0-9]+",
        "",
        normalize_text(company.get("company_name")).lower(),
    )
    location = re.sub(
        r"[^a-z0-9]+",
        "",
        normalize_text(company.get("location")).lower(),
    )
    return name, location


def dedupe_companies(companies):
    seen = set()
    deduped = []

    for company in companies:
        name_key, location_key = normalize_company_key(company)

        if not name_key:
            continue

        # Prefer company + location when location exists.
        # Fall back to company name when location is unavailable.
        key = (name_key, location_key) if location_key else (name_key,)

        if key in seen:
            continue

        seen.add(key)
        deduped.append(company)

    return deduped


def source_value(source, *keys):
    for key in keys:
        value = source.get(key)
        if value not in (None, "", "UNKNOWN"):
            return value
    return None


def build_prompt(state: str, source: dict) -> str:
    source_name = source_value(source, "source_name", "name") or "UNKNOWN"
    source_url = source_value(source, "url", "source_url") or "UNKNOWN"
    authority = source_value(source, "authority") or "UNKNOWN"
    jurisdiction = source_value(source, "jurisdiction") or state

    return f"""
You are extracting private waste-service companies from an authoritative public source.

TARGET STATE:
{state}

SOURCE:
Name: {source_name}
Authority: {authority}
Jurisdiction: {jurisdiction}
URL: {source_url}

GOAL:
Find up to {SETTINGS['max_companies_per_source']} real private companies represented by this source that are relevant to waste-hauler market intelligence.

PRIORITIZE:
- roll-off haulers
- dumpster haulers
- residential waste collection
- commercial waste collection
- recycling haulers
- construction debris hauling
- portable toilet / restroom operators
- septic / liquid-waste operators when clearly source-backed

EXCLUDE:
- government sanitation departments
- landfill-only operators
- transfer-station-only operators
- equipment manufacturers
- brokers with no hauling operation
- hazardous-only specialists
- tire-only operators
- records that cannot be tied to a specific company

RULES:
- Use this source as the grounding source.
- Do not invent companies.
- Do not invent contact information.
- Keep unknown fields null.
- service_lines should contain only services supported by evidence.
- evidence must briefly explain why the company belongs in the extracted set.
- confidence reflects confidence in the extracted company record.
- Do not return duplicate companies.
- Return private operating companies, not government agencies.

Return as many defensible companies as the source supports, up to the requested maximum.
"""


def create_agent():
    return Agent(
        name="Waste Hauler Company Extraction Agent",
        instructions=(
            "Extract private waste-service operators from authoritative public "
            "sources. Preserve factual grounding and never invent missing data."
        ),
        model=MODEL,
        tools=[WebSearchTool()],
        output_type=CompanyExtractionResult,
    )


async def extract_from_source(agent, state, source):
    return await asyncio.wait_for(
        Runner.run(agent, build_prompt(state, source)),
        timeout=SETTINGS["extraction_timeout"],
    )


def is_daily_rate_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "requests per day" in text
        or "requests_per_day" in text
        or "rpd" in text
        or ("rate limit" in text and "day" in text)
    )


def attach_provenance(company: dict, source: dict):
    """
    Canonical discovery schema used by stages 04-06.
    """
    record = dict(company)

    record["source_name"] = source_value(
        source,
        "source_name",
        "name",
    )
    record["source_url"] = source_value(
        source,
        "url",
        "source_url",
    )

    # The company-level extraction evidence is the discovery evidence.
    record["source_evidence"] = company.get("evidence")
    record["discovery_confidence"] = float(
        company.get("confidence", 0.0) or 0.0
    )

    # Remove ambiguous aliases after canonicalization.
    record.pop("evidence", None)
    record.pop("confidence", None)

    return record


async def main():
    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print(f"COMPANY EXTRACTION | {MODE.upper()} MODE")
    print("=" * 72)

    state, sources = load_sources()

    selected_sources = sources[: SETTINGS["max_extraction_sources"]]

    print()
    print(f"State: {state}")
    print(f"Extractable sources available: {len(sources)}")
    print(f"Sources selected: {len(selected_sources)}")
    print(
        f"Max companies/source: "
        f"{SETTINGS['max_companies_per_source']}"
    )
    print()

    if not selected_sources:
        save_checkpoint(state, [], [])
        print("No extractable sources available.")
        print(f"Saved: {OUTPUT_FILE.relative_to(BASE_DIR)}")
        return

    agent = create_agent()
    all_companies = []
    processed_sources = []
    daily_limit_hit = False

    for index, source in enumerate(selected_sources, start=1):
        source_name = source_value(
            source,
            "source_name",
            "name",
        ) or "UNKNOWN"

        print()
        print("-" * 72)
        print(f"SOURCE {index}/{len(selected_sources)}")
        print(source_name)
        print("-" * 72)

        source_success = False
        extracted_count = 0

        for attempt in range(1, SETTINGS["max_attempts"] + 1):
            print()
            print(f"Attempt {attempt}/{SETTINGS['max_attempts']}")

            try:
                result = await extract_from_source(
                    agent,
                    state,
                    source,
                )

                raw_companies = [
                    item.model_dump()
                    for item in result.final_output.companies
                ]

                raw_companies = raw_companies[
                    : SETTINGS["max_companies_per_source"]
                ]

                companies = [
                    attach_provenance(company, source)
                    for company in raw_companies
                ]

                all_companies.extend(companies)
                extracted_count = len(companies)
                source_success = True

                print(f"Companies found: {extracted_count}")

                for company in companies[:10]:
                    print(f"  - {company.get('company_name')}")

                if len(companies) > 10:
                    print(
                        f"  ... and {len(companies) - 10} more"
                    )

                break

            except asyncio.TimeoutError:
                print("Extraction timed out.")

            except Exception as exc:
                message = str(exc)
                print(f"Extraction failed: {message[:300]}")

                if is_daily_rate_limit(exc):
                    print()
                    print("DAILY MODEL RATE LIMIT REACHED")
                    print("Completed extraction has been checkpointed.")
                    print(
                        "Resume later with: "
                        "python run_demo.py --from-stage 03"
                    )
                    daily_limit_hit = True
                    break

            if attempt < SETTINGS["max_attempts"]:
                wait_seconds = SETTINGS["retry_wait"]
                print(
                    f"Retrying in {wait_seconds} seconds..."
                )
                await asyncio.sleep(wait_seconds)

        processed_sources.append(
            {
                "source_name": source_name,
                "status": (
                    "EXTRACTED"
                    if source_success
                    else (
                        "RATE_LIMITED"
                        if daily_limit_hit
                        else "FAILED"
                    )
                ),
                "companies_found": extracted_count,
            }
        )

        deduped = dedupe_companies(all_companies)

        save_checkpoint(
            state=state,
            companies=deduped,
            processed_sources=processed_sources,
        )

        if daily_limit_hit:
            break

        if index < len(selected_sources):
            await asyncio.sleep(
                SETTINGS["inter_source_delay"]
            )

    before_dedupe = len(all_companies)
    final_companies = dedupe_companies(all_companies)
    duplicates_removed = before_dedupe - len(final_companies)

    save_checkpoint(
        state=state,
        companies=final_companies,
        processed_sources=processed_sources,
    )

    print()
    print("=" * 72)
    print("COMPANY EXTRACTION COMPLETE")
    print("=" * 72)
    print()
    print(f"Companies before dedupe: {before_dedupe}")
    print(f"Duplicates removed: {duplicates_removed}")
    print(f"Companies after dedupe: {len(final_companies)}")
    print()

    for index, company in enumerate(
        final_companies[:20],
        start=1,
    ):
        print(f"{index}. {company.get('company_name')}")
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

    if len(final_companies) > 20:
        print(
            f"... {len(final_companies) - 20} additional "
            "companies saved to output."
        )
        print()

    print(f"Saved: {OUTPUT_FILE.relative_to(BASE_DIR)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
