"""
collectors/help_forum.py — Indian investing forum collector.
Scrapes TradingQ&A (Zerodha community) and ValuePickr using Discourse JSON search API.
Explicitly targets:
- Survivor & continuer queries ("1 year SIP", "didn't stop SIP in crash", "2 years SIP", "why I kept SIP")
- Frictional stoppages & confusion ("mandate bounce", "XIRR negative", "NAV allocation delay")
- Cross-platform competitor comparisons (Groww, Zerodha Coin, Kuvera, INDmoney, ET Money)
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Set

import requests
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from collectors.base import BaseCollector
from models.schemas import RawItem, SourcePlatform
from collectors.play_store import detect_language


TRADINGQNA_BASE = "https://tradingqna.com"
VALUEPICKR_BASE = "https://forum.valuepickr.com"

FORUM_QUERIES = [
    # Survivorship / Continuation queries (Pointer 3)
    "didn't stop my SIP in the crash",
    "1 year SIP update",
    "2 years of SIP",
    "SIP anniversary",
    "why I kept my SIP",
    "continued SIP during crash",
    "SIP journey update",
    # Stoppage & Frictional triggers
    "stopped SIP",
    "paused SIP",
    "SIP mandate failed",
    "SIP negative returns disappointing",
    "should I continue SIP market crash",
    "NAV units allotment delay",
    "XIRR confusing negative",
    "bank mandate ECS bounce penalty",
    # Competitor & App-specific context
    "Groww SIP experience",
    "Zerodha Coin vs Groww mutual fund",
    "Kuvera vs Groww SIP",
    "INDmoney mutual funds",
    "ET Money SIP",
    "first time mutual fund investor advice",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)",
    "Accept": "application/json",
}


class HelpForumCollector(BaseCollector):
    source_name = "help_forum"

    def __init__(self):
        super().__init__()
        self.collection_stats = {
            "fetched": 0,
            "kept": 0,
            "skipped_too_short": 0,
            "skipped_empty": 0,
            "per_forum": {"tradingqna": 0, "valuepickr": 0},
            "per_lang": {"en": 0, "hi": 0, "hinglish": 0},
        }

    def collect(self, limit: int = 350) -> List[RawItem]:
        """
        Scrape TradingQ&A and ValuePickr Discourse forums via their JSON search endpoints.
        """
        logger.info(f"[help_forum] Scraping investing forums (target limit={limit})...")
        collected_at = datetime.now(timezone.utc).isoformat()
        items: List[RawItem] = []
        seen_urls: Set[str] = set()

        # ── TradingQ&A ────────────────────────────────────────────────────────
        for query in FORUM_QUERIES:
            if len(items) >= limit:
                break
            try:
                tq_items = self._search_discourse(
                    TRADINGQNA_BASE, "tradingqna", query, collected_at, seen_urls, max_per_q=15
                )
                items.extend(tq_items)
                time.sleep(1.2)
            except Exception as exc:
                logger.warning(f"[help_forum] TradingQ&A error for '{query}': {exc}")

        # ── ValuePickr ────────────────────────────────────────────────────────
        for query in FORUM_QUERIES[:12]:
            if len(items) >= limit:
                break
            try:
                vp_items = self._search_discourse(
                    VALUEPICKR_BASE, "valuepickr", query, collected_at, seen_urls, max_per_q=12
                )
                items.extend(vp_items)
                time.sleep(1.2)
            except Exception as exc:
                logger.warning(f"[help_forum] ValuePickr error for '{query}': {exc}")

        items = self.validate(items)
        self.collection_stats["kept"] = len(items)
        logger.info(
            f"[help_forum] Summary: Fetched={self.collection_stats['fetched']}, "
            f"Kept={len(items)}, Skipped(short)={self.collection_stats['skipped_too_short']}, "
            f"Forums={self.collection_stats['per_forum']}"
        )
        return items[:limit]

    def _search_discourse(
        self,
        base_url: str,
        forum_name: str,
        query: str,
        collected_at: str,
        seen_urls: Set[str],
        max_per_q: int = 15,
    ) -> List[RawItem]:
        search_url = f"{base_url}/search.json"
        params = {"q": query}

        resp = requests.get(search_url, headers=HEADERS, params=params, timeout=12)
        if resp.status_code != 200:
            return []

        data = resp.json()
        items: List[RawItem] = []

        # 1. Extract from posts
        for post in data.get("posts", [])[:max_per_q]:
            topic_id = post.get("topic_id", "")
            post_url = f"{base_url}/t/{post.get('topic_slug', 'topic')}/{topic_id}"
            if post_url in seen_urls:
                continue

            text = (post.get("blurb") or "").strip()
            # Clean HTML snippet tags
            text = BeautifulSoup(text, "html.parser").get_text()
            if not text:
                self.collection_stats["skipped_empty"] += 1
                continue
            if len(text) < 35:
                self.collection_stats["skipped_too_short"] += 1
                continue

            seen_urls.add(post_url)
            self.collection_stats["fetched"] += 1
            lang_tag = detect_language(text)
            self.collection_stats["per_lang"][lang_tag] += 1
            self.collection_stats["per_forum"][forum_name] += 1

            items.append(
                RawItem(
                    id=str(uuid.uuid4()),
                    source=SourcePlatform.HELP_FORUM,
                    platform_item_id=str(post.get("id", "")),
                    app_name="TradingQ&A" if forum_name == "tradingqna" else "ValuePickr",
                    text=text[:2000],
                    language=lang_tag,
                    date=post.get("created_at"),
                    upvotes=int(post.get("like_count") or 0),
                    url=post_url,
                    collected_at=collected_at,
                )
            )

        # 2. Extract from topics
        for topic in data.get("topics", [])[:max_per_q]:
            topic_id = topic.get("id", "")
            topic_url = f"{base_url}/t/{topic.get('slug', 'topic')}/{topic_id}"
            if topic_url in seen_urls:
                continue

            title = topic.get("title", "")
            excerpt = topic.get("excerpt") or topic.get("blurb") or ""
            combined = BeautifulSoup(f"{title}. {excerpt}", "html.parser").get_text().strip()

            if len(combined) < 35:
                self.collection_stats["skipped_too_short"] += 1
                continue

            seen_urls.add(topic_url)
            self.collection_stats["fetched"] += 1
            lang_tag = detect_language(combined)
            self.collection_stats["per_lang"][lang_tag] += 1
            self.collection_stats["per_forum"][forum_name] += 1

            items.append(
                RawItem(
                    id=str(uuid.uuid4()),
                    source=SourcePlatform.HELP_FORUM,
                    platform_item_id=str(topic_id),
                    app_name="TradingQ&A" if forum_name == "tradingqna" else "ValuePickr",
                    text=combined[:2000],
                    language=lang_tag,
                    date=topic.get("created_at"),
                    upvotes=int(topic.get("like_count") or 0),
                    url=topic_url,
                    collected_at=collected_at,
                )
            )

        return items
