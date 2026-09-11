import json
from pathlib import Path


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "discovered_sources.json"

EXTRACTABLE_FILE = DATA_DIR / "extractable_sources.json"
RESOLUTION_FILE = DATA_DIR / "resolution_sources.json"
REVIEW_FILE = DATA_DIR / "review_sources.json"
REJECTED_FILE = DATA_DIR / "rejected_sources.json"


# =========================================================
# THRESHOLDS
# =========================================================

MIN_CONFIDENCE = 0.80
MIN_EXTRACT_CONFIDENCE = 0.80


# =========================================================
# HELPERS
# =========================================================

def save_json(path, payload):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
        )


def route_source(source):
    """
    Deterministic routing.

    AI classifies the source.
    This function decides what the system trusts.
    """

    icp = source.get("icp_relevance")
    extractability = source.get("extractability")

    confidence = source.get("confidence", 0)
    extract_confidence = source.get(
        "extractability_confidence",
        0,
    )

    contains_haulers = source.get(
        "likely_contains_haulers",
        False,
    )

    # -----------------------------------------------------
    # REJECT
    # -----------------------------------------------------

    if icp == "OUT_OF_SCOPE":
        return "REJECTED", "Source is outside the target ICP."

    # -----------------------------------------------------
    # RESOLUTION
    # -----------------------------------------------------

    if (
        icp == "CORE"
        and extractability == "HUB"
    ):
        return (
            "RESOLUTION",
            "Relevant source hub requires underlying list/database resolution."
        )

    # -----------------------------------------------------
    # EXTRACTABLE
    # -----------------------------------------------------

    if (
        icp == "CORE"
        and extractability in {
            "DIRECT_LIST",
            "DATABASE",
        }
        and contains_haulers is True
        and confidence >= MIN_CONFIDENCE
        and extract_confidence >= MIN_EXTRACT_CONFIDENCE
    ):
        return (
            "EXTRACTABLE",
            "High-confidence CORE source suitable for company extraction."
        )

    # -----------------------------------------------------
    # REVIEW
    # -----------------------------------------------------

    if icp == "ADJACENT":
        return (
            "REVIEW",
            "Adjacent ICP source requires optional/manual inclusion decision."
        )

    if extractability == "REQUIREMENTS_PAGE":
        return (
            "REVIEW",
            "Requirements page does not directly provide company records."
        )

    if extractability == "UNKNOWN":
        return (
            "REVIEW",
            "Extractability is uncertain."
        )

    if confidence < MIN_CONFIDENCE:
        return (
            "REVIEW",
            f"Overall confidence below threshold ({MIN_CONFIDENCE:.2f})."
        )

    if extract_confidence < MIN_EXTRACT_CONFIDENCE:
        return (
            "REVIEW",
            f"Extractability confidence below threshold ({MIN_EXTRACT_CONFIDENCE:.2f})."
        )

    if contains_haulers is not True:
        return (
            "REVIEW",
            "Source does not confidently indicate identifiable hauler records."
        )

    return (
        "REVIEW",
        "Source does not meet deterministic extraction rules."
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print("SOURCE ROUTER")
    print("=" * 72)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing input file: {INPUT_FILE}"
        )

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(file)

    state = payload.get("state", "UNKNOWN")
    sources = payload.get("sources", [])

    extractable = []
    resolution = []
    review = []
    rejected = []

    print()
    print(f"State: {state}")
    print(f"Sources received: {len(sources)}")
    print()

    for number, source in enumerate(
        sources,
        start=1,
    ):

        route, reason = route_source(source)

        routed_source = dict(source)

        routed_source["routing_status"] = route
        routed_source["routing_reason"] = reason

        if route == "EXTRACTABLE":
            extractable.append(routed_source)

        elif route == "RESOLUTION":
            resolution.append(routed_source)

        elif route == "REJECTED":
            rejected.append(routed_source)

        else:
            review.append(routed_source)

        print(
            f"{number}. "
            f"{source.get('source_name', 'UNKNOWN')}"
        )

        print(
            f"   ICP:            "
            f"{source.get('icp_relevance')}"
        )

        print(
            f"   Extractability: "
            f"{source.get('extractability')}"
        )

        print(
            f"   Route:          "
            f"{route}"
        )

        print(
            f"   Why:            "
            f"{reason}"
        )

        print()

    # -----------------------------------------------------
    # SAVE OUTPUTS
    # -----------------------------------------------------

    save_json(
        EXTRACTABLE_FILE,
        {
            "state": state,
            "sources": extractable,
        },
    )

    save_json(
        RESOLUTION_FILE,
        {
            "state": state,
            "sources": resolution,
        },
    )

    save_json(
        REVIEW_FILE,
        {
            "state": state,
            "sources": review,
        },
    )

    save_json(
        REJECTED_FILE,
        {
            "state": state,
            "sources": rejected,
        },
    )

    # -----------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------

    print("=" * 72)
    print("ROUTING COMPLETE")
    print("=" * 72)

    print()
    print(
        f"READY FOR EXTRACTION: "
        f"{len(extractable)}"
    )

    print(
        f"NEEDS RESOLUTION:     "
        f"{len(resolution)}"
    )

    print(
        f"REVIEW:               "
        f"{len(review)}"
    )

    print(
        f"REJECTED:             "
        f"{len(rejected)}"
    )

    print()

    print(
        f"Saved: {EXTRACTABLE_FILE}"
    )

    print(
        f"Saved: {RESOLUTION_FILE}"
    )

    print(
        f"Saved: {REVIEW_FILE}"
    )

    print(
        f"Saved: {REJECTED_FILE}"
    )

    print()


if __name__ == "__main__":
    main()
