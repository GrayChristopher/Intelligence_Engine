import argparse
import json
import os
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


def load_json(path):
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return None


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
    print(f"{MODE.capitalize()} configuration:")
    print(f"  Source target:              {SETTINGS['source_target']}")
    print(f"  Extraction sources:         {SETTINGS['max_extraction_sources']}")
    print(f"  Companies per source:       {SETTINGS['max_companies_per_source']}")
    print(f"  Companies researched:       {SETTINGS['max_enrichment_companies']}")
    print()


def run_stage(stage_num, label, script):
    print()
    print("-" * 76)
    print(f"STAGE {stage_num}/06 | {label}")
    print("-" * 76)
    print()

    start = time.time()

    result = subprocess.run(
        [sys.executable, script],
        cwd=BASE_DIR,
        env=os.environ.copy(),
    )

    elapsed = time.time() - start

    if result.returncode != 0:
        print()
        print("=" * 76)
        print(f"STAGE {stage_num} FAILED")
        print("=" * 76)
        print()
        print(f"Script: {script}")
        print(f"Exit code: {result.returncode}")
        print()
        print("Completed upstream outputs remain available in data/.")
        print(
            f"Resume with: python run_demo.py --from-stage {stage_num}"
        )
        return False

    print()
    print(f"STAGE {stage_num} COMPLETE ({elapsed:.1f}s)")
    return True


def count_list(payload, key):
    if not payload:
        return 0
    value = payload.get(key, [])
    return len(value) if isinstance(value, list) else 0


def show_summary():
    discovered = load_json(DATA_DIR / "discovered_sources.json")
    extractable = load_json(DATA_DIR / "extractable_sources.json")
    resolution = load_json(DATA_DIR / "resolution_sources.json")
    review_sources = load_json(DATA_DIR / "review_sources.json")
    rejected_sources = load_json(DATA_DIR / "rejected_sources.json")

    extracted = load_json(DATA_DIR / "discovered_companies.json")
    enriched = load_json(DATA_DIR / "enriched_companies.json")
    validated = load_json(DATA_DIR / "validated_companies.json")
    ranked = load_json(DATA_DIR / "ranked_companies.json")

    state = (
        (ranked or {}).get("state")
        or (validated or {}).get("state")
        or (enriched or {}).get("state")
        or (extracted or {}).get("state")
        or (discovered or {}).get("state")
        or "UNKNOWN"
    )

    discovered_count = count_list(discovered, "sources")

    # Routed source files may be list payloads or object payloads.
    def source_count(payload):
        if payload is None:
            return 0
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            for key in ("sources", "items", "records"):
                if isinstance(payload.get(key), list):
                    return len(payload[key])
        return 0

    extractable_count = source_count(extractable)
    resolution_count = source_count(resolution)
    review_source_count = source_count(review_sources)
    rejected_source_count = source_count(rejected_sources)

    extracted_companies = count_list(extracted, "companies")
    enriched_companies = count_list(enriched, "companies")

    processed = (enriched or {}).get("processed", [])
    successfully_enriched = sum(
        1 for item in processed
        if item.get("status") == "ENRICHED"
    )
    originals_retained = sum(
        1 for item in processed
        if item.get("status") == "ORIGINAL_RETAINED"
    )

    validated_count = (validated or {}).get(
        "validated_count",
        count_list(validated, "validated")
    )
    review_count = (validated or {}).get(
        "review_count",
        count_list(validated, "review")
    )
    rejected_count = (validated or {}).get(
        "rejected_count",
        count_list(validated, "rejected")
    )

    ranked_count = (ranked or {}).get(
        "companies_ranked",
        count_list(ranked, "companies")
    )

    print()
    print("=" * 76)
    print("HAULER INTELLIGENCE ENGINE | RUN SUMMARY")
    print("=" * 76)
    print()
    print(f"State:                      {state}")
    print(f"Mode:                       {MODE.upper()}")
    print(f"Model:                      {MODEL}")
    print()
    print(f"Sources discovered:         {discovered_count}")
    print(f"Sources extractable:        {extractable_count}")
    print(f"Sources needing resolution: {resolution_count}")
    print(f"Sources for review:         {review_source_count}")
    print(f"Sources rejected:           {rejected_source_count}")
    print()
    print(f"Companies extracted:        {extracted_companies}")
    print(f"Companies in research set:  {enriched_companies}")
    print(f"Successfully enriched:      {successfully_enriched}")
    print(f"Original records retained:  {originals_retained}")
    print()
    print(f"Companies validated:        {validated_count}")
    print(f"Companies for review:       {review_count}")
    print(f"Companies rejected:         {rejected_count}")
    print(f"Companies ranked:           {ranked_count}")
    print()
    print("FINAL OUTPUT")
    print("-" * 76)
    print("JSON: data/ranked_companies.json")
    print("CSV:  data/ranked_companies.csv")

    if ranked and isinstance(ranked.get("companies"), list):
        top = ranked["companies"][:10]
        if top:
            print()
            print("TOP RANKED COMPANIES")
            print("-" * 76)
            for company in top:
                rank = company.get("rank", "-")
                name = company.get("company_name", "UNKNOWN")
                score = company.get("score_total", 0)
                print(f"#{rank:<3} {score:>3}/100  {name}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Run the Hauler Intelligence Engine."
    )
    parser.add_argument(
        "--from-stage",
        choices=[stage[0] for stage in STAGES],
        help="Start execution from a specific pipeline stage.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Show existing pipeline results without making API calls.",
    )
    args = parser.parse_args()

    print_header()

    if args.summary_only:
        show_summary()
        return

    start_index = 0

    if args.from_stage:
        stage_numbers = [stage[0] for stage in STAGES]
        start_index = stage_numbers.index(args.from_stage)

    pipeline_start = time.time()

    for stage_num, label, script in STAGES[start_index:]:
        if not run_stage(stage_num, label, script):
            sys.exit(1)

    total_elapsed = time.time() - pipeline_start

    show_summary()
    print(f"Pipeline runtime: {total_elapsed:.1f} seconds")
    print()


if __name__ == "__main__":
    main()
