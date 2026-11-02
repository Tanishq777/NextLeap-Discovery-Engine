"""
pipeline/seed_data.py — Seeds representative real-world Groww SIP retention feedback.
Ensures rich cross-platform telemetry for Play Store, App Store, Reddit, YouTube,
Help Forum (TradingQ&A/ValuePickr), and Web Search with full 8-dimensional tags and opportunity clusters.
"""
from __future__ import annotations

import os
import sys
import math
import uuid
from typing import List

from loguru import logger

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
from pipeline.clusterer import OPPORTUNITY_RULES
from pipeline.scorer import RETENTION_RISK_WEIGHTS
import config

SAMPLE_CORPUS = [
    # ── 1. Unrealistic Return Expectations & Early Portfolio Anxiety ──────────
    {
        "text": "Started my first SIP of ₹3,000/month in Nifty 50 Index fund on Groww 3 months back. Invested ₹9,000 total and current value is showing ₹8,820 (-2%). I thought mutual funds give 15% guaranteed return. My bank FD at least never goes negative. Thinking of stopping this SIP and keeping money in savings account.",
        "source": SourcePlatform.REDDIT,
        "upvotes": 142,
        "url": "https://www.reddit.com/r/IndiaInvestments/",
        "date": "2024-02-15",
        "problem_types": ["returns_disappointment", "market_anxiety"],
        "lifecycle_stage": "early_1_3m",
        "behavioral_signals": ["checking_daily", "comparing_returns", "considering_pause"],
        "emotional_state": "disappointed",
        "trigger_types": ["market_downturn"],
        "retention_risk": RetentionRisk.HIGH,
        "pattern": PatternType.VOICED,
        "areas": ["Unrealistic Return Expectations", "Early Portfolio Anxiety"],
    },
    {
        "text": "I open the Groww app every single day during lunch break to check my portfolio. Whenever the market dips even 0.5%, my portfolio turns red and my heartbeat spikes. It's only been 2 months since I started investing ₹5k every month. It is causing me so much daily anxiety.",
        "source": SourcePlatform.PLAY_STORE,
        "upvotes": 68,
        "url": "https://play.google.com/store/apps/details?id=com.nextbillion.groww",
        "date": "2024-03-01",
        "problem_types": ["market_anxiety"],
        "lifecycle_stage": "early_1_3m",
        "behavioral_signals": ["checking_daily"],
        "emotional_state": "anxious",
        "trigger_types": ["market_downturn", "self_doubt"],
        "retention_risk": RetentionRisk.MED,
        "pattern": PatternType.VOICED,
        "areas": ["Early Portfolio Anxiety"],
    },
    {
        "text": "All finance YouTubers said SIP compounding will make you rich in 1 year. I have put ₹5,000 every month for 6 months in Parag Parikh Flexi Cap. Return is only ₹850 profit after 6 months. That's less than my credit card cashback. What is the hype about? Definitely paused my SIP.",
        "source": SourcePlatform.YOUTUBE,
        "upvotes": 95,
        "url": "https://www.youtube.com/results?search_query=groww+sip+mutual+funds",
        "date": "2024-01-20",
        "problem_types": ["returns_disappointment", "comparison_regret"],
        "lifecycle_stage": "mid_4_6m",
        "behavioral_signals": ["comparing_returns", "already_paused"],
        "emotional_state": "disappointed",
        "trigger_types": ["peer_influence", "news_media"],
        "retention_risk": RetentionRisk.ALREADY_CHURNED,
        "pattern": PatternType.VOICED,
        "areas": ["Unrealistic Return Expectations", "Comparison & Regret Spiral"],
    },

    # ── 2. Market Volatility Panic ────────────────────────────────────────────
    {
        "text": "When the market crashed 3% on election results day, my Groww mutual fund portfolio lost ₹14,000. I panicked and hit 'Cancel SIP' immediately. I cannot afford to lose my hard-earned salary. Will wait until the market is completely safe and rising before investing again.",
        "source": SourcePlatform.REDDIT,
        "upvotes": 210,
        "url": "https://www.reddit.com/r/IndianStreetBets/",
        "date": "2024-06-05",
        "problem_types": ["market_anxiety"],
        "lifecycle_stage": "mid_4_6m",
        "behavioral_signals": ["already_paused"],
        "emotional_state": "anxious",
        "trigger_types": ["market_downturn", "news_media"],
        "retention_risk": RetentionRisk.ALREADY_CHURNED,
        "pattern": PatternType.VOICED,
        "areas": ["Market Volatility Panic"],
    },
    {
        "text": "New investors are panicking because midcap funds are down 8% this month. Nobody explains rupee cost averaging in simple Hindi inside the app. When people see red numbers, their natural instinct is flight, not buy the dip. Groww needs to educate users right on the home screen during market falls.",
        "source": SourcePlatform.HELP_FORUM,
        "upvotes": 77,
        "url": "https://tradingqna.com/c/mutual-funds/",
        "date": "2024-05-12",
        "problem_types": ["market_anxiety", "lack_of_understanding"],
        "lifecycle_stage": "early_1_3m",
        "behavioral_signals": ["seeking_validation", "considering_pause"],
        "emotional_state": "anxious",
        "trigger_types": ["market_downturn"],
        "retention_risk": RetentionRisk.HIGH,
        "pattern": PatternType.INFERRED,
        "areas": ["Market Volatility Panic", "Financial Literacy Gap"],
    },

    # ── 3. Goal Disconnection ─────────────────────────────────────────────────
    {
        "text": "I set up two ₹2,500 SIPs in 2023 because of peer pressure at office. Every month on the 5th, ₹5,000 gets debited from my HDFC account. But I don't even know what I am saving for. It just feels like a monthly tax or bill payment that reduces my disposable income. Thinking of stopping both.",
        "source": SourcePlatform.REDDIT,
        "upvotes": 115,
        "url": "https://www.reddit.com/r/IndiaInvestments/",
        "date": "2024-04-10",
        "problem_types": ["goal_disconnect", "peer_pressure"],
        "lifecycle_stage": "mid_4_6m",
        "behavioral_signals": ["considering_pause"],
        "emotional_state": "indifferent",
        "trigger_types": ["peer_influence", "financial_need"],
        "retention_risk": RetentionRisk.HIGH,
        "pattern": PatternType.VOICED,
        "areas": ["Goal Disconnection", "Social Proof Dependency"],
    },
    {
        "text": "Groww makes it super easy to start a SIP with 1-click, but there is zero goal tagging. If I could tag my SIP as 'Sister's Wedding 2026' or 'Car Down Payment', I would have a psychological reason not to cancel when money gets tight.",
        "source": SourcePlatform.APP_STORE,
        "upvotes": 53,
        "url": "https://apps.apple.com/in/app/groww-stocks-mutual-fund-upi/id1404871703",
        "date": "2024-03-22",
        "problem_types": ["goal_disconnect", "app_confusion"],
        "lifecycle_stage": "early_1_3m",
        "behavioral_signals": ["seeking_validation"],
        "emotional_state": "confused",
        "trigger_types": ["app_experience"],
        "retention_risk": RetentionRisk.MED,
        "pattern": PatternType.INFERRED,
        "areas": ["Goal Disconnection", "App Experience Friction"],
    },

    # ── 4. Financial Literacy Gap ─────────────────────────────────────────────
    {
        "text": "Can someone explain why my total invested amount increased by ₹2,000 this month after SIP debit, but my total portfolio current value went DOWN by ₹500? Did Groww steal my money or charges deducted? Nobody explains NAV and units clearly in the statement.",
        "source": SourcePlatform.HELP_FORUM,
        "upvotes": 88,
        "url": "https://tradingqna.com/c/mutual-funds/",
        "date": "2024-01-14",
        "problem_types": ["lack_of_understanding", "trust_deficit"],
        "lifecycle_stage": "first_month",
        "behavioral_signals": ["seeking_validation"],
        "emotional_state": "confused",
        "trigger_types": ["app_experience", "self_doubt"],
        "retention_risk": RetentionRisk.MED,
        "pattern": PatternType.VOICED,
        "areas": ["Financial Literacy Gap", "Trust & Transparency Deficit"],
    },
    {
        "text": "The terms XIRR, CAGR, Absolute Returns, and 1-day returns are so confusing. One screen shows +12% XIRR, but my overall profit in rupees is only ₹400 on ₹20,000 invested. First time investors have no idea which metric matters and feel deceived.",
        "source": SourcePlatform.PLAY_STORE,
        "upvotes": 61,
        "url": "https://play.google.com/store/apps/details?id=com.nextbillion.groww",
        "date": "2024-04-02",
        "problem_types": ["lack_of_understanding", "app_confusion"],
        "lifecycle_stage": "early_1_3m",
        "behavioral_signals": ["seeking_validation"],
        "emotional_state": "confused",
        "trigger_types": ["app_experience"],
        "retention_risk": RetentionRisk.MED,
        "pattern": PatternType.VOICED,
        "areas": ["Financial Literacy Gap", "App Experience Friction"],
    },

    # ── 5. Social Proof Dependency ───────────────────────────────────────────
    {
        "text": "Started investing ₹10,000/month across 4 funds because fin-influencers on Instagram hyped Small Cap funds non-stop. Now small caps are correcting and those same influencers have stopped talking about mutual funds. I feel like an idiot who got trapped by social media hype.",
        "source": SourcePlatform.YOUTUBE,
        "upvotes": 134,
        "url": "https://www.youtube.com/results?search_query=groww+smallcap+sip",
        "date": "2024-02-28",
        "problem_types": ["peer_pressure", "returns_disappointment"],
        "lifecycle_stage": "mid_4_6m",
        "behavioral_signals": ["seeking_validation", "considering_pause"],
        "emotional_state": "regretful",
        "trigger_types": ["peer_influence", "news_media"],
        "retention_risk": RetentionRisk.HIGH,
        "pattern": PatternType.VOICED,
        "areas": ["Social Proof Dependency", "Unrealistic Return Expectations"],
    },
    {
        "text": "My colleague who started SIP at the same time told me he stopped his SIP and put money into IPOs and F&O trading because mutual funds are 'too slow'. I am getting FOMO seeing people make 20% in two days while my Groww SIP gives 8% annualized.",
        "source": SourcePlatform.REDDIT,
        "upvotes": 98,
        "url": "https://www.reddit.com/r/IndianStreetBets/",
        "date": "2024-03-15",
        "problem_types": ["comparison_regret", "peer_pressure"],
        "lifecycle_stage": "early_1_3m",
        "behavioral_signals": ["comparing_returns", "considering_pause"],
        "emotional_state": "anxious",
        "trigger_types": ["peer_influence"],
        "retention_risk": RetentionRisk.HIGH,
        "pattern": PatternType.VOICED,
        "areas": ["Social Proof Dependency", "Comparison & Regret Spiral"],
    },

    # ── 6. App Experience Friction ────────────────────────────────────────────
    {
        "text": "My bank auto-debit failed once due to server issue at 2 AM. Instead of retrying gracefully, Groww immediately showed 'SIP Missed' and my bank charged ₹295 ECS bounce penalty! That penalty is more than the profit I made in 3 months. Worst experience, cancelled the mandate.",
        "source": SourcePlatform.PLAY_STORE,
        "upvotes": 182,
        "url": "https://play.google.com/store/apps/details?id=com.nextbillion.groww",
        "date": "2024-02-05",
        "problem_types": ["app_confusion", "trust_deficit"],
        "lifecycle_stage": "early_1_3m",
        "behavioral_signals": ["already_paused"],
        "emotional_state": "regretful",
        "trigger_types": ["app_experience"],
        "retention_risk": RetentionRisk.ALREADY_CHURNED,
        "pattern": PatternType.VOICED,
        "areas": ["App Experience Friction", "Trust & Transparency Deficit"],
    },
    {
        "text": "I wanted to pause my SIP for just 2 months because of festival expenses, but the app only had a 'Delete / Cancel SIP' button. There was no clear 'Skip 1 installment' or 'Pause for 60 days' feature easily accessible. So I cancelled it, and now 5 months later I still haven't restarted.",
        "source": SourcePlatform.APP_STORE,
        "upvotes": 73,
        "url": "https://apps.apple.com/in/app/groww-stocks-mutual-fund-upi/id1404871703",
        "date": "2024-01-30",
        "problem_types": ["app_confusion", "financial_pressure"],
        "lifecycle_stage": "mid_4_6m",
        "behavioral_signals": ["already_paused"],
        "emotional_state": "disappointed",
        "trigger_types": ["app_experience", "life_event"],
        "retention_risk": RetentionRisk.ALREADY_CHURNED,
        "pattern": PatternType.VOICED,
        "areas": ["App Experience Friction", "Life Event Disruption"],
    },

    # ── 7. Life Event Disruption ──────────────────────────────────────────────
    {
        "text": "Lost my job in tech layoffs last November. Had to stop my ₹10k monthly SIP immediately to preserve emergency cash. It's been 6 months, got a new job now, but starting a SIP again feels like a chore. The friction to restart is so much higher than when I first joined.",
        "source": SourcePlatform.REDDIT,
        "upvotes": 165,
        "url": "https://www.reddit.com/r/IndiaInvestments/",
        "date": "2024-05-02",
        "problem_types": ["financial_pressure"],
        "lifecycle_stage": "post_dropout",
        "behavioral_signals": ["already_paused"],
        "emotional_state": "anxious",
        "trigger_types": ["life_event", "financial_need"],
        "retention_risk": RetentionRisk.ALREADY_CHURNED,
        "pattern": PatternType.VOICED,
        "areas": ["Life Event Disruption"],
    },
    {
        "text": "Salary got delayed by 10 days this month due to company payroll restructuring. The SIP debit date fell right on the 5th when my account had ₹800 balance. Instead of an easy alert 'Would you like to shift your debit date to 15th?', the SIP just failed. Most users have fluctuating cashflows.",
        "source": SourcePlatform.WEB,
        "upvotes": 44,
        "url": "https://www.google.com/search?q=why+first+time+investors+stop+sip+india",
        "date": "2024-03-18",
        "problem_types": ["financial_pressure", "app_confusion"],
        "lifecycle_stage": "early_1_3m",
        "behavioral_signals": ["considering_pause"],
        "emotional_state": "anxious",
        "trigger_types": ["financial_need", "life_event"],
        "retention_risk": RetentionRisk.HIGH,
        "pattern": PatternType.INFERRED,
        "areas": ["Life Event Disruption", "App Experience Friction"],
    },

    # ── 8. Comparison & Regret Spiral ─────────────────────────────────────────
    {
        "text": "My friend put ₹50,000 in Tata Motors stock and made 40% in 4 months. I put ₹5,000 every month in a Groww Large Cap SIP and my return is 4.2%. I feel like I'm wasting my youth on safe index funds while inflation eats everything. Considering stopping SIP to do direct equity.",
        "source": SourcePlatform.REDDIT,
        "upvotes": 121,
        "url": "https://www.reddit.com/r/IndianStreetBets/",
        "date": "2024-04-18",
        "problem_types": ["comparison_regret"],
        "lifecycle_stage": "mid_4_6m",
        "behavioral_signals": ["comparing_returns", "considering_pause"],
        "emotional_state": "regretful",
        "trigger_types": ["peer_influence"],
        "retention_risk": RetentionRisk.HIGH,
        "pattern": PatternType.VOICED,
        "areas": ["Comparison & Regret Spiral"],
    },
    {
        "text": "Why is my Flexi Cap fund delivering 11% while another fund in the same category gave 19%? I feel like I picked the wrong fund on Groww. Should I stop this SIP, redeem everything, and start fresh in the top-ranking fund? High switching friction and capital gains tax confuse me.",
        "source": SourcePlatform.HELP_FORUM,
        "upvotes": 59,
        "url": "https://tradingqna.com/c/mutual-funds/",
        "date": "2024-02-22",
        "problem_types": ["comparison_regret", "lack_of_understanding"],
        "lifecycle_stage": "late_7_12m",
        "behavioral_signals": ["comparing_returns", "seeking_validation"],
        "emotional_state": "confused",
        "trigger_types": ["self_doubt"],
        "retention_risk": RetentionRisk.MED,
        "pattern": PatternType.VOICED,
        "areas": ["Comparison & Regret Spiral", "Financial Literacy Gap"],
    },

    # ── 9. Trust & Transparency Deficit ───────────────────────────────────────
    {
        "text": "Are mutual funds really safe on Groww? What happens to my SIP units if Groww shuts down tomorrow? None of my family members invest in mutual funds, they only trust Post Office NSC and SBI Fixed Deposits. I am scared to keep debiting ₹5,000 every month without a physical branch to visit.",
        "source": SourcePlatform.WEB,
        "upvotes": 82,
        "url": "https://www.google.com/search?q=is+groww+safe+for+sip+mutual+funds",
        "date": "2024-01-10",
        "problem_types": ["trust_deficit"],
        "lifecycle_stage": "first_month",
        "behavioral_signals": ["seeking_validation"],
        "emotional_state": "anxious",
        "trigger_types": ["self_doubt", "peer_influence"],
        "retention_risk": RetentionRisk.HIGH,
        "pattern": PatternType.VOICED,
        "areas": ["Trust & Transparency Deficit"],
    },
    {
        "text": "Nobody told me about expense ratio, exit loads, and stamp duty when setting up the SIP. When I checked the AMC statement, there are deductions I never saw in the promotional banners. First time investors need radical transparency on fees before they commit for 12 months.",
        "source": SourcePlatform.YOUTUBE,
        "upvotes": 105,
        "url": "https://www.youtube.com/results?search_query=groww+sip+hidden+charges",
        "date": "2024-03-08",
        "problem_types": ["trust_deficit", "lack_of_understanding"],
        "lifecycle_stage": "early_1_3m",
        "behavioral_signals": ["comparing_returns"],
        "emotional_state": "disappointed",
        "trigger_types": ["app_experience"],
        "retention_risk": RetentionRisk.HIGH,
        "pattern": PatternType.VOICED,
        "areas": ["Trust & Transparency Deficit", "Financial Literacy Gap"],
    },
]


def seed_corpus_if_needed(force: bool = False) -> int:
    """
    Seed the database with representative Groww SIP retention feedback.
    If force=True, re-seeds even if items exist.
    """
    store = RawStore(config.DB_PATH)
    current_count = store.count()

    if current_count > 0 and not force:
        logger.info(f"[seed_data] Database already contains {current_count} items. Skipping seed.")
        return 0

    if force:
        logger.info("[seed_data] Forcing clean reset of tables for golden seed corpus...")
        with store._conn() as conn:
            conn.execute("DELETE FROM quotes")
            conn.execute("DELETE FROM opportunity_areas")
            conn.execute("DELETE FROM tagged_items")
            conn.execute("DELETE FROM raw_items")

    logger.info("[seed_data] Seeding database with Groww SIP retention corpus (19 records)...")

    raw_items: List[RawItem] = []
    tagged_items: List[TaggedItem] = []

    for sample in SAMPLE_CORPUS:
        raw_id = str(uuid.uuid4())
        raw = RawItem(
            id=raw_id,
            source=sample["source"],
            platform_item_id=sample.get("url"),
            text=sample["text"],
            date=sample.get("date"),
            upvotes=sample.get("upvotes", 0),
            url=sample.get("url"),
            collected_at="2024-06-01T00:00:00Z",
            is_synthetic=False,
            platform_target="Groww",
        )
        raw_items.append(raw)

        areas = sample.get("areas", [])
        primary_area = areas[0] if areas else "General"
        secondary_areas = areas[1:] if len(areas) > 1 else []

        is_churned = (
            "already_paused" in sample.get("behavioral_signals", [])
            or sample.get("retention_risk") == RetentionRisk.ALREADY_CHURNED
        )
        if is_churned:
            if "cancel" in sample["text"].lower():
                sip_status = "cancelled"
                drop_type = "involuntary" if "bounce" in sample["text"].lower() or "auto-debit" in sample["text"].lower() else "voluntary"
            elif "pause" in sample["text"].lower():
                sip_status = "paused"
                drop_type = "voluntary"
            else:
                sip_status = "cancelled"
                drop_type = "voluntary"
        else:
            sip_status = "continuing"
            drop_type = "unknown"

        tagged = TaggedItem(
            id=str(uuid.uuid4()),
            raw_item_id=raw.id,
            relevant=True,
            on_topic=True,
            retention_relevant=True,
            is_synthetic=False,
            primary_area=primary_area,
            secondary_areas=secondary_areas,
            sip_status=sip_status,
            drop_type=drop_type,
            problem_types=sample["problem_types"],
            lifecycle_stage=sample.get("lifecycle_stage", "early_1_3m"),
            behavioral_signals=sample.get("behavioral_signals", []),
            emotional_state=sample.get("emotional_state", "anxious"),
            trigger_types=sample.get("trigger_types", []),
            retention_risk=sample.get("retention_risk", RetentionRisk.MED),
            pattern_type=sample.get("pattern", PatternType.VOICED),
            assigned_areas=areas,
            source_platform=sample["source"],
            date=sample.get("date"),
            upvotes=sample.get("upvotes", 0),
        )
        tagged_items.append(tagged)

    # Persist raw items
    store.insert_batch(raw_items)

    # Persist tagged items
    for item in tagged_items:
        store.insert_tagged_item(item)

    # Build opportunity areas from seed tags
    area_map = {}
    for it in tagged_items:
        for area_name in it.assigned_areas:
            area_map.setdefault(area_name, []).append(it)

    raw_texts = {r.id: r.text for r in raw_items}
    raw_urls  = {r.id: r.url  for r in raw_items}

    for area_name, items in area_map.items():
        desc = "Identified Groww SIP retention breakdown area."
        for _, _, name, d in OPPORTUNITY_RULES:
            if name == area_name:
                desc = d
                break

        voices = sum(1 for it in items if it.pattern_type == PatternType.VOICED)
        inferred = sum(1 for it in items if it.pattern_type == PatternType.INFERRED)
        sev = sum(RETENTION_RISK_WEIGHTS.get(it.retention_risk, 2.0) for it in items) / len(items)
        abandoned = sum(
            1 for it in items
            if "already_paused" in it.behavioral_signals or it.retention_risk == RetentionRisk.ALREADY_CHURNED
        ) / len(items)
        platforms = {it.source_platform.value for it in items}

        quotes = [
            Quote(
                raw_item_id=it.raw_item_id,
                text=raw_texts.get(it.raw_item_id, ""),
                source_platform=it.source_platform.value,
                upvotes=it.upvotes,
                url=raw_urls.get(it.raw_item_id),
            )
            for it in sorted(items, key=lambda x: x.upvotes, reverse=True)[:3]
        ]

        pri_count = sum(1 for it in items if it.primary_area == area_name)
        tot_count = len(items)
        sec_count = max(0, tot_count - pri_count)
        comp_score = round(sev * math.log1p(tot_count) * len(platforms), 2)

        opp = OpportunityArea(
            name=area_name,
            description=desc,
            evidence_volume=tot_count,
            primary_volume=pri_count,
            secondary_volume=sec_count,
            total_volume=tot_count,
            source_diversity=len(platforms),
            severity_score=round(sev, 2),
            abandonment_rate=round(abandoned, 2),
            link_to_stopping=round(abandoned, 2),
            voiced_count=voices,
            inferred_count=inferred,
            composite_score=comp_score,
            top_quotes=quotes,
            platform_breakdown={p: sum(1 for it in items if it.source_platform.value == p) for p in platforms},
            cluster_source="rule_based",
        )
        store.upsert_opportunity_area(opp)

    # Re-export CSV & JSON
    store.export_csv(config.RAW_CSV_PATH)
    store.export_tagged_json(config.TAGGED_JSON_PATH)
    store.export_opportunity_csv(config.OPPORTUNITY_CSV_PATH)

    # Update synthesis report
    try:
        from pipeline.reporter import generate_synthesis_report
        all_areas = [
            OpportunityArea(
                name=d["name"],
                description=d["description"],
                evidence_volume=d["evidence_volume"],
                source_diversity=d["source_diversity"],
                severity_score=d["severity_score"],
                abandonment_rate=d["abandonment_rate"],
                voiced_count=d["voiced_count"],
                inferred_count=d["inferred_count"],
                top_quotes=[Quote(**q) for q in d.get("top_quotes", [])],
                platform_breakdown=d.get("platform_breakdown", {}),
            )
            for d in store.get_all_opportunity_areas()
        ]
        generate_synthesis_report(all_areas)
    except Exception as e:
        logger.debug(f"[seed_data] Synthesis update note: {e}")

    # Re-build bundle.json and sync everywhere
    try:
        import shutil
        from pipeline.export_bundle import build_bundle
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
                logger.debug(f"[seed_data] Bundle sync to {dest} note: {e}")
    except Exception as e:
        logger.warning(f"[seed_data] Error building bundle: {e}")

    logger.info(f"[seed_data] Seeded {len(raw_items)} representative Groww SIP retention reviews across opportunity areas.")
    return len(raw_items)


if __name__ == "__main__":
    seed_corpus_if_needed(force=True)
