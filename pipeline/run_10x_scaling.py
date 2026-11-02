"""
pipeline/run_10x_scaling.py — 10x Hybrid Quantum Scaler for Groww SIP Retention Corpus.
Executes consecutive multi-channel runs one-by-one to scale the dataset 10x with high variety:
- Pass 1: Google Play 1-Star & 2-Star Critical Friction Mining (Bank penalties, SIP cancellations, mandate drops)
- Pass 2: Google Play Chronological Real-Time Sweep (Sort: Newest across 8 apps)
- Pass 3: Apple App Store Deep Sweep (Pages 1-10 across 8 apps via Apple RSS)
- Pass 4: Wealth Communities & Subreddits Sweep (Continuers, long-term investors, XIRR debates)
- Pass 5: YouTube Personal Finance Video Comments Sweep (Beginner panic, return expectations)

Aligns all collected data against the 9 core research questions.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Set

workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from loguru import logger
from google_play_scraper import reviews as gp_reviews, Sort
import requests

import config
from models.schemas import RawItem, SourcePlatform
from pipeline.normalizer import normalize_items
from pipeline.deduplicator import deduplicate
from pipeline.raw_store import RawStore
from collectors.play_store import detect_language
from collectors.app_store import AppStoreCollector
from collectors.help_forum import HelpForumCollector
from collectors.youtube import YouTubeCollector

ALL_PLAY_APPS = {
    "Groww": "com.nextbillion.groww",
    "Zerodha Coin": "com.zerodha.coin",
    "Kuvera": "com.gooogle.android.kuvera.app",
    "INDmoney": "in.indwealth",
    "ET Money": "com.smartspends",
    "Paytm Money": "com.paytmmoney",
    "Angel One": "com.msf.angelmobile",
    "Dhan": "com.dhan.live",
}


def merge_and_save_cache(new_raw_items: List[Dict[str, Any]]) -> int:
    """Save raw Play Store review dictionaries cumulatively to data/apify_cache/play_store_reviews.json."""
    cache_path = os.path.join(config.APIFY_CACHE_DIR, "play_store_reviews.json")
    os.makedirs(config.APIFY_CACHE_DIR, exist_ok=True)
    existing: List[Dict[str, Any]] = []
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    seen = set()
    merged = []
    for r in new_raw_items + existing:
        key = str(r.get("reviewId") or r.get("id") or (r.get("content") or r.get("body") or r.get("text") or "")[:100])
        if key and key not in seen:
            seen.add(key)
            merged.append(r)

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False, default=str)

    new_added = len(merged) - len(existing)
    logger.info(f"[cache] Cumulative cache updated: {len(merged)} total reviews (+{new_added} newly added).")
    return new_added


def run_pass_1_negative_friction(store: RawStore, existing_hashes: Set[str], limit_per_app: int = 250) -> Set[str]:
    """Pass 1: Target 1-star and 2-star reviews across all 8 apps (highest retention friction signal)."""
    logger.info("\n" + "=" * 70)
    logger.info("  PASS 1: TARGETED 1-STAR & 2-STAR NEGATIVE FRICTION MINING")
    logger.info(f"  Target: Up to {limit_per_app} 1★/2★ reviews per app across {len(ALL_PLAY_APPS)} apps")
    logger.info("=" * 70)

    raw_items: List[RawItem] = []
    raw_dicts: List[Dict[str, Any]] = []
    collected_at = datetime.now(timezone.utc).isoformat()

    for app_name, app_id in ALL_PLAY_APPS.items():
        logger.info(f"  ▶ Querying 1★ & 2★ reviews for {app_name} ({app_id})...")
        for score in [1, 2]:
            try:
                chunk, _ = gp_reviews(
                    app_id,
                    lang="en",
                    country="in",
                    sort=Sort.NEWEST,
                    filter_score_with=score,
                    count=limit_per_app // 2,
                )
                logger.info(f"    • {score}★: Fetched {len(chunk)} reviews for {app_name}")
                for r in chunk:
                    text = (r.get("content") or "").strip()
                    if not text or len(text) < 20:
                        continue
                    r["_target_app_name"] = app_name
                    raw_dicts.append(r)

                    raw_items.append(
                        RawItem(
                            id=str(uuid.uuid4()),
                            source=SourcePlatform.PLAY_STORE,
                            platform_item_id=str(r.get("reviewId") or ""),
                            app_name=app_name,
                            text=text[:2000],
                            language=detect_language(text),
                            date=r.get("at").isoformat() if r.get("at") else None,
                            upvotes=int(r.get("thumbsUpCount") or 0),
                            url=f"https://play.google.com/store/apps/details?id={app_id}",
                            collected_at=collected_at,
                            is_synthetic=False,
                            platform_target="Groww" if app_name == "Groww" else "competitor",
                        )
                    )
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"    ⚠️ Error on {app_name} {score}★: {e}")

    merge_and_save_cache(raw_dicts)
    normalized = normalize_items(raw_items)
    unique, updated_hashes = deduplicate(normalized, existing_hashes)
    inserted = store.insert_batch(unique)
    logger.info(f"  ✅ Pass 1 Complete: {len(raw_items)} fetched, {len(unique)} unique, {inserted} newly inserted into SQLite.")
    return updated_hashes


def run_pass_2_chronological_newest(store: RawStore, existing_hashes: Set[str], limit_per_app: int = 250) -> Set[str]:
    """Pass 2: Harvest newest chronological reviews across all 8 apps (2024/2026 platform changes)."""
    logger.info("\n" + "=" * 70)
    logger.info("  PASS 2: CHRONOLOGICAL REVIEWS HARVEST (SORT: NEWEST)")
    logger.info(f"  Target: Up to {limit_per_app} latest reviews per app across {len(ALL_PLAY_APPS)} apps")
    logger.info("=" * 70)

    raw_items: List[RawItem] = []
    raw_dicts: List[Dict[str, Any]] = []
    collected_at = datetime.now(timezone.utc).isoformat()

    for app_name, app_id in ALL_PLAY_APPS.items():
        logger.info(f"  ▶ Querying latest chronological reviews for {app_name}...")
        try:
            chunk, _ = gp_reviews(
                app_id,
                lang="en",
                country="in",
                sort=Sort.NEWEST,
                count=limit_per_app,
            )
            logger.info(f"    • Fetched {len(chunk)} latest reviews for {app_name}")
            for r in chunk:
                text = (r.get("content") or "").strip()
                if not text or len(text) < 20:
                    continue
                r["_target_app_name"] = app_name
                raw_dicts.append(r)

                raw_items.append(
                    RawItem(
                        id=str(uuid.uuid4()),
                        source=SourcePlatform.PLAY_STORE,
                        platform_item_id=str(r.get("reviewId") or ""),
                        app_name=app_name,
                        text=text[:2000],
                        language=detect_language(text),
                        date=r.get("at").isoformat() if r.get("at") else None,
                        upvotes=int(r.get("thumbsUpCount") or 0),
                        url=f"https://play.google.com/store/apps/details?id={app_id}",
                        collected_at=collected_at,
                        is_synthetic=False,
                        platform_target="Groww" if app_name == "Groww" else "competitor",
                    )
                )
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"    ⚠️ Error on {app_name}: {e}")

    merge_and_save_cache(raw_dicts)
    normalized = normalize_items(raw_items)
    unique, updated_hashes = deduplicate(normalized, existing_hashes)
    inserted = store.insert_batch(unique)
    logger.info(f"  ✅ Pass 2 Complete: {len(raw_items)} fetched, {len(unique)} unique, {inserted} newly inserted into SQLite.")
    return updated_hashes


def run_pass_3_app_store_sweep(store: RawStore, existing_hashes: Set[str]) -> Set[str]:
    """Pass 3: Deep sweep of Apple App Store across all 8 apps (pages 1-10 via Apple RSS)."""
    logger.info("\n" + "=" * 70)
    logger.info("  PASS 3: APPLE APP STORE 10-PAGE DEEP SWEEP (ALL 8 APPS)")
    logger.info("=" * 70)

    collector = AppStoreCollector()
    raw = collector.collect(limit=1500)
    logger.info(f"  Fetched {len(raw)} App Store reviews across iOS mutual fund apps.")

    normalized = normalize_items(raw)
    unique, updated_hashes = deduplicate(normalized, existing_hashes)
    inserted = store.insert_batch(unique)
    logger.info(f"  ✅ Pass 3 Complete: {len(raw)} fetched, {len(unique)} unique, {inserted} newly inserted into SQLite.")
    return updated_hashes


def run_pass_4_youtube_and_forums(store: RawStore, existing_hashes: Set[str]) -> Set[str]:
    """Pass 4: Financial YouTube comments & community investor forums."""
    logger.info("\n" + "=" * 70)
    logger.info("  PASS 4: FINANCIAL YOUTUBE & INVESTOR FORUMS SWEEP")
    logger.info("=" * 70)

    # 1. YouTube
    yt_collector = YouTubeCollector()
    yt_raw = yt_collector.collect(limit=600)
    logger.info(f"  Fetched {len(yt_raw)} YouTube comments.")
    norm_yt = normalize_items(yt_raw)
    uniq_yt, updated_hashes = deduplicate(norm_yt, existing_hashes)
    ins_yt = store.insert_batch(uniq_yt)
    logger.info(f"  YouTube Ingested: {ins_yt} new items.")

    # 2. Forums
    forum_collector = HelpForumCollector()
    forum_raw = forum_collector.collect(limit=600)
    logger.info(f"  Fetched {len(forum_raw)} forum posts.")
    norm_forum = normalize_items(forum_raw)
    uniq_forum, updated_hashes = deduplicate(norm_forum, updated_hashes)
    ins_forum = store.insert_batch(uniq_forum)
    logger.info(f"  Help Forums Ingested: {ins_forum} new items.")

    return updated_hashes


def main():
    logger.info("=" * 75)
    logger.info("  DISCOVERY ENGINE — 10x QUANTUM SCALING ORCHESTRATION")
    logger.info(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 75)

    store = RawStore()
    total_start = store.count()
    existing_hashes = store.get_all_hashes()
    logger.info(f"Initial Raw Items in Corpus: {total_start:,}")

    # Run each pass sequentially as requested
    existing_hashes = run_pass_1_negative_friction(store, existing_hashes, limit_per_app=300)
    existing_hashes = run_pass_2_chronological_newest(store, existing_hashes, limit_per_app=300)
    existing_hashes = run_pass_3_app_store_sweep(store, existing_hashes)
    existing_hashes = run_pass_4_youtube_and_forums(store, existing_hashes)

    total_end = store.count()
    net_added = total_end - total_start

    logger.info("\n" + "=" * 75)
    logger.info("  10x SCALING RUN COMPLETE — SUMMARY")
    logger.info(f"  Initial Raw Count : {total_start:,}")
    logger.info(f"  New Raw Count     : {total_end:,}")
    logger.info(f"  Net New Added     : +{net_added:,} authentic reviews")
    logger.info(f"  Cache File Saved  : {config.APIFY_CACHE_DIR}/play_store_reviews.json")
    logger.info("=" * 75)


if __name__ == "__main__":
    main()
