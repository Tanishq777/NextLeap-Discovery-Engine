"""
collect_genuine_playstore.py — Scrapes authentic, genuine mutual fund & SIP retention reviews
from Google Play Store for Groww and direct competitors (Coin, Kuvera, ET Money, Paytm Money).

Filters out:
- Generic cheerleading / 1-line praise (only ratings 1, 2, 3 stars with >= 50 chars)
- F&O, intraday stock charts, and crypto noise
- Deduplicates against existing items
"""
from __future__ import annotations

import os
import re
import sys
import uuid
import json
import shutil
from datetime import datetime, timezone
from typing import Dict, List, Any

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from google_play_scraper import reviews, Sort
from loguru import logger

import config
from models.schemas import (
    RawItem,
    TaggedItem,
    OpportunityArea,
    Quote,
    SourcePlatform,
    RetentionRisk,
    PatternType,
)
from pipeline.raw_store import RawStore
from pipeline.export_bundle import build_bundle
from pipeline.scorer import RETENTION_RISK_WEIGHTS
from pipeline.clusterer import OPPORTUNITY_RULES

PLAY_APPS = {
    "Groww": "com.nextbillion.groww",
    "Zerodha Coin": "com.zerodha.coin",
    "Kuvera": "com.gooogle.android.kuvera.app",
    "ET Money": "com.smartspends",
    "Paytm Money": "com.paytmmoney",
}

# Strict mutual fund & SIP retention keywords (must have at least one)
MF_MUST_HAVE = [
    r"\b(sip|sips)\b",
    r"\bmutual\s*funds?\b",
    r"\b(mandate|auto-?debit|nach|ecs|autopay)\b",
    r"\b(xirr|cagr|nav)\b",
    r"\b(amc|folio|allotment|installment)\b",
]

# Exclude non-mutual-fund noise (stocks, intraday, options)
NON_MF_EXCLUSIONS = [
    r"\b(mtf|margin\s*trading|square\s*off|take\s*trade|traders?|shares?\s*to\s*sell|scalping)\b",
    r"\b(options?\s*chain|call\s*option|put\s*option|candlestick|intraday|chart\s*reading)\b",
    r"\b(sell\s*order\s*of\s*stocks?|buy\s*order\s*of\s*stocks?)\b",
]

COMPILED_MF = [re.compile(p, re.I) for p in MF_MUST_HAVE]
COMPILED_NON_MF = [re.compile(p, re.I) for p in NON_MF_EXCLUSIONS]


def classify_playstore_review(text: str, score: int) -> Dict[str, Any]:
    """Map review text to opportunity area, SIP status, and drop type."""
    t = text.lower()

    # 1. Check for Rigid Mandate Controls (Missing Pause / Skip)
    if re.search(r"\b(pause|skip|cancel|delete)\b.*(button|option|allow|sips?|installment|month)", t) or \
       re.search(r"\b(tried|unable|cannot)\b.*(skip|pause)\b.*(sip|month)", t) or \
       "no pause button" in t or "skip my sip" in t or "pause sips indefinitely" in t:
        area = "Rigid Mandate Controls (Missing Pause & Skip Affordance)"
        problem_type = "app_confusion"
        trigger = "app_experience"
        sip_status = "cancelled" if "cancel" in t else ("paused" if "pause" in t or "skip" in t else "continuing")
        drop_type = "voluntary" if sip_status in ["cancelled", "paused"] else "unknown"
        risk = RetentionRisk.ALREADY_CHURNED if sip_status in ["cancelled", "paused"] else RetentionRisk.HIGH

    # 2. Check for Bank Bounce / ECS Penalty
    elif re.search(r"\b(bounce|bounced|penalty|charge|charges|fee|fees)\b.*(bank|nach|ecs|debit|insufficient)", t) or \
         re.search(r"\b(mandate\s*fail|failed\s*debit|auto-?debit\s*fail)\b", t):
        area = "Post-Failure Bank Bounce Penalties (ECS / NACH Return Charges)"
        problem_type = "app_confusion"
        trigger = "failed_debit"
        sip_status = "cancelled" if any(w in t for w in ["cancel", "stopped", "delete", "uninstalled"]) else "continuing"
        drop_type = "involuntary" if sip_status == "cancelled" else "unknown"
        risk = RetentionRisk.ALREADY_CHURNED if sip_status == "cancelled" else RetentionRisk.HIGH

    # 3. Check for Return Expectations & Early Portfolio Shock
    elif re.search(r"\b(negative|loss|red|down|crash|dip)\b.*(portfolio|returns?|sip|fund)", t) or \
         re.search(r"\b(profit.*less|fd.*better|zero.*return|disappoint.*return)\b", t):
        area = "Unrealistic Return Expectations & Early Portfolio Shock"
        problem_type = "returns_disappointment"
        trigger = "market_downturn"
        sip_status = "cancelled" if any(w in t for w in ["cancel", "stopped", "pause", "switched"]) else "continuing"
        drop_type = "voluntary" if sip_status == "cancelled" else "unknown"
        risk = RetentionRisk.HIGH

    # 4. Check for Metric Opacity (XIRR, NAV, Units)
    elif re.search(r"\b(xirr|cagr|nav|allotment|cut-?off|units|statement)\b", t):
        area = "Financial Literacy Gap & Metric Opacity"
        problem_type = "lack_of_understanding"
        trigger = "confusion"
        sip_status = "continuing"
        drop_type = "unknown"
        risk = RetentionRisk.MED

    # 5. Check for Trust & Transparency Deficit
    elif re.search(r"\b(cheat|scam|fraud|hidden|blocked|unauthorized|deduct.*without|where.*money)\b", t):
        area = "Trust & Transparency Deficit"
        problem_type = "trust_deficit"
        trigger = "trust"
        sip_status = "cancelled" if any(w in t for w in ["cancel", "delete", "stop", "never"]) else "continuing"
        drop_type = "voluntary" if sip_status == "cancelled" else "unknown"
        risk = RetentionRisk.HIGH

    # 6. Default: App Experience Friction
    else:
        area = "App Experience Friction"
        problem_type = "app_confusion"
        trigger = "app_experience"
        sip_status = "continuing"
        drop_type = "unknown"
        risk = RetentionRisk.MED

    return {
        "primary_area": area,
        "problem_type": problem_type,
        "trigger": trigger,
        "sip_status": sip_status,
        "drop_type": drop_type,
        "risk": risk,
    }


def fetch_genuine_reviews_per_app(max_per_app: int = 15) -> List[Dict[str, Any]]:
    """Scrape and strictly filter genuine reviews across apps."""
    collected = []
    seen_texts = set()

    for app_name, app_id in PLAY_APPS.items():
        app_count = 0
        logger.info(f"[play_store] Scraping {app_name} ({app_id})...")

        for sort_order in [Sort.MOST_RELEVANT, Sort.NEWEST]:
            if app_count >= max_per_app:
                break
            try:
                revs, _ = reviews(app_id, lang="en", country="in", sort=sort_order, count=150)
                for r in revs:
                    if app_count >= max_per_app:
                        break
                    score = r.get("score", 5)
                    text = (r.get("content") or "").strip()

                    # Only ratings 1-3 with meaningful explanation
                    if score > 3 or len(text) < 50:
                        continue

                    # Must have mutual fund / SIP keywords
                    if not any(p.search(text) for p in COMPILED_MF):
                        continue

                    # Exclude pure stock / F&O complaints
                    if any(p.search(text) for p in COMPILED_NON_MF):
                        continue

                    # Extra exclusion of trader phrases
                    if re.search(r"\b(trading\s*experience|chart\s*reading|sell\s*order\s*of\s*stock)\b", text, re.I):
                        continue

                    norm = text.lower().strip()
                    if norm in seen_texts:
                        continue
                    seen_texts.add(norm)

                    review_date = str(r.get("at"))[:10] if r.get("at") else datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    upvotes = r.get("thumbsUpCount", 0)

                    collected.append({
                        "app_name": app_name,
                        "text": text,
                        "score": score,
                        "date": review_date,
                        "upvotes": upvotes,
                        "url": f"https://play.google.com/store/apps/details?id={app_id}&review={r.get('reviewId', '')}",
                    })
                    app_count += 1
            except Exception as e:
                logger.warning(f"Error scraping {app_name}: {e}")

        logger.info(f"[play_store] Kept {app_count} genuine reviews for {app_name}")

    return collected


def run_collection(max_per_app: int = 10):
    """Main workflow to collect, classify, store, and export."""
    store = RawStore(config.DB_PATH)

    # 1. Fetch genuine reviews
    genuine_items = fetch_genuine_reviews_per_app(max_per_app=max_per_app)
    logger.info(f"Total genuine Play Store reviews gathered: {len(genuine_items)}")

    if not genuine_items:
        logger.warning("No reviews fetched.")
        return

    # 2. Get existing texts to avoid duplicates
    existing_texts = set()
    with store._conn() as conn:
        rows = conn.execute("SELECT LOWER(TRIM(text)) as t FROM raw_items").fetchall()
        for r in rows:
            existing_texts.add(r["t"])

    new_raw: List[RawItem] = []
    new_tagged: List[TaggedItem] = []

    for item in genuine_items:
        text = item["text"]
        if text.lower().strip() in existing_texts:
            continue
        existing_texts.add(text.lower().strip())

        classification = classify_playstore_review(text, item["score"])
        raw_id = str(uuid.uuid4())

        raw = RawItem(
            id=raw_id,
            source=SourcePlatform.PLAY_STORE,
            platform_item_id=item["url"],
            app_name=item["app_name"],
            text=text,
            date=item["date"],
            upvotes=item["upvotes"],
            url=item["url"],
            collected_at=datetime.now(timezone.utc).isoformat(),
            is_synthetic=False,
            platform_target="Groww" if item["app_name"] == "Groww" else "competitor",
        )
        new_raw.append(raw)

        tagged = TaggedItem(
            id=str(uuid.uuid4()),
            raw_item_id=raw.id,
            relevant=True,
            on_topic=True,
            retention_relevant=True,
            is_synthetic=False,
            primary_area=classification["primary_area"],
            secondary_areas=[],
            sip_status=classification["sip_status"],
            drop_type=classification["drop_type"],
            problem_types=[classification["problem_type"]],
            lifecycle_stage="mid_4_6m",
            behavioral_signals=["already_paused"] if classification["sip_status"] in ["cancelled", "paused"] else ["seeking_validation"],
            emotional_state="frustrated" if item["score"] == 1 else "anxious",
            trigger_types=[classification["trigger"]],
            retention_risk=classification["risk"],
            pattern_type=PatternType.VOICED,
            assigned_areas=[classification["primary_area"]],
            source_platform=SourcePlatform.PLAY_STORE,
            app_name=item["app_name"],
            date=item["date"],
            upvotes=item["upvotes"],
        )
        new_tagged.append(tagged)

    logger.info(f"Adding {len(new_raw)} newly discovered genuine reviews to the database...")

    # 3. Insert batch
    store.insert_batch(new_raw)
    for t in new_tagged:
        store.insert_tagged_item(t)

    # 4. Rebuild opportunity areas
    import sqlite3
    with store._conn() as conn:
        conn.row_factory = sqlite3.Row
        tagged_rows = conn.execute("SELECT * FROM tagged_items").fetchall()
        raw_rows = {r["id"]: r for r in conn.execute("SELECT * FROM raw_items").fetchall()}

    area_map = {}
    for r in tagged_rows:
        areas = json.loads(r["assigned_areas"] or "[]")
        if not areas and r["primary_area"]:
            areas = [r["primary_area"]]
        for area_name in areas:
            if area_name:
                area_map.setdefault(area_name, []).append(r)

    for area_name, items in area_map.items():
        desc = "Identified mutual fund SIP retention breakdown space."
        for _, _, name, d in OPPORTUNITY_RULES:
            if name == area_name:
                desc = d
                break

        voices = sum(1 for it in items if it["pattern_type"] == "voiced")
        inferred = sum(1 for it in items if it["pattern_type"] == "inferred")
        sev = sum(RETENTION_RISK_WEIGHTS.get(it["retention_risk"], 2.0) for it in items) / len(items)
        abandoned = sum(
            1 for it in items
            if "already_paused" in json.loads(it["behavioral_signals"] or "[]")
            or it["retention_risk"] == "already_churned"
            or it["sip_status"] in ["cancelled", "paused", "lapsed"]
        ) / len(items)
        platforms = {it["source_platform"] for it in items if it["source_platform"]}

        quotes = [
            Quote(
                raw_item_id=it["raw_item_id"],
                text=raw_rows[it["raw_item_id"]]["text"] if it["raw_item_id"] in raw_rows else "",
                source_platform=it["source_platform"] or "play_store",
                upvotes=it["upvotes"] or 0,
                url=raw_rows[it["raw_item_id"]]["url"] if it["raw_item_id"] in raw_rows else "",
            )
            for it in sorted(items, key=lambda x: x["upvotes"] or 0, reverse=True)[:3]
        ]

        opp = OpportunityArea(
            name=area_name,
            description=desc,
            evidence_volume=len(items),
            source_diversity=len(platforms),
            severity_score=round(sev, 2),
            abandonment_rate=round(abandoned, 2),
            voiced_count=voices,
            inferred_count=inferred,
            top_quotes=quotes,
            platform_breakdown={p: sum(1 for it in items if it["source_platform"] == p) for p in platforms},
            cluster_source="playstore_enhanced",
        )
        store.upsert_opportunity_area(opp)

    # 5. Export CSV & JSON
    store.export_csv(config.RAW_CSV_PATH)
    store.export_tagged_json(config.TAGGED_JSON_PATH)
    store.export_opportunity_csv(config.OPPORTUNITY_CSV_PATH)

    # 6. Build bundle and sync everywhere
    build_bundle()
    for dest in [
        os.path.join(config.BASE_DIR, "bundle.json"),
        os.path.join(config.BASE_DIR, "api", "bundle.json"),
        os.path.join(config.BASE_DIR, "api", "data", "bundle.json"),
    ]:
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(os.path.join(config.DATA_DIR, "bundle.json"), dest)
        except Exception as e:
            logger.debug(f"Bundle sync to {dest} note: {e}")

    logger.info("Successfully updated Discovery Engine with genuine Play Store reviews!")


if __name__ == "__main__":
    run_collection(max_per_app=8)
