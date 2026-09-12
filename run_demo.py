import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from config import MODEL, MODE, SETTINGS


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STAGES = [
    ("01", "AI Source Discovery", "01_source_discovery_agent.py"),
    ("02", "Deterministic Source Routing", "02_validate_sources.py"),
    ("03", "AI Company Extraction", "03_company_extraction_agent.py"),
    ("04", "AI Company Research / Enrichment", "04_company_research_agent.py"),
    ("05", "Deterministic Company Validation", "05_validate_companies.py"),
    ("06", "Deterministic ICP Scoring", "06_score_companies.py"),
]


def load_json(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def count_list(payload, key):
    value = payload.get(key, []) if isinstance(payload, dict) else []
    return len(value) if isinstance(value, list) else 0


def source_count(filename):
    payload = load_json(filename)
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("sources", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return 0


def print_header():
    print()
    print("=" * 76)
    print("HAULER INTELLIGENCE ENGINE")
    print("=" * 76)
    print()
    print("Agentic research + deterministic validation and ICP scoring")
    print()
    print(f"Mode:  {MODE.upper()}")
    print(f"Model: {MODEL}")
    print()
    print("Demo configuration:")
    print(f"  Source target:              {SETTINGS['source_target']}")
    print(f"  Extraction sources:         {SETTINGS['max_extraction_sources']}")
    print(f"  Companies per source:       {SETTINGS['max_companies_per_source']}")
    print(f"  Companies researched:       {SETTINGS['max_enrichment_companies']}")
    print()


def run_stage(stage_number, label, script):
    print()
    print("-" * 76)
    print(f"STAGE {stage_number}/06 | {label}")
    print("-" * 76)
    print()

    started = time.time()

    result = subprocess.run(
        [sys.executable, script],
        cwd=BASE_DIR,
    )

    elapsed = time.time() - started

    if result.returncode != 0:
        print()
        print(f"STAGE {stage_number} FAILED ({elapsed:.1f}s)")
        print(f"Exit code: {result.returncode}")
        return False

    print()
    print(f"STAGE {stage_number} COMPLETE ({elapsed:.1f}s)")
    return True


def print_summary(runtime=None):
    discovered = load_json("discovered_sources.json")
    extracted = load_json("discovered_companies.json")
    enriched = load_json("enriched_companies.json")
    validated = load_json("validated_companies.json")
    ranked = load_json("ranked_companies.json")

    state = (
        discovered.get("state")
        or extracted.get("state")
        or enriched.get("state")
        or validated.get("state")
        or ranked.get("state")
        or "UNKNOWN"
    )

    extracted_companies = count_list(extracted, "companies")
    downstream_companies = count_list(enriched, "companies")

    processed = enriched.get("processed", []) if isinstance(enriched, dict) else []

    successfully_enriched = sum(
        1
        for item in processed
        if isinstance(item, dict) and item.get("status") == "ENRICHED"
    )

    research_failures_retained = sum(
        1
        for item in processed
        if isinstance(item, dict) and item.get("status") == "ORIGINAL_RETAINED"
    )

    unresearched_retained = sum(
        1
        for item in processed
        if isinstance(item, dict)
        and item.get("status") == "NOT_SELECTED_FOR_RESEARCH"
    )

    validated_companies = count_list(validated, "validated")
    review_companies = count_list(validated, "review")
    rejected_companies = count_list(validated, "rejected")
    ranked_companies = count_list(ranked, "companies")

    print()
    print("=" * 76)
    print("HAULER INTELLIGENCE ENGINE | RUN SUMMARY")
    print("=" * 76)
    print()
    print(f"State:                       {state}")
    print(f"Mode:                        {MODE.upper()}")
    print(f"Model:                       {MODEL}")
    print()
    print(f"Sources discovered:          {source_count('discovered_sources.json')}")
    print(f"Sources extractable:         {source_count('extractable_sources.json')}")
    print(f"Sources needing resolution:  {source_count('resolution_sources.json')}")
    print(f"Sources for review:          {source_count('review_sources.json')}")
    print(f"Sources rejected:            {source_count('rejected_sources.json')}")
    print()
    print(f"Companies extracted:         {extracted_companies}")
    print(f"Companies passed downstream: {downstream_companies}")
    print(f"Successfully enriched:       {successfully_enriched}")
    print(f"Research failures retained:  {research_failures_retained}")
    print(f"Unresearched retained:       {unresearched_retained}")
    print()
    print(f"Companies validated:         {validated_companies}")
    print(f"Companies for review:        {review_companies}")
    print(f"Companies rejected:          {rejected_companies}")
    print(f"Companies ranked:            {ranked_companies}")
    print()
    print("FINAL OUTPUT")
    print("-" * 76)
    print("JSON: data/ranked_companies.json")
    print("CSV:  data/ranked_companies.csv")

    companies = ranked.get("companies", []) if isinstance(ranked, dict) else []

    if companies:
        print()
        print("TOP RANKED COMPANIES")
        print("-" * 76)

        for index, company in enumerate(companies[:10], start=1):
            name = company.get("company_name", "UNKNOWN")
            score = company.get("score_total", 0)
            print(f"#{index:<3} {score:>3}/100  {name}")

    if runtime is not None:
        print()
        print(f"Pipeline runtime: {runtime:.1f} seconds")

    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-stage",
        choices=[stage[0] for stage in STAGES],
        help="Start execution from a specific stage.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print the current pipeline summary without running stages.",
    )
    args = parser.parse_args()

    print_header()

    if args.summary_only:
        print_summary()
        return

    start_index = 0

    if args.from_stage:
        start_index = next(
            index
            for index, stage in enumerate(STAGES)
            if stage[0] == args.from_stage
        )

    started = time.time()

    for stage_number, label, script in STAGES[start_index:]:
        if not run_stage(stage_number, label, script):
            print()
            print("Pipeline stopped at the failed stage.")
            print(
                f"Resume after resolving the issue with: "
                f"python run_demo.py --from-stage {stage_number}"
            )
            sys.exit(1)

    runtime = time.time() - started
    print_summary(runtime=runtime)


if __name__ == "__main__":
    main()
