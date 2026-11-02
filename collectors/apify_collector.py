"""
collectors/apify_collector.py — Industrial Apify reviews collector with local caching.
Supports:
1. Live retrieval from Apify actors (Google Play & App Store).
2. Local caching to avoid burning Apify credits on repeated runs.
3. Global `.env` toggle: `USE_APIFY_CACHE=true/false`.
   - When `USE_APIFY_CACHE=false`: Fetches live from Apify, persists JSON to data/apify_cache/.
   - When `USE_APIFY_CACHE=true`: Reads directly from data/apify_cache/ (zero credits consumed).
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from loguru import logger
from apify_client import ApifyClient

from collectors.base import BaseCollector
from models.schemas import RawItem, SourcePlatform
import config

HINGLISH_KEYWORDS = {
    "kya", "nahi", "nahin", "hoga", "hogi", "hai", "hain", "karu", "kare", "karein",
    "bhai", "paisa", "paise", "rupaye", "rupees", "rok", "band", "mera", "meri",
    "kaise", "hota", "hoti", "acha", "achha", "chahiye", "raha", "rahi", "maine",
    "mujhe", "hum", "sir", "karo", "mat", "kyu", "kyun", "wala", "wali", "pe", "me", "se"
}


def detect_language(text: str) -> str:
    """Detect Hindi (Devanagari), Hinglish, or English."""
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    words = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
    matches = words.intersection(HINGLISH_KEYWORDS)
    if len(matches) >= 2 or (len(words) >= 4 and len(matches) / len(words) >= 0.15):
        return "hinglish"
    return "en"


class ApifyCollector(BaseCollector):
    source_name = "apify"

    PLAY_APPS = {
        "Groww": "com.nextbillion.groww",
        "Zerodha Coin": "com.zerodha.coin",
        "Kuvera": "com.gooogle.android.kuvera.app",
        "INDmoney": "in.indwealth",
        "ET Money": "com.smartspends",
        "Paytm Money": "com.paytmmoney",
        "Angel One": "com.msf.angelmobile",
        "Dhan": "com.dhan.live",
    }

    APP_STORE_APPS = {
        "Groww": "1404871703",
        "Zerodha Coin": "1392212571",
        "Kuvera": "1329700901",
    }

    def __init__(self, token: Optional[str] = None):
        super().__init__()
        self.token = token or config.APIFY_API_TOKEN
        self.use_cache = config.USE_APIFY_CACHE
        self.cache_dir = config.APIFY_CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
        self.client = ApifyClient(self.token) if self.token else None

    def collect(self, limit: Optional[int] = None) -> List[RawItem]:
        """Collect across both Play Store and App Store via Apify or local cache."""
        effective_limit = limit or config.APIFY_MAX_REVIEWS
        items: List[RawItem] = []
        items.extend(self.collect_play_store(limit=effective_limit))
        return self.validate(items)

    def collect_play_store(self, limit: Optional[int] = None) -> List[RawItem]:
        """
        Collect Google Play Store reviews using Apify with local file caching.
        Cache file: data/apify_cache/play_store_reviews.json
        """
        effective_limit = limit or config.APIFY_MAX_REVIEWS
        cache_path = os.path.join(self.cache_dir, "play_store_reviews.json")

        # ── 1. Check Local Cache (if enabled) ──
        if self.use_cache:
            if os.path.exists(cache_path):
                logger.info(f"[apify] [CACHE HIT] USE_APIFY_CACHE=true: Loading from local file: {cache_path}")
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        raw_data = json.load(f)
                    items = self._parse_play_store_items(raw_data)
                    logger.info(f"[apify] Loaded {len(items)} items from local cache (0 Apify credits used).")
                    return items
                except Exception as e:
                    logger.warning(f"[apify] Error reading local cache {cache_path}: {e}. Falling back to live API.")
            else:
                logger.warning(f"[apify] USE_APIFY_CACHE=true but {cache_path} not found. Running live collection.")

        # ── 2. Live Apify Execution ──
        if not self.client:
            logger.error("[apify] APIFY_API_TOKEN not configured in .env or config.py")
            return []

        logger.info(f"[apify] [LIVE RUN] USE_APIFY_CACHE=false: Fetching up to {effective_limit} reviews from Apify API...")
        all_raw_reviews: List[Dict[str, Any]] = []

        per_app_limit = max(50, effective_limit // len(self.PLAY_APPS))

        for app_name, app_id in self.PLAY_APPS.items():
            logger.info(f"[apify] Querying Google Play reviews for {app_name} ({app_id})...")
            app_items: List[Dict[str, Any]] = []

            # 1. Primary high-volume actor: neatrat/google-play-store-reviews-scraper
            try:
                run = self.client.actor("neatrat/google-play-store-reviews-scraper").call(
                    run_input={
                        "appIdOrUrl": app_id,
                        "maxItems": per_app_limit,
                        "sortBy": "mostRelevant",
                    }
                )
                ds_id = getattr(run, "default_dataset_id", None) or (run.get("defaultDatasetId") if isinstance(run, dict) else None)
                if ds_id:
                    fetched = list(self.client.dataset(ds_id).iterate_items())
                    for d in fetched:
                        d["_target_app_name"] = app_name
                    app_items.extend(fetched)
                    logger.info(f"[apify] neatrat actor retrieved {len(fetched)} reviews for {app_name}")
            except Exception as exc:
                logger.warning(f"[apify] Primary neatrat scraper failed for {app_name}: {exc}")

            # 2. Fallback actor: thewolves/google-play-reviews-scraper
            if not app_items:
                try:
                    logger.info(f"[apify] Trying fallback actor thewolves/google-play-reviews-scraper for {app_name}...")
                    run = self.client.actor("thewolves/google-play-reviews-scraper").call(
                        run_input={"appIds": [app_id], "maxItems": per_app_limit}
                    )
                    ds_id = getattr(run, "default_dataset_id", None) or (run.get("defaultDatasetId") if isinstance(run, dict) else None)
                    if ds_id:
                        fetched = list(self.client.dataset(ds_id).iterate_items())
                        for d in fetched:
                            d["_target_app_name"] = app_name
                        app_items.extend(fetched)
                        logger.info(f"[apify] Fallback thewolves retrieved {len(fetched)} reviews for {app_name}")
                except Exception as fb_exc:
                    logger.error(f"[apify] Fallback failed for {app_name}: {fb_exc}")

            all_raw_reviews.extend(app_items)

        # ── 3. Cumulative Merge & Save Raw Response to Local File ──
        existing_cached: List[Dict[str, Any]] = []
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    existing_cached = json.load(f)
            except Exception:
                existing_cached = []

        seen_keys = set()
        merged_reviews: List[Dict[str, Any]] = []
        # Prioritize newly scraped items first, followed by existing items
        for r in all_raw_reviews + existing_cached:
            key = str(r.get("reviewId") or r.get("id") or (r.get("body") or r.get("text") or "")[:100])
            if key and key not in seen_keys:
                seen_keys.add(key)
                merged_reviews.append(r)

        if merged_reviews:
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(merged_reviews, f, indent=2, ensure_ascii=False)
                new_added = len(merged_reviews) - len(existing_cached)
                logger.info(f"[apify] Saved {len(merged_reviews)} cumulative raw reviews to {cache_path} (+{new_added} newly discovered)")
            except Exception as e:
                logger.error(f"[apify] Failed to save cache file {cache_path}: {e}")

        effective_reviews = merged_reviews if merged_reviews else all_raw_reviews
        items = self._parse_play_store_items(effective_reviews)
        logger.info(f"[apify] Parsed {len(items)} valid RawItem records (cumulative total across runs).")
        return items

    def _parse_play_store_items(self, raw_list: List[Dict[str, Any]]) -> List[RawItem]:
        """Convert raw Apify review dictionaries into validated RawItem instances."""
        items: List[RawItem] = []
        collected_at = datetime.now(timezone.utc).isoformat()

        for r in raw_list:
            text = (r.get("body") or r.get("text") or r.get("content") or r.get("review") or "").strip()
            if not text or len(text) < 15:
                continue

            app_name = r.get("_target_app_name") or r.get("appId") or "Groww"
            if "groww" in str(app_name).lower():
                app_name = "Groww"
            elif "coin" in str(app_name).lower():
                app_name = "Zerodha Coin"
            elif "kuvera" in str(app_name).lower():
                app_name = "Kuvera"
            elif "indwealth" in str(app_name).lower() or "indmoney" in str(app_name).lower():
                app_name = "INDmoney"
            elif "smartspends" in str(app_name).lower() or "et" in str(app_name).lower():
                app_name = "ET Money"
            elif "paytm" in str(app_name).lower():
                app_name = "Paytm Money"
            elif "angel" in str(app_name).lower():
                app_name = "Angel One"
            elif "dhan" in str(app_name).lower():
                app_name = "Dhan"

            date_val = r.get("date") or r.get("at")
            date_str = str(date_val) if date_val else None

            lang_tag = r.get("language") or r.get("reviewedIn") or r.get("appLanguage") or detect_language(text)
            if lang_tag not in ("en", "hi", "hinglish"):
                lang_tag = detect_language(text)

            upvotes = 0
            for u_key in ("helpfulCounts", "thumbsUp", "thumbsUpCount"):
                if r.get(u_key) is not None:
                    try:
                        upvotes = int(r.get(u_key))
                        break
                    except (ValueError, TypeError):
                        pass

            item_id = str(r.get("reviewId") or r.get("id") or uuid.uuid4())

            items.append(
                RawItem(
                    id=str(uuid.uuid4()),
                    source=SourcePlatform.PLAY_STORE,
                    platform_item_id=item_id,
                    app_name=app_name,
                    text=text[:2000],
                    language=lang_tag,
                    date=date_str,
                    upvotes=upvotes,
                    url=r.get("url") or f"https://play.google.com/store/apps/details?id={r.get('appId', '')}",
                    collected_at=collected_at,
                    is_synthetic=False,
                    platform_target="Groww" if app_name == "Groww" else "competitor",
                )
            )

        return items
