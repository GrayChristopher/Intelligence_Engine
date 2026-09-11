import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "discovered_sources.json"
ACCEPTED_FILE = DATA_DIR / "accepted_sources.json"
REVIEW_FILE = DATA_DIR / "review_sources.json"
REJECTED_FILE = DATA_DIR / "rejected_sources.json"


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing input file: {INPUT_FILE}"
        )

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    accepted = []
    review = []
    rejected = []

    for source in data["sources"]:

        relevance = source["icp_relevance"]
        confidence = source["confidence"]
        contains_haulers = source["likely_contains_haulers"]

        if relevance == "OUT_OF_SCOPE":
            rejected.append(source)

        elif relevance == "CORE" and confidence >= 0.85 and contains_haulers:
            accepted.append(source)

        else:
            review.append(source)

    with open(ACCEPTED_FILE, "w", encoding="utf-8") as f:
        json.dump(accepted, f, indent=2)

    with open(REVIEW_FILE, "w", encoding="utf-8") as f:
        json.dump(review, f, indent=2)

    with open(REJECTED_FILE, "w", encoding="utf-8") as f:
        json.dump(rejected, f, indent=2)

    print("\nSOURCE VALIDATION COMPLETE")
    print("=" * 50)

    print(f"Accepted: {len(accepted)}")
    print(f"Review:   {len(review)}")
    print(f"Rejected: {len(rejected)}")

    print("\nAccepted sources:")
    for source in accepted:
        print(
            f"- {source['source_name']} "
            f"({source['confidence']:.2f})"
        )

    print("\nReview sources:")
    for source in review:
        print(
            f"- {source['source_name']} "
            f"[{source['icp_relevance']}] "
            f"({source['confidence']:.2f})"
        )

    print("\nRejected sources:")
    for source in rejected:
        print(
            f"- {source['source_name']} "
            f"({source['confidence']:.2f})"
        )


if __name__ == "__main__":
    main()
