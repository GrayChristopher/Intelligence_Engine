import csv
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INPUT_FILE = DATA_DIR / "validated_companies.json"
JSON_OUTPUT = DATA_DIR / "ranked_companies.json"
CSV_OUTPUT = DATA_DIR / "ranked_companies.csv"

CORE_SERVICE_TERMS = {
    "roll-off",
    "roll off",
    "dumpster",
    "commercial waste",
    "residential waste",
    "waste collection",
    "waste hauling",
    "solid waste",
    "recycling",
    "construction debris",
    "front-load",
    "front load",
    "rear-load",
    "rear load",
}

ADJACENT_SERVICE_TERMS = {
    "portable toilet",
    "portable restroom",
    "restroom trailer",
    "septic",
    "liquid waste",
    "grease",
    "holding tank",
}


def normalize(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def has_value(value):
    if value is None:
        return False
    if isinstance(value, list):
        return any(has_value(item) for item in value)
    return normalize(value) not in {
        "",
        "unknown",
        "none",
        "null",
        "n/a",
    }


def as_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def first_value(company, *keys):
    for key in keys:
        value = company.get(key)
        if has_value(value):
            return value
    return None


def canonicalize(company):
    record = dict(company)
    record["source_name"] = first_value(
        company, "source_name", "discovery_source_name"
    )
    record["source_url"] = first_value(
        company, "source_url", "discovery_source_url"
    )
    record["source_evidence"] = first_value(
        company, "source_evidence", "evidence", "discovery_evidence"
    )
    record["discovery_confidence"] = as_float(
        first_value(company, "discovery_confidence", "confidence")
    )
    if "service_lines" not in record or record["service_lines"] is None:
        record["service_lines"] = []
    return record


def get_service_text(company):
    services = company.get("service_lines", [])
    if isinstance(services, str):
        services = [services]
    return " ".join(normalize(service) for service in services)


def find_matches(text, terms):
    return sorted(term for term in terms if term in text)


def score_service_fit(company):
    text = get_service_text(company)
    core_matches = find_matches(text, CORE_SERVICE_TERMS)
    adjacent_matches = find_matches(text, ADJACENT_SERVICE_TERMS)

    core_count = len(core_matches)
    adjacent_count = len(adjacent_matches)

    if core_count >= 3:
        score = 40
    elif core_count == 2:
        score = 35
    elif core_count == 1:
        score = 30
    elif adjacent_count >= 1:
        score = 15
    else:
        score = 0

    return score, core_matches, adjacent_matches


def score_complexity(core_matches, adjacent_matches):
    count = len(set(core_matches + adjacent_matches))

    if count >= 5:
        return 20
    if count >= 3:
        return 15
    if count >= 2:
        return 10
    if count == 1:
        return 5
    return 0


def score_scale(company):
    if not has_value(company.get("size_signal")):
        return 0

    research_confidence = as_float(
        company.get("research_confidence")
    )

    if research_confidence >= 0.90:
        return 20
    if research_confidence >= 0.75:
        return 15
    return 10


def score_data_confidence(company):
    company = canonicalize(company)
    score = 0

    # 8 points: complete authoritative discovery provenance
    if (
        has_value(company.get("source_name"))
        and has_value(company.get("source_url"))
        and has_value(company.get("source_evidence"))
    ):
        score += 8

    # 4 points: discovery confidence
    discovery_confidence = as_float(
        company.get("discovery_confidence")
    )

    if discovery_confidence >= 0.90:
        score += 4
    elif discovery_confidence >= 0.75:
        score += 3
    elif discovery_confidence > 0:
        score += 1

    # 6 points: contactability
    if has_value(company.get("phone")):
        score += 2
    if has_value(company.get("website")):
        score += 2
    if has_value(company.get("location")):
        score += 2

    # 2 points: successful research
    if as_float(company.get("research_confidence")) >= 0.75:
        score += 2

    return min(score, 20)


def score_company(raw_company):
    company = canonicalize(raw_company)

    service_score, core_matches, adjacent_matches = score_service_fit(company)
    complexity_score = score_complexity(core_matches, adjacent_matches)
    scale_score = score_scale(company)
    data_score = score_data_confidence(company)

    total_score = (
        service_score
        + complexity_score
        + scale_score
        + data_score
    )

    scored = dict(company)
    scored["score_service_fit"] = service_score
    scored["score_complexity"] = complexity_score
    scored["score_scale"] = scale_score
    scored["score_data_confidence"] = data_score
    scored["score_total"] = total_score
    scored["score_core_matches"] = core_matches
    scored["score_adjacent_matches"] = adjacent_matches

    return scored


def save_csv(companies):
    fields = [
        "rank",
        "company_name",
        "location",
        "phone",
        "website",
        "service_lines",
        "size_signal",
        "discovery_confidence",
        "research_confidence",
        "score_service_fit",
        "score_complexity",
        "score_scale",
        "score_data_confidence",
        "score_total",
        "source_name",
        "source_url",
        "source_evidence",
    ]

    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for company in companies:
            services = company.get("service_lines", [])
            if isinstance(services, str):
                services_text = services
            else:
                services_text = " | ".join(services)

            row = {
                "rank": company.get("rank"),
                "company_name": company.get("company_name"),
                "location": company.get("location"),
                "phone": company.get("phone"),
                "website": company.get("website"),
                "service_lines": services_text,
                "size_signal": company.get("size_signal"),
                "discovery_confidence": company.get(
                    "discovery_confidence"
                ),
                "research_confidence": company.get(
                    "research_confidence"
                ),
                "score_service_fit": company.get(
                    "score_service_fit"
                ),
                "score_complexity": company.get(
                    "score_complexity"
                ),
                "score_scale": company.get("score_scale"),
                "score_data_confidence": company.get(
                    "score_data_confidence"
                ),
                "score_total": company.get("score_total"),
                "source_name": company.get("source_name"),
                "source_url": company.get("source_url"),
                "source_evidence": company.get(
                    "source_evidence"
                ),
            }
            writer.writerow(row)


def main():
    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print("DETERMINISTIC ICP SCORING")
    print("=" * 72)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        payload = json.load(file)

    state = payload.get("state", "UNKNOWN")
    companies = payload.get("validated", [])

    print()
    print(f"State: {state}")
    print(f"Validated companies: {len(companies)}")

    scored_companies = [
        score_company(company) for company in companies
    ]

    scored_companies.sort(
        key=lambda company: (
            company.get("score_total", 0),
            company.get("score_service_fit", 0),
            company.get("score_data_confidence", 0),
            company.get("company_name", ""),
        ),
        reverse=True,
    )

    for rank, company in enumerate(scored_companies, start=1):
        company["rank"] = rank

    final_payload = {
        "state": state,
        "companies_ranked": len(scored_companies),
        "scoring_model": {
            "service_fit_max": 40,
            "operational_complexity_max": 20,
            "scale_max": 20,
            "data_confidence_max": 20,
            "total_max": 100,
        },
        "companies": scored_companies,
    }

    with open(JSON_OUTPUT, "w", encoding="utf-8") as file:
        json.dump(final_payload, file, indent=2, ensure_ascii=False)

    save_csv(scored_companies)

    print()
    print("=" * 72)
    print("ICP RANKING")
    print("=" * 72)
    print()

    for company in scored_companies:
        print(f"#{company['rank']}  {company.get('company_name')}")
        print(f"    TOTAL:       {company.get('score_total')}/100")
        print(
            f"    Service:     "
            f"{company.get('score_service_fit')}/40"
        )
        print(
            f"    Complexity:  "
            f"{company.get('score_complexity')}/20"
        )
        print(f"    Scale:       {company.get('score_scale')}/20")
        print(
            f"    Data:        "
            f"{company.get('score_data_confidence')}/20"
        )
        print(
            f"    Size signal: "
            f"{company.get('size_signal') or 'UNKNOWN'}"
        )
        print()

    print("=" * 72)
    print("SCORING COMPLETE")
    print("=" * 72)
    print()
    print(f"Companies ranked: {len(scored_companies)}")
    print(f"JSON: {JSON_OUTPUT}")
    print(f"CSV:  {CSV_OUTPUT}")
    print()


if __name__ == "__main__":
    main()
