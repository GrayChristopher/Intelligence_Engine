import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


# =========================================================
# CONFIG
# =========================================================

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


# =========================================================
# DISPLAY
# =========================================================

def header(text):
    print()
    print("=" * 76)
    print(text)
    print("=" * 76)


def stage_header(number, name):
    print()
    print("-" * 76)
    print(f"STAGE {number}/06 | {name}")
    print("-" * 76)
    print()


# =========================================================
# RUN STAGE
# =========================================================

def run_stage(number, name, script):
    stage_header(number, name)

    script_path = BASE_DIR / script

    if not script_path.exists():
        print(f"ERROR: Missing {script}")
        return False

    start = time.time()

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=BASE_DIR,
    )

    elapsed = time.time() - start

    if result.returncode != 0:
        print()
        print(
            f"STAGE {number} FAILED "
            f"after {elapsed:.1f}s"
        )
        return False

    print()
    print(
        f"STAGE {number} COMPLETE "
        f"({elapsed:.1f}s)"
    )

    return True


# =========================================================
# READ OUTPUT HELPERS
# =========================================================

def load_json(filename):
    path = DATA_DIR / filename

    if not path.exists():
        return {}

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception:
        return {}


def count_sources(filename):
    payload = load_json(filename)
    return len(payload.get("sources", []))


# =========================================================
# FINAL SUMMARY
# =========================================================

def print_summary():
    discovered = load_json(
        "discovered_sources.json"
    )

    extracted = load_json(
        "discovered_companies.json"
    )

    enriched = load_json(
        "enriched_companies.json"
    )

    validated = load_json(
        "validated_companies.json"
    )

    ranked = load_json(
        "ranked_companies.json"
    )

    state = (
        ranked.get("state")
        or validated.get("state")
        or enriched.get("state")
        or extracted.get("state")
        or discovered.get("state")
        or "UNKNOWN"
    )

    sources_discovered = len(
        discovered.get("sources", [])
    )

    sources_extractable = count_sources(
        "extractable_sources.json"
    )

    sources_resolution = count_sources(
        "resolution_sources.json"
    )

    companies_extracted = len(
        extracted.get("companies", [])
    )

    companies_available = enriched.get(
        "companies_available",
        companies_extracted,
    )

    companies_researched = enriched.get(
        "companies_researched",
        len(enriched.get("companies", [])),
    )

    enriched_statuses = enriched.get(
        "processed",
        [],
    )

    successfully_enriched = sum(
        1
        for item in enriched_statuses
        if item.get("status") == "ENRICHED"
    )

    companies_validated = validated.get(
        "validated_count",
        len(validated.get("validated", [])),
    )

    companies_review = validated.get(
        "review_count",
        len(validated.get("review", [])),
    )

    companies_rejected = validated.get(
        "rejected_count",
        len(validated.get("rejected", [])),
    )

    ranked_companies = ranked.get(
        "companies",
        [],
    )

    header("HAULER INTELLIGENCE ENGINE | RUN COMPLETE")

    print()
    print(f"State:                     {state}")
    print()
    print(f"Sources discovered:        {sources_discovered}")
    print(f"Sources extractable:       {sources_extractable}")
    print(f"Sources needing resolution:{sources_resolution:>8}")
    print()
    print(f"Companies extracted:       {companies_extracted}")
    print(f"Companies available:       {companies_available}")
    print(f"Companies researched:      {companies_researched}")
    print(f"Successfully enriched:     {successfully_enriched}")
    print()
    print(f"Companies validated:       {companies_validated}")
    print(f"Companies for review:      {companies_review}")
    print(f"Companies rejected:        {companies_rejected}")
    print(f"Companies ranked:          {len(ranked_companies)}")

    if ranked_companies:
        print()
        print("TOP ICP RESULTS")
        print("-" * 76)

        for company in ranked_companies[:5]:
            rank = company.get("rank", "?")
            name = company.get(
                "company_name",
                "UNKNOWN",
            )
            score = company.get(
                "score_total",
                0,
            )

            print(
                f"#{rank:<3} "
                f"{name:<40} "
                f"{score}/100"
            )

    print()
    print("OUTPUTS")
    print("-" * 76)
    print(
        "JSON: data/ranked_companies.json"
    )
    print(
        "CSV:  data/ranked_companies.csv"
    )
    print()


# =========================================================
# PIPELINE
# =========================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run the Hauler Intelligence Engine "
            "end-to-end."
        )
    )

    parser.add_argument(
        "--from-stage",
        choices=[
            "01",
            "02",
            "03",
            "04",
            "05",
            "06",
        ],
        default="01",
        help=(
            "Start from a specific pipeline stage. "
            "Default: 01"
        ),
    )

    parser.add_argument(
        "--summary-only",
        action="store_true",
        help=(
            "Display the latest pipeline outputs "
            "without making API calls."
        ),
    )

    args = parser.parse_args()

    header("HAULER INTELLIGENCE ENGINE")

    print()
    print(
        "Agentic research + deterministic "
        "validation and scoring"
    )

    if args.summary_only:
        print_summary()
        return

    start_index = next(
        index
        for index, stage in enumerate(STAGES)
        if stage[0] == args.from_stage
    )

    pipeline_start = time.time()

    for (
        number,
        name,
        script,
    ) in STAGES[start_index:]:

        success = run_stage(
            number,
            name,
            script,
        )

        if not success:
            print()
            print(
                "Pipeline stopped safely."
            )
            print(
                "Existing successful outputs "
                "have been retained."
            )
            sys.exit(1)

    elapsed = (
        time.time()
        - pipeline_start
    )

    print_summary()

    print(
        f"Pipeline runtime: "
        f"{elapsed:.1f} seconds"
    )
    print()


if __name__ == "__main__":
    main()
