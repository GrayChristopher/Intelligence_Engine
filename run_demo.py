import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from config import MODE, MODEL, SETTINGS


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


# =========================================================
# PIPELINE
# =========================================================

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


def print_mode():

    print()
    print(f"Mode:  {MODE.upper()}")
    print(f"Model: {MODEL}")

    print()

    if MODE == "demo":

        print("Demo configuration:")
        print(
            f"  Source target:              "
            f"{SETTINGS['source_target']}"
        )
        print(
            f"  Extraction sources:         "
            f"{SETTINGS['max_extraction_sources']}"
        )
        print(
            f"  Companies per source:       "
            f"{SETTINGS['max_companies_per_source']}"
        )
        print(
            f"  Companies researched:       "
            f"{SETTINGS['max_enrichment_companies']}"
        )

    else:

        print("Full configuration:")
        print(
            f"  Source target:              "
            f"{SETTINGS['source_target']}"
        )
        print(
            f"  Extraction sources:         "
            f"{SETTINGS['max_extraction_sources']}"
        )
        print(
            f"  Companies per source:       "
            f"{SETTINGS['max_companies_per_source']}"
        )
        print(
            f"  Companies researched:       "
            f"{SETTINGS['max_enrichment_companies']}"
        )

    print()


# =========================================================
# RUN STAGE
# =========================================================

def run_stage(number, name, script):

    stage_header(
        number,
        name,
    )

    script_path = BASE_DIR / script

    if not script_path.exists():

        print(
            f"ERROR: Missing pipeline script: "
            f"{script}"
        )

        return False

    start = time.time()

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
        ],
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
# JSON HELPERS
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


def get_list(
    payload,
    *keys,
):

    for key in keys:

        value = payload.get(key)

        if isinstance(value, list):
            return value

    return []


# =========================================================
# SUMMARY
# =========================================================

def print_summary():

    discovered = load_json(
        "discovered_sources.json"
    )

    extractable = load_json(
        "extractable_sources.json"
    )

    resolution = load_json(
        "resolution_sources.json"
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

    discovered_sources = get_list(
        discovered,
        "sources",
    )

    extractable_sources = get_list(
        extractable,
        "sources",
    )

    resolution_sources = get_list(
        resolution,
        "sources",
    )

    extracted_companies = get_list(
        extracted,
        "companies",
    )

    enriched_companies = get_list(
        enriched,
        "companies",
    )

    processed_research = get_list(
        enriched,
        "processed",
    )

    validated_companies = get_list(
        validated,
        "validated",
        "companies",
    )

    review_companies = get_list(
        validated,
        "review",
    )

    rejected_companies = get_list(
        validated,
        "rejected",
    )

    ranked_companies = get_list(
        ranked,
        "companies",
        "ranked_companies",
    )

    successfully_enriched = sum(
        1
        for item in processed_research
        if item.get("status") == "ENRICHED"
    )

    retained_original = sum(
        1
        for item in processed_research
        if item.get("status")
        == "ORIGINAL_RETAINED"
    )

    header(
        "HAULER INTELLIGENCE ENGINE | RUN SUMMARY"
    )

    print()
    print(f"State:                      {state}")
    print(f"Mode:                       {MODE.upper()}")
    print(f"Model:                      {MODEL}")

    print()

    print(
        f"Sources discovered:         "
        f"{len(discovered_sources)}"
    )

    print(
        f"Sources extractable:        "
        f"{len(extractable_sources)}"
    )

    print(
        f"Sources needing resolution: "
        f"{len(resolution_sources)}"
    )

    print()

    print(
        f"Companies extracted:        "
        f"{len(extracted_companies)}"
    )

    print(
        f"Companies researched:       "
        f"{len(enriched_companies)}"
    )

    print(
        f"Successfully enriched:      "
        f"{successfully_enriched}"
    )

    print(
        f"Original records retained:  "
        f"{retained_original}"
    )

    print()

    print(
        f"Companies validated:        "
        f"{len(validated_companies)}"
    )

    print(
        f"Companies for review:       "
        f"{len(review_companies)}"
    )

    print(
        f"Companies rejected:         "
        f"{len(rejected_companies)}"
    )

    print(
        f"Companies ranked:           "
        f"{len(ranked_companies)}"
    )

    if ranked_companies:

        print()
        print("TOP ICP RESULTS")
        print("-" * 76)

        for index, company in enumerate(
            ranked_companies[:5],
            start=1,
        ):

            rank = company.get(
                "rank",
                index,
            )

            name = company.get(
                "company_name",
                "UNKNOWN",
            )

            score = (
                company.get("score_total")
                or company.get("total_score")
                or company.get("score")
                or 0
            )

            print(
                f"#{rank:<3} "
                f"{name:<42} "
                f"{score}/100"
            )

    print()
    print("FINAL OUTPUT")
    print("-" * 76)

    print(
        "JSON: data/ranked_companies.json"
    )

    print(
        "CSV:  data/ranked_companies.csv"
    )

    print()


# =========================================================
# MAIN
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Run the Hauler Intelligence Engine."
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
            "Display the latest outputs without "
            "running any pipeline stages."
        ),
    )

    args = parser.parse_args()

    header(
        "HAULER INTELLIGENCE ENGINE"
    )

    print()
    print(
        "Agentic research + deterministic "
        "validation and ICP scoring"
    )

    print_mode()

    if args.summary_only:

        print_summary()
        return

    start_index = next(
        index
        for index, stage in enumerate(
            STAGES
        )
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
                "Previously completed outputs "
                "remain intact."
            )

            print()
            print(
                "You can inspect the latest "
                "successful state with:"
            )

            print(
                "python run_demo.py --summary-only"
            )

            print()

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
