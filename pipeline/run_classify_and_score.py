"""
pipeline/run_classify_and_score.py — High-Throughput Classification, Defensible Opportunity Scoring & Benchmark Answering.
Classifies all untagged empirical reviews into SQLite, updates opportunity areas, exports CSV/JSON,
and generates benchmark question telemetry.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Any

workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from loguru import logger
from tqdm import tqdm

import config
from models.schemas import RawItem, TaggedItem
from pipeline.raw_store import RawStore
from pipeline.tagger import LLMTagger
from pipeline.scorer import score_defensible_opportunity_areas
from pipeline.export_bundle import build_bundle


def main():
    logger.info("=" * 75)
    logger.info("  DISCOVERY ENGINE — CLASSIFICATION & BENCHMARK INTELLIGENCE")
    logger.info(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 75)

    store = RawStore()
    total_raw = store.count()
    all_raw = store.get_all_raw_items()
    logger.info(f"Total raw items in SQLite to reclassify: {len(all_raw):,}")

    logger.info(f"\n▶ Reclassifying all {len(all_raw):,} items with refined Two-Level filter...")
    with store._conn() as conn:
        conn.execute("DELETE FROM tagged_items")

    tagger = LLMTagger()
    batch_size = 100
    tagged_batch = []
    with tqdm(total=len(all_raw), desc="Classifying", unit="item") as pbar:
        for item in all_raw:
            tagged = tagger.classify_item(item)
            tagged_batch.append(tagged)
            if len(tagged_batch) >= batch_size:
                store.insert_tagged_items_batch(tagged_batch)
                tagged_batch = []
            pbar.update(1)

        if tagged_batch:
            store.insert_tagged_items_batch(tagged_batch)

    stats = store.get_tagging_stats()
    logger.info("\n" + "=" * 75)
    logger.info("  CLASSIFICATION STATISTICS")
    logger.info(f"  • Total Classified : {stats['total']:,}")
    logger.info(f"  • Relevant Items   : {stats['relevant']:,}")
    logger.info(f"  • Continuers Found : {stats['continuers']:,}")
    logger.info(f"  • Error Rate       : {stats['error_rate']:.1%}")
    logger.info("=" * 75)

    # Export tagged CSV and JSON
    store.export_csv(config.RAW_CSV_PATH)
    store.export_tagged_json(config.TAGGED_JSON_PATH)
    store.export_tagged_csv(config.TAGGED_CSV_PATH)
    logger.info(f"Exported {config.TAGGED_JSON_PATH} and {config.TAGGED_CSV_PATH}")

    # Compute Defensible Opportunity Scores
    logger.info("\n▶ Computing defensible opportunity scores across empirical corpus...")
    relevant_items = store.get_relevant_tagged_items()
    raw_texts, raw_urls = store.get_raw_texts_and_urls()

    scored_areas = score_defensible_opportunity_areas(relevant_items, raw_texts, raw_urls)
    for area in scored_areas:
        store.upsert_opportunity_area(area)

    store.export_opportunity_csv(config.OPPORTUNITY_CSV_PATH)
    logger.info(f"Persisted {len(scored_areas)} opportunity areas to SQLite & CSV")

    # Export bundle for Dashboard and Chat API
    logger.info("\n▶ Exporting comprehensive bundle.json...")
    build_bundle()
    bundle_path = os.path.join(config.DATA_DIR, "bundle.json")
    logger.info(f"Bundle successfully exported to: {bundle_path}")

    # Copy bundle to api/bundle.json and api/data/bundle.json if api directory exists
    api_dir = os.path.join(config.BASE_DIR, "api")
    if os.path.exists(api_dir):
        import shutil
        shutil.copyfile(bundle_path, os.path.join(api_dir, "bundle.json"))
        api_data_dir = os.path.join(api_dir, "data")
        os.makedirs(api_data_dir, exist_ok=True)
        shutil.copyfile(bundle_path, os.path.join(api_data_dir, "bundle.json"))
        logger.info(f"Synced bundle to API directory: {os.path.join(api_dir, 'bundle.json')}")

    logger.info("\n" + "=" * 75)
    logger.info("  CLASSIFICATION & SCORING PIPELINE COMPLETE")
    logger.info("=" * 75)


if __name__ == "__main__":
    main()
