"""
config.py — Centralised configuration for the Discovery Engine.
All settings are loaded from a .env file via python-dotenv.
Never hardcode credentials here.

LLM Backend: Groq  (fast inference, free tier available)
Embeddings : OpenAI text-embedding-3-small
  NOTE — Groq does not offer an embedding API; OpenAI is used
         only for vector embeddings (Chroma storage, Phase 2).
         All text classification goes through Groq (Phase 3).
"""
from dotenv import load_dotenv
import os

load_dotenv()

def _get_secret(key: str, default: str = "") -> str:
    """Read configuration from environment or Streamlit Cloud secrets."""
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as _st
        if hasattr(_st, "secrets") and key in _st.secrets:
            return str(_st.secrets[key])
    except Exception:
        pass
    return default

# ── API Credentials ──────────────────────────────────────────────────────────
GROQ_API_KEY         = _get_secret("GROQ_API_KEY", "")          # LLM classification
OPENAI_API_KEY       = _get_secret("OPENAI_API_KEY", "")        # Embeddings only
REDDIT_CLIENT_ID     = _get_secret("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = _get_secret("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = _get_secret("REDDIT_USER_AGENT", "discovery-engine/1.0")
YOUTUBE_API_KEY      = _get_secret("YOUTUBE_API_KEY", "")
SERP_API_KEY         = _get_secret("SERP_API_KEY", "")          # optional web search
APIFY_API_TOKEN      = _get_secret("APIFY_API_TOKEN", "")       # Apify scraper token
USE_APIFY_CACHE      = _get_secret("USE_APIFY_CACHE", "false").lower() in ("true", "1", "yes")
APIFY_MAX_REVIEWS    = int(_get_secret("APIFY_MAX_REVIEWS", "1000"))  # Max reviews to fetch from Apify
APIFY_CACHE_DIR      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "apify_cache")

# ── LLM Model (Groq) ─────────────────────────────────────────────────────────
# Primary: qwen/qwen3.8-27b  — high quality, fast inference on Groq
# Fallback: openai/gpt-oss-120b — powerful 120B parameter model
CLASSIFIER_MODEL         = _get_secret("CLASSIFIER_MODEL", "qwen/qwen3.8-27b")
CLASSIFIER_MODEL_FALLBACK = "openai/gpt-oss-120b"
CLASSIFIER_TEMPERATURE   = 0.0      # deterministic JSON output

# ── Embedding Model (OpenAI) ─────────────────────────────────────────────────
EMBEDDING_MODEL      = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536         # text-embedding-3-small output dim
EMBEDDING_BATCH_SIZE = 100          # items per OpenAI embedding API call
CHROMA_COLLECTION    = "feedback_items"
CHROMA_DISTANCE      = "cosine"     # metric for similarity search

# ── Pipeline Settings ────────────────────────────────────────────────────────
BATCH_SIZE        = 20       # items per Groq classification batch
MAX_RETRIES       = 3        # max API retry attempts per item
TARGET_RAW_COUNT     = 1500     # minimum raw items before proceeding to tagging
TARGET_RELEVANT_MIN  = 600      # minimum relevant items after classification
TARGET_RELEVANT_MAX  = 800      # target relevant range

# Per-source collection limits (ensures balanced distribution across channels)
SOURCE_LIMITS = {
    "play_store":  500,
    "app_store":   400,
    "reddit":      350,
    "youtube":     350,
    "help_forum":  350,
    "web":         150,
}

# ── Storage Paths ─────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.path.join(BASE_DIR, "data")
LOGS_DIR     = os.path.join(BASE_DIR, "logs")
REPORTS_DIR  = os.path.join(BASE_DIR, "reports")

DB_PATH              = os.path.join(DATA_DIR, "discovery_engine.db")
CHROMA_PATH          = os.path.join(DATA_DIR, "chroma")
RAW_CSV_PATH         = os.path.join(DATA_DIR, "raw_items.csv")
TAGGED_JSON_PATH     = os.path.join(DATA_DIR, "tagged_items.json")
TAGGED_CSV_PATH      = os.path.join(DATA_DIR, "tagged_items.csv")
OPPORTUNITY_CSV_PATH = os.path.join(DATA_DIR, "opportunity_areas.csv")
SYNTHESIS_REPORT_PATH = os.path.join(REPORTS_DIR, "synthesis_report.md")

# ── Text Quality Filters ──────────────────────────────────────────────────────
MIN_TEXT_LENGTH   = 35    # characters — items shorter than this are discarded
MAX_TEXT_LENGTH   = 2000  # characters — items longer are truncated intelligently

# ── Scraping / Rate Limiting ──────────────────────────────────────────────────
REQUEST_DELAY_MIN = 1.5   # seconds — minimum delay between requests
REQUEST_DELAY_MAX = 3.0   # seconds — maximum delay (random within range)

# ── Ensure directories exist on import ───────────────────────────────────────
for _dir in [DATA_DIR, LOGS_DIR, REPORTS_DIR, APIFY_CACHE_DIR]:
    os.makedirs(_dir, exist_ok=True)
