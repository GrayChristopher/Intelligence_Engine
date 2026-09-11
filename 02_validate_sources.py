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
# CONFIG
# =========================================================

MIN_CONFIDENCE = 0.80
MIN_EXTRACT_CONFIDENCE = 0.80


# =========================================================
# HELPERS
# =========================================================

def load_input():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing input file: {INPUT_FILE}"
        )

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def write_output(
    path: Path,
    state: str,
    sources: list,
):

    payload = {
        "state": state,
        "sources": sources,
    }

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
        )


def get_source_type(source: dict):

    # Current schema from 01_source_discovery_agent.py
    source_type = source.get("source_type")

    # Backward compatibility with older schema
    if not source_type:
        source_type = source.get("extractability")

    return source_type or "UNKNOWN"


# =========================================================
# ROUTING
# =========================================================

def route_source(source: dict):

    icp = (
        source.get(
            "icp_relevance",
            "OUT_OF_SCOPE",
        )
        or "OUT_OF_SCOPE"
    ).upper()

    source_type = (
        get_source_type(source)
        or "UNKNOWN"
    ).upper()

    confidence = float(
        source.get(
            "confidence",
            0.0,
        )
        or 0.0
    )

    extract_confidence = float(
        source.get(
            "extractability_confidence",
            0.0,
        )
        or 0.0
    )

    likely_contains_haulers = bool(
        source.get(
            "likely_contains_haulers",
            False,
        )
    )

    # -----------------------------------------------------
    # OUT OF SCOPE
    # -----------------------------------------------------

    if icp == "OUT_OF_SCOPE":

        return (
            "REJECTED",
            "Source is outside the target ICP.",
        )

    # -----------------------------------------------------
    # ADJACENT ICP
    # -----------------------------------------------------

    if icp == "ADJACENT":

        return (
            "REVIEW",
            (
                "Adjacent ICP source requires "
                "optional/manual inclusion decision."
            ),
        )

    # -----------------------------------------------------
    # CORE HUB
    # -----------------------------------------------------

    if (
        icp == "CORE"
        and source_type == "HUB"
        and confidence >= MIN_CONFIDENCE
    ):

        return (
            "RESOLUTION",
            (
                "Relevant source hub requires resolution "
                "to an underlying extractable dataset."
            ),
        )

    # -----------------------------------------------------
    # CORE DIRECTLY EXTRACTABLE
    # -----------------------------------------------------

    if (
        icp == "CORE"
        and source_type in {
            "DIRECT_LIST",
            "DATABASE",
        }
        and likely_contains_haulers
        and confidence >= MIN_CONFIDENCE
        and extract_confidence
        >= MIN_EXTRACT_CONFIDENCE
    ):

        return (
            "EXTRACTABLE",
            (
                "Core ICP source meets deterministic "
                "confidence and extractability rules."
            ),
        )

    # -----------------------------------------------------
    # REQUIREMENTS / POLICY PAGE
    # -----------------------------------------------------

    if source_type == "REQUIREMENTS_PAGE":

        return (
            "REVIEW",
            (
                "Relevant requirements page does not "
                "directly provide extractable hauler records."
            ),
        )

    # -----------------------------------------------------
    # CONTRACT RECORDS
    # -----------------------------------------------------

    if source_type == "CONTRACT_RECORDS":

        return (
            "REVIEW",
            (
                "Contract records may contain useful "
                "operators but require additional review."
            ),
        )

    # -----------------------------------------------------
    # LOW CONFIDENCE
    # -----------------------------------------------------

    if confidence < MIN_CONFIDENCE:

        return (
            "REVIEW",
            (
                f"Source confidence {confidence:.2f} "
                f"is below threshold "
                f"{MIN_CONFIDENCE:.2f}."
            ),
        )

    if (
        source_type
        in {
            "DIRECT_LIST",
            "DATABASE",
        }
        and extract_confidence
        < MIN_EXTRACT_CONFIDENCE
    ):

        return (
            "REVIEW",
            (
                f"Extractability confidence "
                f"{extract_confidence:.2f} "
                f"is below threshold "
                f"{MIN_EXTRACT_CONFIDENCE:.2f}."
            ),
        )

    if (
        source_type
        in {
            "DIRECT_LIST",
            "DATABASE",
        }
        and not likely_contains_haulers
    ):

        return (
            "REVIEW",
            (
                "Source structure may be extractable, "
                "but it is not sufficiently clear that "
                "it contains private hauler records."
            ),
        )

    # -----------------------------------------------------
    # DEFAULT
    # -----------------------------------------------------

    return (
        "REVIEW",
        (
            "Source does not meet deterministic "
            "extraction rules."
        ),
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

    payload = load_input()

    state = payload.get(
        "state",
        "UNKNOWN",
    )

    sources = payload.get(
        "sources",
        [],
    )

    extractable = []
    resolution = []
    review = []
    rejected = []

    print()
    print(f"State: {state}")
    print(
        f"Sources received: "
        f"{len(sources)}"
    )
    print()

    for index, source in enumerate(
        sources,
        start=1,
    ):

        route, reason = route_source(
            source
        )

        routed_source = dict(source)

        # Normalize the source type so downstream scripts
        # always have the current field available.
        routed_source["source_type"] = (
            get_source_type(source)
        )

        routed_source["route"] = route
        routed_source["route_reason"] = reason

        if route == "EXTRACTABLE":
            extractable.append(
                routed_source
            )

        elif route == "RESOLUTION":
            resolution.append(
                routed_source
            )

        elif route == "REJECTED":
            rejected.append(
                routed_source
            )

        else:
            review.append(
                routed_source
            )

        print(
            f"{index}. "
            f"{source.get('source_name', 'UNKNOWN')}"
        )

        print(
            f"   ICP:            "
            f"{source.get('icp_relevance', 'UNKNOWN')}"
        )

        print(
            f"   Extractability: "
            f"{get_source_type(source)}"
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

    write_output(
        EXTRACTABLE_FILE,
        state,
        extractable,
    )

    write_output(
        RESOLUTION_FILE,
        state,
        resolution,
    )

    write_output(
        REVIEW_FILE,
        state,
        review,
    )

    write_output(
        REJECTED_FILE,
        state,
        rejected,
    )

    print("=" * 72)
    print("SOURCE ROUTING COMPLETE")
    print("=" * 72)

    print()
    print(
        f"EXTRACTABLE: "
        f"{len(extractable)}"
    )

    print(
        f"RESOLUTION:  "
        f"{len(resolution)}"
    )

    print(
        f"REVIEW:      "
        f"{len(review)}"
    )

    print(
        f"REJECTED:    "
        f"{len(rejected)}"
    )

    print()

    print(
        "Saved:"
    )

    print(
        "  data/extractable_sources.json"
    )

    print(
        "  data/resolution_sources.json"
    )

    print(
        "  data/review_sources.json"
    )

    print(
        "  data/rejected_sources.json"
    )

    print()


if __name__ == "__main__":
    main()
