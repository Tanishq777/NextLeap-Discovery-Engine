"""
collectors/app_store.py — Apple App Store review collector via official Apple RSS feeds.
Collects reviews at scale across Groww and primary competitors:
- Groww: 1404871703
- Zerodha Coin: 1392892554
- Kuvera: 1329701793
- INDmoney: 1450178837
- ET Money: 1212752482

No fragile third-party scrapers; uses Apple's official JSON customer reviews feed.
Supports language tagging (English, Hindi, Hinglish) and tracks skip reasons.
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

import requests
from loguru import logger

from collectors.base import BaseCollector
from models.schemas import RawItem, SourcePlatform
from collectors.play_store import detect_language


APP_STORE_APPS = {
    "Groww": "1404871703",
    "Zerodha Coin": "1392892554",
    "Kuvera": "1329701793",
    "INDmoney": "1450178837",
    "ET Money": "1212752482",
    "Paytm Money": "1409200845",
    "Angel One": "1060530976",
    "Dhan": "1575318726",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)",
    "Accept": "application/json",
}


class AppStoreCollector(BaseCollector):
    source_name = "app_store"

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

    def collect(self, limit: int = 400) -> List[RawItem]:
        """
        Fetch up to `limit` reviews across Groww and competitors via Apple RSS feeds.
        Pages through the top recent customer reviews.
        """
        per_app_limit = max(40, limit // len(APP_STORE_APPS))
        logger.info(
            f"[app_store] Fetching up to {limit} reviews across {len(APP_STORE_APPS)} apps "
            f"(~{per_app_limit} per app) via Apple RSS..."
        )

        items: List[RawItem] = []
        collected_at = datetime.now(timezone.utc).isoformat()
        seen_ids = set()

        for app_name, app_id in APP_STORE_APPS.items():
            self.collection_stats["per_app"][app_name] = 0
            app_collected = 0

            # Apple RSS allows pages 1 to 10 (each page has up to 50 reviews)
            max_pages = min(6, (per_app_limit // 50) + 2)
            for page in range(1, max_pages + 1):
                if app_collected >= per_app_limit or len(items) >= limit:
                    break

                url = f"https://itunes.apple.com/in/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
                try:
                    resp = requests.get(url, headers=HEADERS, timeout=12)
                    if resp.status_code == 404 or resp.status_code != 200:
                        break

                    data = resp.json()
                    entries = data.get("feed", {}).get("entry", [])
                    if not entries:
                        break

                    # Skip the first entry if it's the app metadata rather than a review
                    for entry in entries:
                        # Reviews typically contain an 'id' dict and 'content' dict
                        review_id = entry.get("id", {}).get("label") or str(uuid.uuid4())
                        if review_id in seen_ids:
                            continue

                        content = entry.get("content", {}).get("label", "")
                        title = entry.get("title", {}).get("label", "")
                        full_text = f"{title}. {content}".strip() if title else content.strip()

                        if not full_text:
                            self.collection_stats["skipped_empty"] += 1
                            continue
                        if len(full_text) < 25:
                            self.collection_stats["skipped_too_short"] += 1
                            continue

                        seen_ids.add(review_id)
                        self.collection_stats["fetched"] += 1

                        # Vote/rating info
                        rating = 0
                        try:
                            rating = int(entry.get("im:rating", {}).get("label", 0))
                        except Exception:
                            pass

                        lang_tag = detect_language(full_text)
                        self.collection_stats["per_lang"][lang_tag] += 1
                        self.collection_stats["per_app"][app_name] += 1
                        app_collected += 1

                        items.append(
                            RawItem(
                                id=str(uuid.uuid4()),
                                source=SourcePlatform.APP_STORE,
                                platform_item_id=str(review_id),
                                app_name=app_name,
                                text=full_text[:2000],
                                language=lang_tag,
                                date=entry.get("updated", {}).get("label"),
                                upvotes=rating,  # Store rating as proxy
                                url=f"https://apps.apple.com/in/app/id{app_id}",
                                collected_at=collected_at,
                            )
                        )

                    time.sleep(0.8)

                except Exception as exc:
                    logger.warning(f"[app_store] Error fetching {app_name} page {page}: {exc}")
                    break

        items = self.validate(items)
        self.collection_stats["kept"] = len(items)
        logger.info(
            f"[app_store] Summary: Fetched={self.collection_stats['fetched']}, "
            f"Kept={len(items)}, Skipped(short)={self.collection_stats['skipped_too_short']}, "
            f"Languages={self.collection_stats['per_lang']}"
        )
        return items[:limit]
