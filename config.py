import os


MODEL = os.getenv("HAULER_MODEL", "gpt-5.6-luna")
MODE = os.getenv("HAULER_MODE", "demo").strip().lower()

if MODE not in {"demo", "full"}:
    raise ValueError("HAULER_MODE must be 'demo' or 'full'.")


DEMO_SETTINGS = {
    # Source discovery
    "source_target": 8,

    # Company extraction
    "max_extraction_sources": 5,
    "max_companies_per_source": 10,

    # Company research / enrichment
    "max_enrichment_companies": 12,

    # Agent execution controls
    "max_attempts": 2,
    "retry_wait": 15,
    "discovery_timeout": 120,
    "extraction_timeout": 120,
    "enrichment_timeout": 120,

    # Light pacing between calls
    "inter_source_delay": 1,
    "inter_company_delay": 1,
}


FULL_SETTINGS = {
    # Source discovery
    "source_target": 15,

    # Company extraction
    "max_extraction_sources": 10,
    "max_companies_per_source": 25,

    # Company research / enrichment
    "max_enrichment_companies": 50,

    # Agent execution controls
    "max_attempts": 2,
    "retry_wait": 15,
    "discovery_timeout": 180,
    "extraction_timeout": 180,
    "enrichment_timeout": 180,

    # Light pacing between calls
    "inter_source_delay": 1,
    "inter_company_delay": 1,
}


SETTINGS = DEMO_SETTINGS if MODE == "demo" else FULL_SETTINGS
