"""
pipeline/run_full_scale.py — Orchestrates collection and intelligence extraction at real scale.

Target Execution:
1. Collect at real scale: >=1,500 raw items across 5 balanced channels:
   - Play Store (Groww, Zerodha Coin, Kuvera, INDmoney, ET Money in English + Hindi)
   - App Store (Groww, Zerodha Coin, Kuvera, INDmoney, ET Money via Apple RSS)
   - Help Forums (TradingQ&A + ValuePickr with continuers and competitors)
   - YouTube comments (top personal finance / SIP videos)
   - Reddit (authentic investing discussions covering continuers, stoppers, and confusion)
2. Normalization and deduplication.
3. Classification into 10 brief dimensions with evidence spans and confidence scores.
   Filters to 600–800 relevant items. Balanced per channel.
4. Defensible opportunity scoring with sensitivity analysis.
5. Export Question Bank (105 questions, 25 must-decline).
6. Execute and print complete telemetry report.
"""
from __future__ import annotations

import os
import sys

# Ensure workspace root is in python path
workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

import time
from datetime import datetime

from loguru import logger
from tqdm import tqdm

from collectors.play_store import PlayStoreCollector
from collectors.app_store import AppStoreCollector
from collectors.help_forum import HelpForumCollector
from collectors.youtube import YouTubeCollector
from collectors.reddit import RedditCollector
from collectors.apify_collector import ApifyCollector
from pipeline.normalizer import normalize_items
from pipeline.deduplicator import deduplicate
from pipeline.raw_store import RawStore
from pipeline.tagger import LLMTagger
from pipeline.scorer import score_defensible_opportunity_areas
from pipeline.question_bank import export_question_bank
from pipeline.compute_metrics import print_report
import config


def run_full_scale_collection() -> None:
    logger.info("=" * 70)
    logger.info("  DISCOVERY ENGINE — REAL-SCALE COLLECTION & INTELLIGENCE")
    logger.info(f"  Target: ≥ 1,500 Raw Items  ➔  600–800 Relevant After Classification")
    logger.info(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    store = RawStore()
    existing_hashes = store.get_all_hashes()

    # Step 1: Collect across all 5 channels with balanced targets
    play_collector = ApifyCollector() if (config.APIFY_API_TOKEN or config.USE_APIFY_CACHE) else PlayStoreCollector()
    collectors = [
        ("play_store", play_collector, 450),
        ("app_store", AppStoreCollector(), 380),
        ("help_forum", HelpForumCollector(), 320),
        ("youtube", YouTubeCollector(), 300),
        ("reddit", RedditCollector(), 350),
    ]

    total_inserted = 0
    collection_log: dict = {}

    for name, collector, limit in collectors:
        logger.info(f"\n▶ Collecting from {name} (budget={limit})...")
        try:
            raw = collector.collect(limit=limit)
            logger.info(f"  Fetched: {len(raw)} raw items")

            normalized = normalize_items(raw)
            unique, existing_hashes = deduplicate(normalized, existing_hashes)
            logger.info(f"  After deduplication: {len(unique)} unique items")

            inserted = store.insert_batch(unique)
            total_inserted += inserted
            collection_log[name] = {
                "fetched": len(raw),
                "unique": len(unique),
                "inserted": inserted,
            }
            logger.info(f"  Inserted: {inserted} into SQLite")
        except Exception as e:
            logger.error(f"  Collection failed for {name}: {e}")
            collection_log[name] = {"error": str(e)}

    logger.info(f"\nTotal raw items currently in SQLite: {store.count()}")
    store.export_csv(config.RAW_CSV_PATH)

    # Step 2: Classify all untagged items with the brief-aligned LLMTagger
    untagged = store.get_untagged_items()
    logger.info(f"\n▶ Classifying {len(untagged)} items across brief dimensions...")

    tagger = LLMTagger()
    batch_size = 50
    with tqdm(total=len(untagged), desc="Classifying", unit="item") as pbar:
        for i in range(0, len(untagged), batch_size):
            batch = untagged[i : i + batch_size]
            tagged_batch = []
            for item in batch:
                tagged = tagger.classify_item(item)
                tagged_batch.append(tagged)
                pbar.update(1)
            store.insert_tagged_items_batch(tagged_batch)

    stats = store.get_tagging_stats()
    logger.info(f"\nClassification complete:")
    logger.info(f"  • Total Classified : {stats['total']}")
    logger.info(f"  • Relevant Items   : {stats['relevant']} (Target: 600–800)")
    logger.info(f"  • Continuers Found : {stats['continuers']}")
    logger.info(f"  • Error Rate       : {stats['error_rate']:.1%}")

    store.export_tagged_json(config.TAGGED_JSON_PATH)
    store.export_tagged_csv(config.TAGGED_CSV_PATH)

    # Step 3: Defensible Opportunity Scoring
    logger.info("\n▶ Computing defensible opportunity scores and sensitivity analysis...")
    relevant_items = store.get_relevant_tagged_items()
    raw_texts, raw_urls = store.get_raw_texts_and_urls()

    scored_areas = score_defensible_opportunity_areas(relevant_items, raw_texts, raw_urls)
    for area in scored_areas:
        store.upsert_opportunity_area(area)

    store.export_opportunity_csv(config.OPPORTUNITY_CSV_PATH)
    logger.info(f"Persisted {len(scored_areas)} opportunity areas to SQLite & CSV")

    # Step 4: Export Question Bank
    logger.info("\n▶ Generating Unsure-Moment Question Bank (MVP Golden Eval Set)...")
    q_bank = export_question_bank()

    # Step 5: Print Full Mathematical Telemetry
    logger.info("\n▶ Generating reproducible mathematical telemetry...")
    print_report()


if __name__ == "__main__":
    run_full_scale_collection()
