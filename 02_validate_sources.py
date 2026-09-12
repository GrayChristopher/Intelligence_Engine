import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INPUT_FILE = DATA_DIR / "discovered_sources.json"

EXTRACTABLE_FILE = DATA_DIR / "extractable_sources.json"
RESOLUTION_FILE = DATA_DIR / "resolution_sources.json"
REVIEW_FILE = DATA_DIR / "review_sources.json"
REJECTED_FILE = DATA_DIR / "rejected_sources.json"

MIN_CONFIDENCE = 0.80
MIN_EXTRACTABILITY_CONFIDENCE = 0.80


def normalize(value):
    return str(value or "").strip().upper()


def source_type(source):
    # Canonical field first, backward-compatible fallback second.
    return normalize(
        source.get("source_type")
        or source.get("extractability")
    )


def route_source(source):
    icp = normalize(source.get("icp_relevance"))
    stype = source_type(source)

    likely_contains = bool(source.get("likely_contains_haulers"))
    confidence = float(source.get("confidence", 0.0) or 0.0)
    extractability_confidence = float(
        source.get("extractability_confidence", 0.0) or 0.0
    )

    if icp == "OUT_OF_SCOPE":
        return (
            "REJECTED",
            "Source is outside the target ICP.",
        )

    if icp == "ADJACENT":
        return (
            "REVIEW",
            "Adjacent ICP source requires optional/manual inclusion decision.",
        )

    if stype == "HUB":
        if confidence >= MIN_CONFIDENCE:
            return (
                "RESOLUTION",
                "Relevant source hub requires resolution to an underlying extractable dataset.",
            )
        return (
            "REVIEW",
            "Relevant hub has insufficient confidence for automatic resolution.",
        )

    if stype in {"DIRECT_LIST", "DATABASE"}:
        if not likely_contains:
            return (
                "REVIEW",
                "Source structure is usable, but likely_contains_haulers is false.",
            )

        if confidence < MIN_CONFIDENCE:
            return (
                "REVIEW",
                f"Source confidence below {MIN_CONFIDENCE:.2f}.",
            )

        if extractability_confidence < MIN_EXTRACTABILITY_CONFIDENCE:
            return (
                "REVIEW",
                f"Extractability confidence below {MIN_EXTRACTABILITY_CONFIDENCE:.2f}.",
            )

        return (
            "EXTRACTABLE",
            "Core ICP source meets deterministic confidence and extractability rules.",
        )

    if stype == "REQUIREMENTS_PAGE":
        return (
            "REVIEW",
            "Requirements page is relevant but does not directly expose company records.",
        )

    if stype == "CONTRACT_RECORDS":
        return (
            "REVIEW",
            "Contract records may identify operators but are not a clean reusable company dataset.",
        )

    return (
        "REVIEW",
        "Source type is unknown or insufficiently structured for automatic extraction.",
    )


def write_payload(path, state, mode, model, sources):
    payload = {
        "state": state,
        "mode": mode,
        "model": model,
        "sources": sources,
    }

    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)


def main():
    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print("SOURCE ROUTER")
    print("=" * 72)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        payload = json.load(file)

    state = payload.get("state", "UNKNOWN")
    mode = payload.get("mode")
    model = payload.get("model")
    sources = payload.get("sources", [])

    extractable = []
    resolution = []
    review = []
    rejected = []

    print()
    print(f"State: {state}")
    print(f"Sources received: {len(sources)}")
    print()

    for index, source in enumerate(sources, start=1):
        stype = source_type(source)

        # Normalize canonical field for downstream stages.
        record = dict(source)
        record["source_type"] = stype

        route, reason = route_source(record)

        if route == "EXTRACTABLE":
            extractable.append(record)
        elif route == "RESOLUTION":
            resolution.append(record)
        elif route == "REVIEW":
            review.append(record)
        else:
            rejected.append(record)

        print(f"{index}. {record.get('source_name', 'UNKNOWN')}")
        print(f"   ICP:            {record.get('icp_relevance', 'UNKNOWN')}")
        print(f"   Extractability: {record.get('source_type', 'UNKNOWN')}")
        print(f"   Route:          {route}")
        print(f"   Why:            {reason}")
        print()

    write_payload(
        EXTRACTABLE_FILE,
        state,
        mode,
        model,
        extractable,
    )
    write_payload(
        RESOLUTION_FILE,
        state,
        mode,
        model,
        resolution,
    )
    write_payload(
        REVIEW_FILE,
        state,
        mode,
        model,
        review,
    )
    write_payload(
        REJECTED_FILE,
        state,
        mode,
        model,
        rejected,
    )

    print("=" * 72)
    print("SOURCE ROUTING COMPLETE")
    print("=" * 72)
    print()
    print(f"EXTRACTABLE: {len(extractable)}")
    print(f"RESOLUTION:  {len(resolution)}")
    print(f"REVIEW:      {len(review)}")
    print(f"REJECTED:    {len(rejected)}")
    print()
    print("Saved:")
    print(f"  {EXTRACTABLE_FILE.relative_to(BASE_DIR)}")
    print(f"  {RESOLUTION_FILE.relative_to(BASE_DIR)}")
    print(f"  {REVIEW_FILE.relative_to(BASE_DIR)}")
    print(f"  {REJECTED_FILE.relative_to(BASE_DIR)}")
    print()


if __name__ == "__main__":
    main()
