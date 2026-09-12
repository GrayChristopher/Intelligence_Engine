import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INPUT_FILE = DATA_DIR / "enriched_companies.json"
OUTPUT_FILE = DATA_DIR / "validated_companies.json"

MIN_DISCOVERY_CONFIDENCE = 0.75

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
    """
    Normalize old/new field aliases into the canonical extraction schema.

    Canonical names:
      source_name
      source_url
      source_evidence
      discovery_confidence
    """
    record = dict(company)

    record["source_name"] = first_value(
        company,
        "source_name",
        "discovery_source_name",
    )
    record["source_url"] = first_value(
        company,
        "source_url",
        "discovery_source_url",
    )
    record["source_evidence"] = first_value(
        company,
        "source_evidence",
        "evidence",
        "discovery_evidence",
    )

    raw_confidence = first_value(
        company,
        "discovery_confidence",
        "confidence",
    )
    record["discovery_confidence"] = as_float(raw_confidence)

    if "service_lines" not in record or record["service_lines"] is None:
        record["service_lines"] = []

    return record


def service_text(company):
    services = company.get("service_lines", [])
    if isinstance(services, str):
        services = [services]
    return " ".join(normalize(service) for service in services)


def detect_service_fit(company):
    text = service_text(company)

    core_matches = sorted(
        term for term in CORE_SERVICE_TERMS if term in text
    )
    adjacent_matches = sorted(
        term for term in ADJACENT_SERVICE_TERMS if term in text
    )

    if core_matches:
        return "CORE", core_matches
    if adjacent_matches:
        return "ADJACENT", adjacent_matches
    return "UNKNOWN", []


def validate_company(company):
    company = canonicalize(company)

    hard_failures = []
    warnings = []

    company_name = company.get("company_name")
    source_name = company.get("source_name")
    source_url = company.get("source_url")
    source_evidence = company.get("source_evidence")
    discovery_confidence = as_float(
        company.get("discovery_confidence")
    )

    if not has_value(company_name):
        return company, {
            "status": "REJECTED",
            "reason": "Missing company name.",
            "warnings": [],
            "service_fit": "UNKNOWN",
            "matched_services": [],
            "contact_fields_available": 0,
            "has_scale_signal": False,
            "discovery_confidence": discovery_confidence,
        }

    # Discovery provenance is a trust requirement.
    if not has_value(source_name):
        hard_failures.append("Missing authoritative discovery source.")
    if not has_value(source_url):
        hard_failures.append("Missing authoritative source URL.")
    if not has_value(source_evidence):
        hard_failures.append("Missing source-backed discovery evidence.")
    if discovery_confidence < MIN_DISCOVERY_CONFIDENCE:
        hard_failures.append(
            f"Discovery confidence below {MIN_DISCOVERY_CONFIDENCE:.2f}."
        )

    service_fit, matches = detect_service_fit(company)

    if service_fit == "UNKNOWN":
        warnings.append(
            "No explicit core or adjacent service line detected."
        )

    has_phone = has_value(company.get("phone"))
    has_website = has_value(company.get("website"))
    has_location = has_value(company.get("location"))
    contact_fields = sum([has_phone, has_website, has_location])

    if contact_fields == 0:
        warnings.append("No phone, website, or location available.")

    has_scale_signal = has_value(company.get("size_signal"))
    research_confidence = as_float(
        company.get("research_confidence")
    )

    if not has_scale_signal:
        warnings.append("No verified size/scale signal.")

    if research_confidence == 0:
        warnings.append(
            "Company was not successfully enriched; "
            "original source-backed record retained."
        )

    if hard_failures:
        status = "REJECTED"
        reason = " ".join(hard_failures)
    elif service_fit == "CORE":
        status = "VALIDATED"
        reason = "Passed deterministic validation as a core ICP operator."
    elif service_fit == "ADJACENT":
        status = "REVIEW"
        reason = "Source-backed adjacent operator requires inclusion decision."
    else:
        status = "REVIEW"
        reason = "Source-backed company requires service-fit review."

    validation = {
        "status": status,
        "reason": reason,
        "warnings": warnings,
        "service_fit": service_fit,
        "matched_services": matches,
        "contact_fields_available": contact_fields,
        "has_scale_signal": has_scale_signal,
        "discovery_confidence": discovery_confidence,
    }

    return company, validation


def main():
    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print("DETERMINISTIC COMPANY VALIDATION")
    print("=" * 72)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        payload = json.load(file)

    state = payload.get("state", "UNKNOWN")
    companies = payload.get("companies", [])

    validated = []
    review = []
    rejected = []

    print()
    print(f"State: {state}")
    print(f"Companies received: {len(companies)}")
    print()

    for number, raw_company in enumerate(companies, start=1):
        company, validation = validate_company(raw_company)

        record = dict(company)
        record["validation"] = validation
        status = validation["status"]

        if status == "VALIDATED":
            validated.append(record)
        elif status == "REVIEW":
            review.append(record)
        else:
            rejected.append(record)

        print("-" * 72)
        print(f"{number}. {company.get('company_name', 'UNKNOWN')}")
        print(f"   Status:       {status}")
        print(f"   Service fit:  {validation['service_fit']}")

        matches = validation.get("matched_services", [])
        print(
            f"   Matched:      "
            f"{', '.join(matches) if matches else 'NONE'}"
        )
        print(
            f"   Discovery:    "
            f"{validation.get('discovery_confidence', 0):.2f}"
        )
        print(
            f"   Contacts:     "
            f"{validation.get('contact_fields_available', 0)}/3"
        )
        print(
            f"   Scale signal: "
            f"{validation.get('has_scale_signal', False)}"
        )
        print(f"   Why:          {validation['reason']}")

        for warning in validation["warnings"]:
            print(f"   Warning:      {warning}")

    final_payload = {
        "state": state,
        "companies_received": len(companies),
        "validated_count": len(validated),
        "review_count": len(review),
        "rejected_count": len(rejected),
        "validated": validated,
        "review": review,
        "rejected": rejected,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(final_payload, file, indent=2, ensure_ascii=False)

    print()
    print("=" * 72)
    print("VALIDATION COMPLETE")
    print("=" * 72)
    print()
    print(f"VALIDATED: {len(validated)}")
    print(f"REVIEW:    {len(review)}")
    print(f"REJECTED:  {len(rejected)}")
    print()
    print(f"Saved to: {OUTPUT_FILE}")
    print()


if __name__ == "__main__":
    main()
