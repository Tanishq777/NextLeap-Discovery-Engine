"""
pipeline/run_apify_collection.py — Run Apify Feedback Collection with Local File Caching.
Usage:
    python -m pipeline.run_apify_collection

Features:
- Checks `USE_APIFY_CACHE` from .env:
  - If False: Queries live Apify actor and saves responses to data/apify_cache/
  - If True: Reuses saved local cache file (zero Apify credits used)
- Normalizes and deduplicates newly fetched reviews
- Inserts new items into SQLite RawStore
- Prints before/after corpus quantum
"""
from __future__ import annotations

import os
import sys

# Ensure workspace root is in python path
workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from datetime import datetime
from loguru import logger

from collectors.apify_collector import ApifyCollector
from pipeline.normalizer import normalize_items
from pipeline.deduplicator import deduplicate
from pipeline.raw_store import RawStore
import config


def run_apify_pipeline(limit: Optional[int] = None) -> None:
    effective_limit = limit or config.APIFY_MAX_REVIEWS
    logger.info("=" * 65)
    logger.info("  APIFY DISCOVERY ENGINE — QUANTUM REVIEW INGESTION")
    logger.info(f"  Target Review Limit         : {effective_limit:,}")
    logger.info(f"  Cache Mode (USE_APIFY_CACHE): {config.USE_APIFY_CACHE}")
    logger.info(f"  Cache Directory             : {config.APIFY_CACHE_DIR}")
    logger.info(f"  Token Configured            : {bool(config.APIFY_API_TOKEN)}")
    logger.info(f"  Started                     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 65)

    store = RawStore()
    total_before = store.count()
    existing_hashes = store.get_all_hashes()
    logger.info(f"Current Raw Corpus Volume: {total_before:,} records")

    collector = ApifyCollector()
    raw_items = collector.collect(limit=effective_limit)
    logger.info(f"Retrieved {len(raw_items)} items from Apify Collector")

    if not raw_items:
        logger.warning("No items retrieved. Check Apify API token or cache status.")
        return

    # Normalize & Deduplicate
    normalized = normalize_items(raw_items)
    unique_items, _ = deduplicate(normalized, existing_hashes)
    logger.info(f"Unique items after deduplication: {len(unique_items)}")

    # Ingest into SQLite
    inserted = store.insert_batch(unique_items)
    total_after = store.count()

    logger.info("=" * 65)
    logger.info("  APIFY INGESTION SUMMARY")
    logger.info(f"  Items Processed     : {len(raw_items)}")
    logger.info(f"  New Unique Ingested : {inserted}")
    logger.info(f"  Previous Total      : {total_before}")
    logger.info(f"  New Total Raw Items : {total_after}")
    if config.USE_APIFY_CACHE:
        logger.info("  Cost / Credits      : 0 credits (reused local cache file)")
    else:
        logger.info(f"  Cache Saved To      : {config.APIFY_CACHE_DIR}/play_store_reviews.json")
    logger.info("=" * 65)


if __name__ == "__main__":
    run_apify_pipeline()
