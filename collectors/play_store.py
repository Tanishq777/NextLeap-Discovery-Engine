"""
collectors/play_store.py — Google Play Store review collector.
Collects reviews at scale across Groww and primary competitors:
- Groww: com.nextbillion.groww
- Zerodha Coin: com.zerodha.coin
- Kuvera: com.gooogle.android.kuvera.app
- INDmoney: in.indwealth
- ET Money: com.smartspends

Supports English and Hindi text, tags Hinglish, and logs skip reasons.
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from collectors.base import BaseCollector
from models.schemas import RawItem, SourcePlatform
import config


PLAY_STORE_APPS = {
    "Groww": "com.nextbillion.groww",
    "Zerodha Coin": "com.zerodha.coin",
    "Kuvera": "com.gooogle.android.kuvera.app",
    "INDmoney": "in.indwealth",
    "ET Money": "com.smartspends",
    "Paytm Money": "com.paytmmoney",
    "Angel One": "com.msf.angelmobile",
    "Dhan": "com.dhan.live",
}

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


class PlayStoreCollector(BaseCollector):
    source_name = "play_store"

    def __init__(self):
        super().__init__()
        self.collection_stats = {
            "fetched": 0,
            "kept": 0,
            "skipped_too_short": 0,
            "skipped_empty": 0,
            "per_app": {},
            "per_lang": {"en": 0, "hi": 0, "hinglish": 0},
        }

    def collect(self, limit: int = 500) -> List[RawItem]:
        """
        Fetch up to `limit` reviews across Groww and competitors in English & Hindi.
        Allocates quota across apps to ensure sample diversity.
        """
        try:
            from google_play_scraper import reviews, Sort
        except ImportError:
            logger.error("google-play-scraper not installed. Run: pip install google-play-scraper")
            return []

        per_app_limit = max(50, limit // len(PLAY_STORE_APPS))
        logger.info(
            f"[play_store] Collecting up to {limit} reviews across {len(PLAY_STORE_APPS)} apps "
            f"(~{per_app_limit} per app)..."
        )

        items: List[RawItem] = []
        collected_at = datetime.now(timezone.utc).isoformat()

        for app_name, app_id in PLAY_STORE_APPS.items():
            self.collection_stats["per_app"][app_name] = 0
            # Collect both English and Hindi reviews
            for lang in ["en", "hi"]:
                try:
                    fetch_count = per_app_limit // 2 if lang == "hi" else per_app_limit
                    raw_reviews, _ = self._fetch_reviews_with_retry(
                        app_id=app_id,
                        lang=lang,
                        count=fetch_count,
                    )
                    self.collection_stats["fetched"] += len(raw_reviews)

                    for r in raw_reviews:
                        text = (r.get("content") or "").strip()
                        if not text:
                            self.collection_stats["skipped_empty"] += 1
                            continue
                        if len(text) < 25:
                            self.collection_stats["skipped_too_short"] += 1
                            continue

                        text = text[:2000]
                        date_val = r.get("at")
                        date_str = date_val.isoformat() if date_val else None
                        lang_tag = detect_language(text)

                        self.collection_stats["per_lang"][lang_tag] += 1
                        self.collection_stats["per_app"][app_name] += 1

                        items.append(
                            RawItem(
                                id=str(uuid.uuid4()),
                                source=SourcePlatform.PLAY_STORE,
                                platform_item_id=str(r.get("reviewId") or ""),
                                app_name=app_name,
                                text=text,
                                language=lang_tag,
                                date=date_str,
                                upvotes=int(r.get("thumbsUpCount") or 0),
                                url=f"https://play.google.com/store/apps/details?id={app_id}",
                                collected_at=collected_at,
                            )
                        )

                    time.sleep(1.0)  # Polite delay between store calls

                except Exception as exc:
                    logger.warning(f"[play_store] Failed to fetch {app_name} ({lang}): {exc}")

        items = self.validate(items)
        self.collection_stats["kept"] = len(items)
        logger.info(
            f"[play_store] Collection summary: Fetched={self.collection_stats['fetched']}, "
            f"Kept={len(items)}, Skipped(short)={self.collection_stats['skipped_too_short']}, "
            f"Languages={self.collection_stats['per_lang']}"
        )
        return items[:limit]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=2, max=15),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _fetch_reviews_with_retry(self, app_id: str, lang: str, count: int):
        from google_play_scraper import reviews, Sort
        return reviews(
            app_id,
            lang=lang,
            country="in",
            sort=Sort.NEWEST,
            count=count,
            filter_score_with=None,
        )
