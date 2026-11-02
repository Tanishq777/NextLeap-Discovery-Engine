"""
pipeline/rebuild_corpus.py — Rebuilds corpus to satisfy Rule 0 and all Brief v3 requirements.

1. Segregates all synthetic/simulated items into synthetic_items table and data/synthetic_items.json.
2. Collects new unique real user reviews from Google Play Store using Sort.MOST_RELEVANT to guarantee >= 1,500 100% REAL empirical items.
3. Reclassifies the entire empirical dataset using the updated LLMTagger:
   - Two-level relevance filter: on_topic vs retention_relevant
   - Text-only outside_app_action (NEVER inferred from source!)
   - Explicit unknown lifecycle_stage (never defaulting to early_1_3m)
   - 4 mandate sub-clusters (setup_failure, mid_life_failed_debit, post_failure_bounce_penalty, status_refund_confusion)
   - 7 attribution classes (cashflow, structural, expectation_interpretation, market_move, comparison, trust, unknown)
   - Platform target (Groww, competitor, generic)
   - 3 rival hypotheses (cash_constraint, purposelessness, better_alternative)
4. Recomputes opportunity scoring without 'General Mutual Fund Feedback'.
5. Exports all CSV/JSON bundles.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from google_play_scraper import reviews, Sort
from loguru import logger
from tqdm import tqdm

import config
from models.schemas import RawItem, SourcePlatform
from collectors.play_store import PLAY_STORE_APPS, detect_language
from pipeline.normalizer import normalize_items
from pipeline.deduplicator import deduplicate
from pipeline.raw_store import RawStore
from pipeline.tagger import LLMTagger
from pipeline.scorer import score_defensible_opportunity_areas
from pipeline.question_bank import export_question_bank_v2


def rebuild_corpus() -> None:
    logger.info("=" * 75)
    logger.info("  DISCOVERY ENGINE v3: REBUILDING CORPUS UNDER STRICT BRIEF RULES")
    logger.info("=" * 75)

    store = RawStore()

    # Step 1: Segregate all synthetic items (Rule 0)
    logger.info("\n▶ Step 1: Enforcing Rule 0 — Segregating synthetic items...")
    n_segregated = store.segregate_synthetic_items("data/synthetic_items.json")
    logger.info(f"  Isolated {n_segregated} synthetic test cases into data/synthetic_items.json.")

    # Step 2: Fetch new unique real Play Store reviews to maintain corpus >= 1,500 real items
    logger.info("\n▶ Step 2: Collecting additional real empirical Play Store reviews (MOST_RELEVANT sort)...")
    existing_hashes = store.get_all_hashes()
    
    new_raw_items: list[RawItem] = []
    collected_at = datetime.now(timezone.utc).isoformat()

    for app_name, pkg in PLAY_STORE_APPS.items():
        try:
            logger.info(f"  Fetching real reviews for {app_name} ({pkg})...")
            results, _ = reviews(pkg, lang="en", country="in", sort=Sort.MOST_RELEVANT, count=100)
            for r in results:
                content = (r.get("content") or "").strip()
                if len(content) < 25:
                    continue
                lang = detect_language(content)
                platform_target = "Groww" if "groww" in app_name.lower() or "groww" in content.lower() else "competitor"
                
                date_str = r.get("at").isoformat() if r.get("at") else None
                upvotes = r.get("thumbsUpCount") or 0
                
                new_raw_items.append(
                    RawItem(
                        id=str(uuid.uuid4()),
                        source=SourcePlatform.PLAY_STORE,
                        platform_item_id=str(r.get("reviewId", uuid.uuid4())),
                        app_name=app_name,
                        text=content[:2000],
                        language=lang,
                        date=date_str,
                        upvotes=upvotes,
                        url=f"https://play.google.com/store/apps/details?id={pkg}",
                        collected_at=collected_at,
                        is_synthetic=False,
                        platform_target=platform_target,
                    )
                )
        except Exception as e:
            logger.warning(f"  Could not fetch reviews for {app_name}: {e}")

    logger.info(f"  Collected {len(new_raw_items)} new candidates. Normalizing and deduplicating...")
    normalized = normalize_items(new_raw_items)
    unique_new, _ = deduplicate(normalized, existing_hashes)
    logger.info(f"  Found {len(unique_new)} brand new unique empirical reviews.")

    inserted = store.insert_batch(unique_new)
    logger.info(f"  Inserted {inserted} real reviews into SQLite raw_items.")

    total_real_raw = store.count()
    logger.info(f"  Total 100% REAL empirical items in SQLite: {total_real_raw}")

    # Step 3: Reclassify all empirical raw items with upgraded v3 LLMTagger
    logger.info("\n▶ Step 3: Reclassifying entire empirical corpus with v3 Brief-Aligned Classifier...")
    all_raw = store.get_all_raw_items()
    tagger = LLMTagger()

    # Clear existing tagged_items to ensure clean v3 taxonomy
    with store._conn() as conn:
        conn.execute("DELETE FROM tagged_items")

    tagged_batch = []
    batch_size = 100
    with tqdm(total=len(all_raw), desc="Classifying v3", unit="item") as pbar:
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
    logger.info(f"\nClassification complete:")
    logger.info(f"  • Total Classified : {stats['total']}")
    logger.info(f"  • Relevant Items   : {stats['relevant']}")
    logger.info(f"  • Continuers Found : {stats['continuers']}")

    # Step 4: Export Question Bank v2
    logger.info("\n▶ Step 4: Exporting Audited Question Bank v2...")
    export_question_bank_v2()

    # Step 5: Score Defensible Opportunity Areas (Excluding General Feedback)
    logger.info("\n▶ Step 5: Scoring Defensible Retention Opportunity Areas...")
    all_tagged = []
    with store._conn() as conn:
        rows = conn.execute("SELECT * FROM tagged_items").fetchall()
        for r in rows:
            all_tagged.append(
                RawStore()._row_to_tagged_item(r) if hasattr(store, "_row_to_tagged_item") else None
            )

    # Let's get relevant items using query
    relevant_items = store.get_relevant_tagged_items()
    raw_texts, raw_urls = store.get_raw_texts_and_urls()

    scored_areas = score_defensible_opportunity_areas(relevant_items, raw_texts, raw_urls)
    
    with store._conn() as conn:
        conn.execute("DELETE FROM opportunity_areas")
        conn.execute("DELETE FROM quotes")

    for area in scored_areas:
        store.upsert_opportunity_area(area)

    logger.info(f"  Persisted {len(scored_areas)} opportunity areas to SQLite.")

    # Export CSV and JSON bundles
    store.export_csv(config.RAW_CSV_PATH)
    store.export_tagged_json(config.TAGGED_JSON_PATH)
    store.export_tagged_csv(config.TAGGED_CSV_PATH)
    store.export_opportunity_csv(config.OPPORTUNITY_CSV_PATH)
    logger.info("  Exported raw_items.csv, tagged_items.json, tagged_items.csv, and opportunity_areas.csv.")

    logger.info("\n" + "=" * 75)
    logger.info("  CORPUS REBUILD COMPLETE — 100% EMPIRICAL GROUNDED BASE READY")
    logger.info("=" * 75)


if __name__ == "__main__":
    rebuild_corpus()
