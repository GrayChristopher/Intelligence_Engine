import json
from pathlib import Path


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "enriched_companies.json"
OUTPUT_FILE = DATA_DIR / "validated_companies.json"


# =========================================================
# CONFIG
# =========================================================

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


# =========================================================
# HELPERS
# =========================================================

def normalize(value):

    if value is None:
        return ""

    return str(value).strip().lower()


def has_value(value):

    if value is None:
        return False

    if isinstance(value, list):
        return len(value) > 0

    text = normalize(value)

    return text not in {
        "",
        "unknown",
        "none",
        "null",
        "n/a",
    }


def service_text(company):

    services = company.get(
        "service_lines",
        [],
    )

    return " ".join(
        normalize(service)
        for service in services
    )


def detect_service_fit(company):

    text = service_text(company)

    core_matches = sorted(
        term
        for term in CORE_SERVICE_TERMS
        if term in text
    )

    adjacent_matches = sorted(
        term
        for term in ADJACENT_SERVICE_TERMS
        if term in text
    )

    if core_matches:

        return (
            "CORE",
            core_matches,
        )

    if adjacent_matches:

        return (
            "ADJACENT",
            adjacent_matches,
        )

    return (
        "UNKNOWN",
        [],
    )


# =========================================================
# VALIDATION
# =========================================================

def validate_company(company):

    reasons = []
    warnings = []

    company_name = company.get(
        "company_name"
    )

    discovery_confidence = float(
        company.get(
            "confidence",
            0,
        )
        or 0
    )

    source_name = company.get(
        "source_name"
    )

    source_url = company.get(
        "source_url"
    )

    discovery_evidence = company.get(
        "evidence"
    )

    # -----------------------------------------------------
    # REQUIRED IDENTITY
    # -----------------------------------------------------

    if not has_value(company_name):

        return {
            "status": "REJECTED",
            "reason": "Missing company name.",
            "warnings": [],
            "service_fit": "UNKNOWN",
            "matched_services": [],
        }

    # -----------------------------------------------------
    # AUTHORITATIVE SOURCE
    # -----------------------------------------------------

    if not has_value(source_name):

        reasons.append(
            "Missing authoritative discovery source."
        )

    if not has_value(source_url):

        reasons.append(
            "Missing authoritative source URL."
        )

    if not has_value(discovery_evidence):

        reasons.append(
            "Missing source-backed discovery evidence."
        )

    # -----------------------------------------------------
    # DISCOVERY CONFIDENCE
    # -----------------------------------------------------

    if (
        discovery_confidence
        < MIN_DISCOVERY_CONFIDENCE
    ):

        reasons.append(
            "Discovery confidence below "
            f"{MIN_DISCOVERY_CONFIDENCE:.2f}."
        )

    # -----------------------------------------------------
    # SERVICE FIT
    # -----------------------------------------------------

    service_fit, matches = (
        detect_service_fit(
            company
        )
    )

    if service_fit == "UNKNOWN":

        warnings.append(
            "No explicit core or adjacent "
            "service line detected."
        )

    # -----------------------------------------------------
    # CONTACTABILITY
    # -----------------------------------------------------

    has_phone = has_value(
        company.get("phone")
    )

    has_website = has_value(
        company.get("website")
    )

    has_location = has_value(
        company.get("location")
    )

    contact_fields = sum(
        [
            has_phone,
            has_website,
            has_location,
        ]
    )

    if contact_fields == 0:

        warnings.append(
            "No phone, website, or location available."
        )

    # -----------------------------------------------------
    # RESEARCH / SCALE
    # -----------------------------------------------------

    has_scale_signal = has_value(
        company.get("size_signal")
    )

    research_confidence = float(
        company.get(
            "research_confidence",
            0,
        )
        or 0
    )

    if not has_scale_signal:

        warnings.append(
            "No verified size/scale signal."
        )

    if research_confidence == 0:

        warnings.append(
            "Company was not successfully enriched; "
            "original source-backed record retained."
        )

    # -----------------------------------------------------
    # FINAL STATUS
    # -----------------------------------------------------

    if reasons:

        status = "REJECTED"

    elif service_fit == "CORE":

        status = "VALIDATED"

    elif service_fit == "ADJACENT":

        status = "REVIEW"

    else:

        status = "REVIEW"

    return {
        "status": status,
        "reason": (
            "Passed deterministic validation."
            if not reasons
            else " ".join(reasons)
        ),
        "warnings": warnings,
        "service_fit": service_fit,
        "matched_services": matches,
        "contact_fields_available": contact_fields,
        "has_scale_signal": has_scale_signal,
    }


# =========================================================
# MAIN
# =========================================================

def main():

    print()
    print("=" * 72)
    print("HAULER INTELLIGENCE ENGINE")
    print("DETERMINISTIC COMPANY VALIDATION")
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

    state = payload.get(
        "state",
        "UNKNOWN",
    )

    companies = payload.get(
        "companies",
        [],
    )

    validated = []
    review = []
    rejected = []

    print()
    print(f"State: {state}")
    print(
        f"Companies received: "
        f"{len(companies)}"
    )
    print()

    # =====================================================
    # VALIDATE
    # =====================================================

    for number, company in enumerate(
        companies,
        start=1,
    ):

        validation = validate_company(
            company
        )

        record = dict(company)

        record["validation"] = validation

        status = validation["status"]

        if status == "VALIDATED":

            validated.append(
                record
            )

        elif status == "REVIEW":

            review.append(
                record
            )

        else:

            rejected.append(
                record
            )

        print("-" * 72)

        print(
            f"{number}. "
            f"{company.get('company_name', 'UNKNOWN')}"
        )

        print(
            f"   Status:       "
            f"{status}"
        )

        print(
            f"   Service fit:  "
            f"{validation['service_fit']}"
        )

        matches = validation.get(
            "matched_services",
            [],
        )

        print(
            f"   Matched:      "
            f"{', '.join(matches) if matches else 'NONE'}"
        )

        print(
            f"   Contacts:     "
            f"{validation.get('contact_fields_available', 0)}/3"
        )

        print(
            f"   Scale signal: "
            f"{validation.get('has_scale_signal', False)}"
        )

        if validation["warnings"]:

            for warning in validation[
                "warnings"
            ]:

                print(
                    f"   Warning:      "
                    f"{warning}"
                )

    # =====================================================
    # SAVE
    # =====================================================

    final_payload = {
        "state": state,
        "companies_received": len(
            companies
        ),
        "validated_count": len(
            validated
        ),
        "review_count": len(
            review
        ),
        "rejected_count": len(
            rejected
        ),
        "validated": validated,
        "review": review,
        "rejected": rejected,
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            final_payload,
            file,
            indent=2,
            ensure_ascii=False,
        )

    # =====================================================
    # SUMMARY
    # =====================================================

    print()
    print("=" * 72)
    print("VALIDATION COMPLETE")
    print("=" * 72)

    print()
    print(
        f"VALIDATED: {len(validated)}"
    )

    print(
        f"REVIEW:    {len(review)}"
    )

    print(
        f"REJECTED:  {len(rejected)}"
    )

    print()

    print(
        f"Saved to: {OUTPUT_FILE}"
    )

    print()


if __name__ == "__main__":
    main()
