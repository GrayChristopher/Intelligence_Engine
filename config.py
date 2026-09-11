import os


# =========================================================
# MODE
# =========================================================

MODE = os.getenv(
    "HAULER_MODE",
    "demo",
).lower()

if MODE not in {
    "demo",
    "full",
}:
    raise ValueError(
        "HAULER_MODE must be 'demo' or 'full'."
    )


# =========================================================
# MODEL
# =========================================================

MODEL = "gpt-5.6-luna"


# =========================================================
# DEMO MODE
# =========================================================

DEMO = {
    "source_target": 4,

    "max_extraction_sources": 2,
    "max_companies_per_source": 5,

    "max_enrichment_companies": 5,

    "source_timeout": 90,
    "extraction_timeout": 90,
    "enrichment_timeout": 75,

    "max_attempts": 2,
    "retry_wait": 15,

    "inter_source_delay": 5,
    "inter_company_delay": 5,
}


# =========================================================
# FULL MODE
# =========================================================

FULL = {
    "source_target": 12,

    "max_extraction_sources": 10,
    "max_companies_per_source": 25,

    "max_enrichment_companies": 100,

    "source_timeout": 240,
    "extraction_timeout": 180,
    "enrichment_timeout": 120,

    "max_attempts": 5,
    "retry_wait": 30,

    "inter_source_delay": 10,
    "inter_company_delay": 8,
}


# =========================================================
# ACTIVE CONFIG
# =========================================================

SETTINGS = (
    DEMO
    if MODE == "demo"
    else FULL
)


def print_config():

    print()
    print("=" * 72)
    print(
        f"HAULER INTELLIGENCE ENGINE | "
        f"{MODE.upper()} MODE"
    )
    print("=" * 72)

    print(
        f"Model: {MODEL}"
    )

    print(
        f"Source target: "
        f"{SETTINGS['source_target']}"
    )

    print(
        f"Extraction sources: "
        f"{SETTINGS['max_extraction_sources']}"
    )

    print(
        f"Companies/source: "
        f"{SETTINGS['max_companies_per_source']}"
    )

    print(
        f"Enrichment companies: "
        f"{SETTINGS['max_enrichment_companies']}"
    )

    print()
