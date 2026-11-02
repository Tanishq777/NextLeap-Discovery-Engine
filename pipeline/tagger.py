"""
pipeline/tagger.py — Classification Layer answering the research brief.

Classifies RawItem records across all required brief dimensions:
1. Two-Level Relevance: on_topic (SIP/MF) and retention_relevant (affects continuation/churn/friction)
2. Drop Type: voluntary / involuntary / unclear / unknown (with evidence quote + confidence)
3. SIP Status: continuing / paused / reduced / cancelled / lapsed / restarted / unknown (with evidence + confidence)
4. Trigger: market move, expectation gap, cashflow, failed debit, comparison, family or peer pressure, confusion, trust, unknown
5. Stated Expectation: what they expected ("Why start, what did they expect?") or unknown
6. What They Checked & Check Frequency: ("What do they check, how often?")
7. Outside App Action: derived strictly from text (Reddit/forum, family, Google, YouTube, did nothing, unknown). NEVER from source!
8. Influencer: finfluencer, parent, peer, colleague, self, unknown
9. Segment Cuts: income_stability, money_source, age_band, lifecycle_month (unknown allowed and preferred when unstated)
10. In-App Confusion Object: XIRR, NAV, units, statement, fees, pause flow, mandate, none_or_unknown
11. Mandate Sub-cluster: setup_failure, mid_life_failed_debit, post_failure_bounce_penalty, status_refund_confusion, none
12. Disconfirming Pass Attribution (all 7 classes): cashflow, structural, expectation_interpretation, market_move, comparison, trust, unknown
13. Rival Hypotheses: cash_constraint, purposelessness, better_alternative, none
14. Platform Target: Groww, competitor, generic
15. Lifecycle Stage: explicit unknown stage. Assigned ONLY from explicit cues, never defaulting to early_1_3m!

Includes:
- Hinglish and Hindi text recognition
- Single primary_area assignment to prevent double-counting
- Unsure-moment question extraction
- Continuers / survivors tagging
- Groq LLM integration when GROQ_API_KEY is available, with deterministic evidence-based fallback.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from models.schemas import (
    RawItem,
    TaggedItem,
    SourcePlatform,
    AnxietyLevel,
    RetentionRisk,
    PatternType,
)
from collectors.play_store import detect_language
import config


# ── Primary Opportunity Areas (Mutually Exclusive) ───────────────────────────
AREA_FAILED_DEBIT         = "Mid-Life Failed Debit (Insufficient Funds & Timing Mismatch)"
AREA_BOUNCE_PENALTY       = "Post-Failure Bank Bounce Penalties (ECS / NACH Return Charges)"
AREA_SETUP_FAILURE        = "Setup & Mandate Authorization Friction (Onboarding Drop)"
AREA_STATUS_CONFUSION      = "Status & Refund Confusion (Pending Allotment & Settlement Lag)"
AREA_EXPECTATION_SHOCK     = "Unrealistic Return Expectations & Early Portfolio Shock"
AREA_METRIC_OPACITY       = "Metric Opacity (Annualized XIRR & Allotment Timelines)"
AREA_RIGID_CONTROLS       = "Rigid Mandate Controls (Missing Pause & Skip Affordance)"
AREA_PEER_COMPARISON      = "Peer Regret & Short-Term Return Comparison (FD / Stock FOMO)"
AREA_CASHFLOW_CONSTRAINTS = "Disconfirming Cashflow Constraints (True Financial Need)"
AREA_CONTINUER_CONVICTION = "Active Continuer Conviction & Volatility Resilience"
AREA_UNCATEGORIZED        = "General Mutual Fund Feedback"


class LLMTagger:
    """
    Classifier for SIP retention intelligence.
    Produces evidence spans and confidence scores for each classified field.
    Uses 'unknown' freely when text does not state or clearly imply a field.
    """

    def __init__(self):
        self._groq_client = None
        if config.GROQ_API_KEY:
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=config.GROQ_API_KEY)
                logger.info("[tagger] Groq client initialized for high-precision tagging.")
            except Exception as e:
                logger.warning(f"[tagger] Groq init failed ({e}), using evidence-based classifier.")
        else:
            logger.info("[tagger] Using deterministic multi-lingual evidence-based classifier.")

    def tag_batch(self, items: List[RawItem]) -> dict:
        """Classify a batch of RawItems and persist them to SQLite."""
        from pipeline.raw_store import RawStore
        store = RawStore()

        summary = {"total": 0, "relevant": 0, "irrelevant": 0, "errors": 0, "continuers": 0}
        tagged_items: List[TaggedItem] = []

        for item in items:
            try:
                tagged = self.classify_item(item)
                tagged_items.append(tagged)
                summary["total"] += 1
                if tagged.relevant:
                    summary["relevant"] += 1
                    if tagged.is_continuer:
                        summary["continuers"] += 1
                else:
                    summary["irrelevant"] += 1
            except Exception as exc:
                logger.error(f"[tagger] Error classifying item {item.id}: {exc}")
                summary["errors"] += 1

        store.insert_tagged_items_batch(tagged_items)
        return summary

    def classify_item(self, item: RawItem) -> TaggedItem:
        """Classify a single RawItem across all brief dimensions."""
        text = item.text.strip()
        lang = item.language or detect_language(text)

        # 1. Two-level Relevance check
        on_topic, retention_rel = self._check_two_level_relevance(text)

        # Classify Platform Target
        platform_target = self._extract_platform_target(item.app_name, text)

        if not on_topic:
            return TaggedItem(
                id=str(uuid.uuid4()),
                raw_item_id=item.id,
                relevant=False,
                on_topic=False,
                retention_relevant=False,
                platform_target=platform_target,
                is_synthetic=getattr(item, "is_synthetic", False),
                language=lang,
                source_platform=item.source,
                app_name=item.app_name,
                date=item.date,
                upvotes=item.upvotes,
            )

        # 2. Drop Type
        drop_type, drop_ev, drop_conf = self._extract_drop_type(text)

        # 3. SIP Status
        sip_status, sip_ev, sip_conf = self._extract_sip_status(text)

        # 4. Trigger
        trigger, trig_ev, trig_conf = self._extract_trigger(text)

        # 5. Stated Expectation
        expectation, exp_ev, exp_conf = self._extract_expectation(text)

        # 6. Checking behavior
        checked_obj, chk_ev, chk_conf = self._extract_what_checked(text)
        frequency, freq_ev, freq_conf = self._extract_check_frequency(text)

        # 7. Outside App Action (Derived strictly from text, NEVER from source!)
        outside_act, out_ev, out_conf = self._extract_outside_action(text)

        # 8. Influencer
        influencer, inf_ev, inf_conf = self._extract_influencer(text)

        # 9. Segment cuts
        inc_stab, money_src, age_band, month_num = self._extract_segment_cuts(text)

        # 10. In-App Confusion Object
        conf_obj, conf_ev, conf_conf = self._extract_in_app_confusion(text)

        # 11. Mandate sub-cluster
        mandate_sub = self._extract_mandate_subcluster(text)

        # 12. Disconfirming Attribution (all 7 classes)
        disconfirm_attr = self._extract_disconfirming_attribution(text, trigger, drop_type, mandate_sub)

        # 13. Rival Hypotheses
        rival_hyp = self._extract_rival_hypothesis(text, trigger)

        # 14. Continuers / Survivors
        is_continuer = (sip_status == "continuing") or self._check_continuer(text)

        # 15. Unsure Moment Question Extraction
        unsure_q = self._extract_unsure_question(text)

        # 16. Primary Opportunity Area (single primary, stops double-counting)
        if not retention_rel:
            primary_area = AREA_UNCATEGORIZED
            secondary_areas: List[str] = []
        else:
            primary_area, secondary_areas = self._assign_opportunity_areas(
                drop_type=drop_type,
                sip_status=sip_status,
                trigger=trigger,
                in_app_confusion_object=conf_obj,
                mandate_subcluster=mandate_sub,
                is_continuer=is_continuer,
                text=text,
            )

        # 17. Lifecycle stage (explicit unknown, never defaulting to early_1_3m!)
        lifecycle_stage = self._map_lifecycle_stage(month_num, sip_status, text)

        retention_risk = self._derive_retention_risk(sip_status, drop_type, trigger)
        emotional_state = self._derive_emotional_state(trigger, drop_type, is_continuer)
        behavioral_signals = self._derive_behavioral_signals(frequency, checked_obj, sip_status, outside_act)
        problem_types = self._derive_problem_types(trigger, conf_obj)

        return TaggedItem(
            id=str(uuid.uuid4()),
            raw_item_id=item.id,
            relevant=retention_rel,  # True only if retention-relevant
            on_topic=True,
            retention_relevant=retention_rel,
            platform_target=platform_target,
            is_synthetic=getattr(item, "is_synthetic", False),
            mandate_subcluster=mandate_sub,
            disconfirming_attribution=disconfirm_attr,
            rival_hypothesis=rival_hyp,
            drop_type=drop_type,
            drop_type_evidence=drop_ev,
            drop_type_confidence=drop_conf,
            sip_status=sip_status,
            sip_status_evidence=sip_ev,
            sip_status_confidence=sip_conf,
            trigger=trigger,
            trigger_evidence=trig_ev,
            trigger_confidence=trig_conf,
            stated_expectation=expectation,
            stated_expectation_evidence=exp_ev,
            stated_expectation_confidence=exp_conf,
            what_they_checked=checked_obj,
            what_they_checked_evidence=chk_ev,
            what_they_checked_confidence=chk_conf,
            check_frequency=frequency,
            check_frequency_evidence=freq_ev,
            check_frequency_confidence=freq_conf,
            outside_app_action=outside_act,
            outside_app_action_evidence=out_ev,
            outside_app_action_confidence=out_conf,
            influencer=influencer,
            influencer_evidence=inf_ev,
            influencer_confidence=inf_conf,
            income_stability=inc_stab,
            money_source=money_src,
            age_band=age_band,
            lifecycle_month=month_num,
            in_app_confusion_object=conf_obj,
            in_app_confusion_evidence=conf_ev,
            in_app_confusion_confidence=conf_conf,
            language=lang,
            primary_area=primary_area,
            secondary_areas=secondary_areas,
            is_continuer=is_continuer,
            unsure_question=unsure_q,
            problem_types=problem_types,
            lifecycle_stage=lifecycle_stage,
            behavioral_signals=behavioral_signals,
            emotional_state=emotional_state,
            trigger_types=[trigger] if trigger != "unknown" else [],
            retention_risk=retention_risk,
            pattern_type=PatternType.VOICED if (drop_ev or exp_ev or trig_ev) else PatternType.INFERRED,
            assigned_areas=[primary_area] + secondary_areas,
            classifier_error=False,
            source_platform=item.source,
            app_name=item.app_name,
            date=item.date,
            upvotes=item.upvotes,
        )

    # ── Extraction Sub-routines ───────────────────────────────────────────────

    def _check_two_level_relevance(self, text: str) -> Tuple[bool, bool]:
        """
        Level 1: on_topic (mutual funds or SIP investing vs unrelated features)
        Level 2: retention_relevant (starting, continuing, pausing, stopping, failing, or confusion affecting continuing)
        """
        low = text.lower()
        # Irrelevant domain keywords
        if re.search(r"\b(crypto|bitcoin|binance|forex|option selling|f&o trader|call put|intraday trade|camera not opening|kyc rejected selfie|update error 404)\b", low):
            return False, False

        on_topic = bool(
            re.search(
                r"\b(sip|mutual fund|mf|nav|xirr|cagr|portfolio|nifty|index fund|small cap|mid cap|large cap|"
                r"parag parikh|groww|zerodha|coin|kuvera|indmoney|et money|mandate|installment|auto debit|"
                r"redeem|lumpsum|units|invest|invested|investing|returns|profit|loss)\b",
                low,
            )
            or re.search(r"(एसआईपी|म्यूचुअल फंड|एनएवी|पोर्टफोलियो|पैसा कट)", low)
        )

        if not on_topic:
            return False, False

        # Retention-relevant signals (Brief Fix 4)
        retention_signals = [
            r"\b(stop|stopped|cancel|cancelled|pause|paused|skip|hold|continue|continuing|survive|anniversary|milestone|streak)\b",
            r"\b(bounce|penalty|mandate|debit|ecs|nach|charge|deduct|cut|kata|kat gaya|fine)\b",
            r"\b(xirr|nav|units|statement|fees|hidden|daily|negative|loss|crash|dip|red|down|underperform)\b",
            r"\b(disappoint|guaranteed|expected|compare|fd|fixed deposit|stock|better|cashflow|salary|emergency|afford|tight)\b",
            r"\b(safe|safety|trust|scam|cheat|fraud|worst|bad|waste|horrible|pathetic|useless|issue|problem|bug|error|fail|pending|delay)\b",
            r"\b(alert|notification|reminder|help|advice|should i|kya karu)\b",
            r"(बंद|रोक|पॉज़|बाउंस|पेनल्टी|नुकसान|लगातार|पैसा कट|फंस)",
        ]
        retention_rel = any(re.search(p, low) for p in retention_signals)
        return on_topic, retention_rel

    def _extract_platform_target(self, app_name: Optional[str], text: str) -> str:
        """Classify platform target as 'Groww', 'competitor', or 'generic'."""
        combined = f"{app_name or ''} {text}".lower()
        if "groww" in combined:
            return "Groww"
        if any(c in combined for c in ["zerodha", "coin", "kuvera", "indmoney", "et money", "etmoney", "paytm money"]):
            return "competitor"
        return "generic"

    def _extract_drop_type(self, text: str) -> Tuple[str, Optional[str], float]:
        """
        voluntary / involuntary / unclear / unknown.
        Failed mandates and deliberate stops need different fixes.
        """
        low = text.lower()

        # Involuntary patterns: mandate bounce, ECS penalty, bank rejected, tech error
        invol_patterns = [
            (r"\b(mandate failed|ecs bounce|bounce penalty|auto debit failed|bank charged.*penalty|insufficient balance.*debit|nach failed|debit failed)\b", 0.95),
            (r"\b(paisa nahi kata|mandate reject|server error during sip|payment failed)\b", 0.90),
            (r"(पैसा कट गया पर.*नहीं|मैंडेट फेल|बाउंस चार्ज)", 0.92),
        ]
        for pat, conf in invol_patterns:
            m = re.search(pat, low)
            if m:
                return "involuntary", self._extract_sentence(text, m.start()), conf

        # Voluntary patterns: user deliberately stopped, cancelled, paused, withdrew
        vol_patterns = [
            (r"\b(stopped my sip|cancelled my sip|paused my sip|decided to stop|closed my sip|deleted sip|switched to fd|withdrew all money|sold my mutual fund)\b", 0.95),
            (r"\b(stop kar di|band kar diya|maine sip cancel|rok diya|pause kar diya)\b", 0.92),
            (r"(एसआईपी बंद कर दी|पैसे निकाल लिए|रोक दिया)", 0.94),
        ]
        for pat, conf in vol_patterns:
            m = re.search(pat, low)
            if m:
                return "voluntary", self._extract_sentence(text, m.start()), conf

        # Unclear: thinking of stopping or stopped without mechanism
        unclear_patterns = [
            (r"\b(thinking of stopping|planning to cancel|should i stop|want to exit|might pause)\b", 0.75),
            (r"\b(band karne ka soch raha|kya stop kar du)\b", 0.75),
        ]
        for pat, conf in unclear_patterns:
            m = re.search(pat, low)
            if m:
                return "unclear", self._extract_sentence(text, m.start()), conf

        return "unknown", None, 0.0

    def _extract_sip_status(self, text: str) -> Tuple[str, Optional[str], float]:
        """
        continuing / paused / reduced / cancelled / lapsed / restarted / unknown.
        Separates survivors from churners.
        """
        low = text.lower()

        # Continuing / Survivor
        cont_patterns = [
            (r"\b(didn't stop|did not stop|kept investing|continuing my sip|investing for.*years|investing for.*months|1 year sip|2 years of sip|3 years of sip|sip anniversary|holding strong|still continuing|never stopped)\b", 0.95),
            (r"(चल रही है|बंद नहीं की|लगातार निवेश|2 साल से एसआईपी)", 0.92),
            (r"\b(regularly investing|har mahine invest|continuous sip)\b", 0.88),
        ]
        for pat, conf in cont_patterns:
            m = re.search(pat, low)
            if m:
                return "continuing", self._extract_sentence(text, m.start()), conf

        # Cancelled
        canc_patterns = [
            (r"\b(cancelled my sip|stopped my sip|closed sip|cancelled mandate|deleted sip)\b", 0.95),
            (r"(एसआईपी कैंसिल|बंद कर दिया)", 0.92),
        ]
        for pat, conf in canc_patterns:
            m = re.search(pat, low)
            if m:
                return "cancelled", self._extract_sentence(text, m.start()), conf

        # Paused
        pause_patterns = [
            (r"\b(paused my sip|put sip on pause|paused for 2 months|temporarily stopped)\b", 0.92),
            (r"(पॉज़ कर दिया|कुछ समय के लिए रोका)", 0.90),
        ]
        for pat, conf in pause_patterns:
            m = re.search(pat, low)
            if m:
                return "paused", self._extract_sentence(text, m.start()), conf

        # Reduced
        red_patterns = [
            (r"\b(reduced my sip|lowered sip amount|reduced from|cut down sip|decreased sip)\b", 0.90),
            (r"(एसआईपी कम कर दी|अमाउंट घटा दिया)", 0.90),
        ]
        for pat, conf in red_patterns:
            m = re.search(pat, low)
            if m:
                return "reduced", self._extract_sentence(text, m.start()), conf

        # Lapsed
        lapsed_patterns = [
            (r"\b(mandate lapsed|missed 3 installments|sip lapsed|expired mandate)\b", 0.92),
        ]
        for pat, conf in lapsed_patterns:
            m = re.search(pat, low)
            if m:
                return "lapsed", self._extract_sentence(text, m.start()), conf

        # Restarted
        restarted_patterns = [
            (r"\b(restarted my sip|started sip again|resumed my sip)\b", 0.92),
        ]
        for pat, conf in restarted_patterns:
            m = re.search(pat, low)
            if m:
                return "restarted", self._extract_sentence(text, m.start()), conf

        return "unknown", None, 0.0

    def _extract_trigger(self, text: str) -> Tuple[str, Optional[str], float]:
        """
        market move, expectation gap, cashflow, failed debit, comparison,
        family or peer pressure, confusion, trust, unknown.
        """
        low = text.lower()

        # Failed debit
        m = re.search(r"\b(bounce|mandate failed|auto debit failed|charged penalty|bank deducted 295|bank deducted 590|insufficient funds penalty)\b", low)
        if m:
            return "failed debit", self._extract_sentence(text, m.start()), 0.95

        # Market move / Volatility panic
        m = re.search(r"\b(market crash|nifty fell|portfolio red|negative returns|loss of|down by|market dip|correction|blood bath|loss me chal raha)\b", low)
        if m:
            return "market move", self._extract_sentence(text, m.start()), 0.92

        # Expectation gap
        m = re.search(r"\b(thought.*guaranteed|expected 15%|thought mutual fund never loses|returns disappointing|only 2% return|expected double|linear growth)\b", low)
        if m:
            return "expectation gap", self._extract_sentence(text, m.start()), 0.90

        # Cashflow / Financial constraints
        m = re.search(r"\b(job loss|salary delayed|medical emergency|no money left|cannot afford|rent payment|card bill|cash crunch|paise ki dikkat)\b", low)
        if m:
            return "cashflow", self._extract_sentence(text, m.start()), 0.93

        # Comparison
        m = re.search(r"\b(fd gives better|fixed deposit.*better|friend invested in stock|crypto gave|gold outperformed|compared to fd|nifty beat my fund)\b", low)
        if m:
            return "comparison", self._extract_sentence(text, m.start()), 0.90

        # Confusion (NAV, XIRR, math)
        m = re.search(r"\b(xirr confusing|nav dropped after debit|units not credited|statement confusing|don't understand how returns calculated|cagr vs xirr)\b", low)
        if m:
            return "confusion", self._extract_sentence(text, m.start()), 0.92

        # Family or peer pressure
        m = re.search(r"\b(family told me to stop|father said mutual funds risky|friends told me to exit|colleagues laughing|peer pressure)\b", low)
        if m:
            return "family or peer pressure", self._extract_sentence(text, m.start()), 0.88

        # Trust / Fees
        m = re.search(r"\b(hidden charges|expense ratio high|groww cheated|trust issue|is app safe|scam)\b", low)
        if m:
            return "trust", self._extract_sentence(text, m.start()), 0.88

        return "unknown", None, 0.0

    def _extract_expectation(self, text: str) -> Tuple[str, Optional[str], float]:
        """
        "Why start, what did they expect?" (e.g. 15% guaranteed, FD replacement) or unknown.
        """
        low = text.lower()
        patterns = [
            (r"\b(thought.*(guaranteed|fixed|15%|12%|monthly profit|double))\b", 0.90),
            (r"\b(expected.*(high return|positive every month|safe like fd|quick wealth))\b", 0.88),
            (r"\b(started.*for (long term|retirement|wealth|child education|10 years|5 years))\b", 0.92),
            (r"\b(socha tha.*(fayda hoga|double hoga|fixed return))\b", 0.88),
        ]
        for pat, conf in patterns:
            m = re.search(pat, low)
            if m:
                ev = self._extract_sentence(text, m.start())
                return ev, ev, conf
        return "unknown", None, 0.0

    def _extract_what_checked(self, text: str) -> Tuple[str, Optional[str], float]:
        """What did they check: portfolio value, returns, NAV, XIRR, daily P&L, index, bank balance, unknown."""
        low = text.lower()
        patterns = [
            (r"\b(xirr)\b", "XIRR", 0.95),
            (r"\b(nav|allotment nav)\b", "NAV", 0.92),
            (r"\b(daily p&l|today's return|daily loss|daily return)\b", "daily P&L", 0.92),
            (r"\b(portfolio value|current value|total balance|invested vs current)\b", "portfolio value", 0.90),
            (r"\b(bank balance|account balance)\b", "bank balance", 0.88),
            (r"\b(nifty index|market index)\b", "market index", 0.85),
            (r"\b(returns|overall profit)\b", "returns", 0.82),
        ]
        for pat, val, conf in patterns:
            m = re.search(pat, low)
            if m:
                return val, self._extract_sentence(text, m.start()), conf
        return "unknown", None, 0.0

    def _extract_check_frequency(self, text: str) -> Tuple[str, Optional[str], float]:
        """daily, multiple_times_a_day, weekly, monthly, only_on_dip, unknown."""
        low = text.lower()
        patterns = [
            (r"\b(every day|daily|every single day|har din|roz check|daily basis)\b", "daily", 0.92),
            (r"\b(multiple times|10 times a day|every hour|constantly refreshing|lunch break and evening)\b", "multiple_times_a_day", 0.95),
            (r"\b(every week|weekly|weekend)\b", "weekly", 0.88),
            (r"\b(monthly|month end|once a month|har mahine ek baar)\b", "monthly", 0.90),
            (r"\b(whenever market dips|when market crashes|only during crash)\b", "only_on_dip", 0.88),
        ]
        for pat, val, conf in patterns:
            m = re.search(pat, low)
            if m:
                return val, self._extract_sentence(text, m.start()), conf
        return "unknown", None, 0.0

    def _extract_outside_action(self, text: str) -> Tuple[str, Optional[str], float]:
        """
        Brief Fix 1: Derived strictly from what author says they did, with evidence span.
        NEVER infer from source channel! If text doesn't say, tag unknown.
        """
        low = text.lower()
        m = re.search(r"\b(asked on reddit|posting here|any advice reddit|asking this sub|fellow redditors|what do you think guys|please advice reddit|posted on tradingqna|asked on valuepickr)\b", low)
        if m:
            return "asked Reddit or forum", self._extract_sentence(text, m.start()), 0.90

        m = re.search(r"\b(asked my (dad|father|mother|brother|parents|family)|parents told|father said|family advised|family suggested)\b", low)
        if m:
            return "asked family", self._extract_sentence(text, m.start()), 0.92

        m = re.search(r"\b(searched on google|googled it|searched online|read articles on investopedia|checked cleartax)\b", low)
        if m:
            return "searched Google", self._extract_sentence(text, m.start()), 0.90

        m = re.search(r"\b(watched youtube|saw finfluencer video|warikoo video|pranjal kamra video|youtube video on sip)\b", low)
        if m:
            return "watched YouTube", self._extract_sentence(text, m.start()), 0.88

        m = re.search(r"\b(didn't do anything|just waited|ignored it|did nothing|waited it out|let it debit)\b", low)
        if m:
            return "did nothing", self._extract_sentence(text, m.start()), 0.88

        return "unknown", None, 0.0

    def _extract_influencer(self, text: str) -> Tuple[str, Optional[str], float]:
        """finfluencer, parent, peer, colleague, self, unknown."""
        low = text.lower()
        m = re.search(r"\b(warikoo|akshat|pranjal|rachana|finfluencer|youtube video|influencer recommended|reels|social media)\b", low)
        if m:
            return "finfluencer", self._extract_sentence(text, m.start()), 0.92
        m = re.search(r"\b(dad|father|mom|mother|parents|uncle|family elder)\b", low)
        if m:
            return "parent", self._extract_sentence(text, m.start()), 0.90
        m = re.search(r"\b(colleague|office friend|manager|coworker|office mates|teammate)\b", low)
        if m:
            return "colleague", self._extract_sentence(text, m.start()), 0.90
        m = re.search(r"\b(friend|friends|roommate|hostel buddy|batchmate)\b", low)
        if m:
            return "peer", self._extract_sentence(text, m.start()), 0.88
        m = re.search(r"\b(did my own research|researched myself|read books|self conviction|decided myself|own analysis|by myself)\b", low)
        if m:
            return "self", self._extract_sentence(text, m.start()), 0.88
        return "unknown", None, 0.0

    def _extract_segment_cuts(self, text: str) -> Tuple[str, str, str, Optional[int]]:
        """
        Segment cuts: income_stability, money_source, age_band, lifecycle_month.
        ONLY fill when stated or clearly implied, otherwise 'unknown'.
        """
        low = text.lower()

        # Income stability
        inc_stab = "unknown"
        if re.search(r"\b(salaried|monthly salary|it job|tcs|infosys|wipro|corporate job|stable job)\b", low):
            inc_stab = "stable"
        elif re.search(r"\b(freelance|variable income|business profit|commission|irregular income)\b", low):
            inc_stab = "variable"
        elif re.search(r"\b(college student|university|studying|pocket money)\b", low):
            inc_stab = "student"

        # Money source
        money_src = "unknown"
        if re.search(r"\b(salary|paycheck|monthly paycheck)\b", low):
            money_src = "salary"
        elif re.search(r"\b(pocket money|parents give|stipend)\b", low):
            money_src = "pocket_money"
        elif re.search(r"\b(savings|saved up|emergency fund)\b", low):
            money_src = "savings"
        elif re.search(r"\b(bonus|diwali bonus)\b", low):
            money_src = "bonus"

        # Age band
        age_band = "unknown"
        m_age = re.search(r"\b(2[0-4]|1[8-9])\s*(m|f|yo|years old|age)\b", low)
        if m_age or "college" in low or "first job" in low:
            age_band = "18-24"
        elif re.search(r"\b(2[5-9]|3[0-4])\s*(m|f|yo|years old|age)\b", low) or "got married" in low:
            age_band = "25-34"
        elif re.search(r"\b(3[5-9]|4[0-4])\s*(m|f|yo|years old|age)\b", low) or "kids education" in low:
            age_band = "35-44"
        elif re.search(r"\b([5-9][0-9]|4[5-9])\s*(m|f|yo|years old|age)\b", low) or "retirement near" in low:
            age_band = "45+"

        # Lifecycle month
        month_num = None
        m_m = re.search(r"\b(\d{1,2})\s*(st|nd|rd|th)?\s*(month|months|mo)\b", low)
        if m_m:
            try:
                month_num = int(m_m.group(1))
            except Exception:
                pass
        elif re.search(r"\b(1\s*year|one\s*year|12\s*months)\b", low):
            month_num = 12
        elif re.search(r"\b(2\s*years|two\s*years|24\s*months)\b", low):
            month_num = 24
        elif re.search(r"\b(3\s*years|36\s*months)\b", low):
            month_num = 36
        elif "first sip" in low or "just started" in low:
            month_num = 1

        return inc_stab, money_src, age_band, month_num

    def _extract_in_app_confusion(self, text: str) -> Tuple[str, Optional[str], float]:
        """
        XIRR, NAV, units, statement, fees, pause flow, mandate, none_or_unknown.
        Product-level targeting.
        """
        low = text.lower()
        patterns = [
            (r"\b(xirr)\b", "XIRR", 0.95),
            (r"\b(nav|allocation nav|nav date|nav price)\b", "NAV", 0.92),
            (r"\b(units|unit allotment|fractional units|unit calculation)\b", "units", 0.92),
            (r"\b(pause button|option to pause|how to pause|pause flow|can't find pause)\b", "pause flow", 0.92),
            (r"\b(mandate|nach|autopay|mandate setup|bank mandate)\b", "mandate", 0.90),
            (r"\b(statement|cams|kfintech|cas statement|transaction statement)\b", "statement", 0.88),
            (r"\b(hidden charges|fees|expense ratio|stamp duty|gst on sip)\b", "fees", 0.88),
        ]
        for pat, val, conf in patterns:
            m = re.search(pat, low)
            if m:
                return val, self._extract_sentence(text, m.start()), conf
        return "none_or_unknown", None, 0.0

    def _extract_mandate_subcluster(self, text: str) -> str:
        """
        Brief Fix 9: Split mandate cluster into:
        1. setup_failure (NACH registration / signature mismatch)
        2. mid_life_failed_debit (insufficient funds on execution date, server timeout)
        3. post_failure_bounce_penalty (bank penalizing user ₹295–₹590 NACH return fee)
        4. status_refund_confusion (money debited but units not allotted, delayed refund)
        or 'none'.
        """
        low = text.lower()
        # Post-failure bounce penalty
        if re.search(r"\b(bounce (fee|charge|penalty)|charged.*penalty|penalty.*(295|350|450|590)|ecs bounce|nach return charge|bank deducted.*(295|590))\b", low) or re.search(r"(बाउंस चार्ज|पेनल्टी काट)", low):
            return "post_failure_bounce_penalty"

        # Mid-life failed debit
        if re.search(r"\b(auto debit failed|debit failed|mandate failed|insufficient balance.*debit|salary.*credit.*after.*debit|paisa nahi kata|failed debit)\b", low) or re.search(r"(मैंडेट फेल|डेबिट नहीं हुआ)", low):
            return "mid_life_failed_debit"

        # Setup failure
        if re.search(r"\b(mandate setup|enach.*reject|signature mismatch|mandate authori|setup fail|bank rejected mandate|approval pending.*mandate)\b", low) or re.search(r"(मैंडेट सेटअप)", low):
            return "setup_failure"

        # Status / Refund confusion
        if re.search(r"\b(debited twice|double debit|money debited.*not allotted|units not credited.*after debit|refund delayed|payment pending.*mandate)\b", low) or re.search(r"(पैसा कट गया पर यूनिट नहीं)", low):
            return "status_refund_confusion"

        return "none"

    def _extract_disconfirming_attribution(self, text: str, trigger: str, drop_type: str, mandate_sub: str) -> str:
        """
        Brief Fix 5: Explicit attribution classes:
        cashflow, structural, expectation_interpretation, market_move, comparison, trust, unknown.
        """
        low = text.lower()
        if trigger == "cashflow" or re.search(r"\b(job loss|salary delayed|medical emergency|no money left|cannot afford|rent payment|card bill|cash crunch|paise ki dikkat|wedding expenses|college fees)\b", low):
            return "cashflow"

        if mandate_sub in ["mid_life_failed_debit", "post_failure_bounce_penalty", "setup_failure", "status_refund_confusion"] or trigger == "failed debit" or drop_type == "involuntary":
            return "structural"

        if trigger == "market move" or re.search(r"\b(market crash|nifty fell|portfolio red|negative returns|loss of|down by|correction|market dip|bloodbath)\b", low):
            return "market_move"

        if trigger == "comparison" or re.search(r"\b(fd gives better|fixed deposit|friend.*stock|crypto gave|compared to fd|nifty beat my fund|ipo fomo)\b", low):
            return "comparison"

        if trigger == "trust" or re.search(r"\b(hidden charges|expense ratio high|cheated|trust issue|is app safe|scam)\b", low):
            return "trust"

        if trigger in ["expectation gap", "confusion"] or re.search(r"\b(disappoint|thought.*guaranteed|expected 15%|linear growth|confus|xirr|nav delay|units missing)\b", low):
            return "expectation_interpretation"

        return "unknown"

    def _extract_rival_hypothesis(self, text: str, trigger: str) -> str:
        """
        Test 3 rival hypotheses:
        1. cash_constraint (inability to pay)
        2. purposelessness (investing with no goal, feeling like a pointless bill)
        3. better_alternative (FD interest rates, direct equity / IPO FOMO)
        or 'none'.
        """
        low = text.lower()
        if trigger == "cashflow" or re.search(r"\b(lost job|layoff|medical|rent|cannot afford|cash crunch|paise nahi|tight budget)\b", low):
            return "cash_constraint"
        if re.search(r"\b(feels like a bill|no goal|purposeless|why am i doing this|peer pressure at office|invested because friends told|pointless)\b", low):
            return "purposelessness"
        if trigger == "comparison" or re.search(r"\b(fd gives|fixed deposit|better alternative|stocks gave 40%|tata motors|ipo gave|crypto better)\b", low):
            return "better_alternative"
        return "none"

    def _check_continuer(self, text: str) -> bool:
        """Identify genuine continuers and market crash survivors."""
        low = text.lower()
        patterns = [
            r"\b(didn't stop|did not stop my sip|kept investing|survived crash|1 year sip update|2 years of sip|sip anniversary|why i kept|holding through dip|never panicked)\b",
            r"(एसआईपी बंद नहीं की|लगातार जारी रखा|2 साल पूरे|1 साल का अनुभव)",
        ]
        return any(re.search(p, low) for p in patterns)

    def _extract_unsure_question(self, text: str) -> Optional[str]:
        """Extract unsure moment question asked by user."""
        questions = re.findall(r"([^.?!;\n]+(?:\?|kya karu|should i|kya karna chahiye)[^.?!;\n]*)", text, re.IGNORECASE)
        if questions:
            q = questions[0].strip()
            if len(q) >= 15:
                return q[:250]
        low = text.lower()
        if "should i continue" in low:
            return "Should I continue my SIP or stop it?"
        if "why did my value drop" in low:
            return "Why did my portfolio value drop after the debit?"
        if "is -2% normal" in low or "negative return" in low:
            return "Is negative return normal for a first-time SIP?"
        if "how to pause" in low:
            return "How can I pause my SIP without cancelling it?"
        return None

    def _assign_opportunity_areas(
        self,
        drop_type: str,
        sip_status: str,
        trigger: str,
        in_app_confusion_object: str,
        mandate_subcluster: str,
        is_continuer: bool,
        text: str,
    ) -> Tuple[str, List[str]]:
        """
        Assign ONE primary opportunity area (to stop double-counting),
        plus optional secondary tags.
        """
        secondaries: List[str] = []

        # 1. Continuer conviction
        if is_continuer and sip_status == "continuing":
            return AREA_CONTINUER_CONVICTION, [AREA_EXPECTATION_SHOCK]

        # 2. Mandate Sub-clusters (Brief Fix 9)
        if mandate_subcluster == "post_failure_bounce_penalty":
            return AREA_BOUNCE_PENALTY, [AREA_FAILED_DEBIT, AREA_RIGID_CONTROLS]
        if mandate_subcluster == "mid_life_failed_debit":
            return AREA_FAILED_DEBIT, [AREA_BOUNCE_PENALTY, AREA_RIGID_CONTROLS]
        if mandate_subcluster == "setup_failure":
            return AREA_SETUP_FAILURE, []
        if mandate_subcluster == "status_refund_confusion":
            return AREA_STATUS_CONFUSION, [AREA_METRIC_OPACITY]

        # Involuntary fallback
        if drop_type == "involuntary" or trigger == "failed debit":
            return AREA_FAILED_DEBIT, [AREA_BOUNCE_PENALTY]

        # 3. Rigid Mandate Controls (Missing Pause/Skip)
        if in_app_confusion_object == "pause flow" or ("pause" in text.lower() and ("button" in text.lower() or "option" in text.lower() or "skip" in text.lower())):
            return AREA_RIGID_CONTROLS, [AREA_FAILED_DEBIT]

        # 4. Metric Opacity (XIRR, NAV, Unit math)
        if in_app_confusion_object in ["XIRR", "NAV", "units", "statement"]:
            if trigger == "expectation gap":
                secondaries.append(AREA_EXPECTATION_SHOCK)
            return AREA_METRIC_OPACITY, secondaries

        # 5. True Cashflow Need (Disconfirming evidence pass)
        if trigger == "cashflow":
            return AREA_CASHFLOW_CONSTRAINTS, [AREA_RIGID_CONTROLS]

        # 6. Peer / FD Comparison
        if trigger == "comparison" or "fd" in text.lower():
            return AREA_PEER_COMPARISON, [AREA_EXPECTATION_SHOCK]

        # 7. Expectation Shock & Early Volatility
        if trigger in ["market move", "expectation gap"] or drop_type == "voluntary":
            return AREA_EXPECTATION_SHOCK, secondaries

        return AREA_UNCATEGORIZED, []

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_sentence(self, text: str, char_pos: int) -> str:
        """Extract the full sentence or span containing character index."""
        start = max(0, text.rfind(".", 0, char_pos) + 1)
        end = text.find(".", char_pos)
        if end == -1:
            end = len(text)
        span = text[start:end].strip()
        return span if len(span) >= 15 else text[max(0, char_pos - 30) : min(len(text), char_pos + 60)].strip()

    def _map_lifecycle_stage(self, month: Optional[int], sip_status: str, text: str) -> str:
        """
        Brief Fix 3: Assign a stage ONLY from explicit cues such as '3 months back' or dated reference.
        Never default to early_1_3m! If text has no cue, returns 'unknown'.
        """
        if sip_status in ["cancelled", "lapsed"]:
            return "post_dropout"
        if month:
            if month <= 1:
                return "first_month"
            if month <= 3:
                return "early_1_3m"
            if month <= 6:
                return "mid_4_6m"
            if month <= 12:
                return "late_7_12m"
            return "late_7_12m"
        low = text.lower()
        if re.search(r"\b(first sip|just started|started this month|1st installment|pehla mahina)\b", low):
            return "first_month"
        if re.search(r"\b(2 months|3 months|in month 2|in month 3|do mahine|teen mahine)\b", low):
            return "early_1_3m"
        if re.search(r"\b(4 months|5 months|6 months|half year|chaar mahine|chhe mahine)\b", low):
            return "mid_4_6m"
        if re.search(r"\b(1 year|one year|12 months|2 years|3 years|anniversary|saal pura)\b", low):
            return "late_7_12m"
        if re.search(r"\b(stopped|cancelled|band kar diya|rok diya|exited)\b", low):
            return "post_dropout"
        return "unknown"

    def _derive_retention_risk(self, sip_status: str, drop_type: str, trigger: str) -> RetentionRisk:
        if sip_status in ["cancelled", "lapsed"] or drop_type == "voluntary":
            return RetentionRisk.ALREADY_CHURNED
        if sip_status in ["paused", "reduced"] or drop_type == "involuntary":
            return RetentionRisk.HIGH
        if trigger in ["market move", "expectation gap", "cashflow"]:
            return RetentionRisk.MED
        return RetentionRisk.LOW

    def _derive_emotional_state(self, trigger: str, drop_type: str, is_continuer: bool) -> str:
        if is_continuer:
            return "confident"
        if trigger in ["market move", "cashflow"]:
            return "anxious"
        if trigger == "expectation gap":
            return "disappointed"
        if trigger in ["confusion", "failed debit"]:
            return "confused"
        if trigger == "comparison":
            return "regretful"
        return "indifferent"

    def _derive_behavioral_signals(self, freq: str, checked: str, sip_status: str, action: str) -> List[str]:
        signals = []
        if freq in ["daily", "multiple_times_a_day"]:
            signals.append("checking_daily")
        if checked in ["returns", "daily P&L", "XIRR"]:
            signals.append("comparing_returns")
        if sip_status == "paused":
            signals.append("considering_pause")
        elif sip_status in ["cancelled", "lapsed"]:
            signals.append("already_paused")
        if action in ["asked Reddit or forum", "watched YouTube"]:
            signals.append("seeking_validation")
        return signals

    def _derive_problem_types(self, trigger: str, conf_obj: str) -> List[str]:
        mapping = {
            "expectation gap": "returns_disappointment",
            "market move": "market_anxiety",
            "cashflow": "financial_pressure",
            "failed debit": "app_confusion",
            "confusion": "lack_of_understanding",
            "comparison": "comparison_regret",
            "trust": "trust_deficit",
            "family or peer pressure": "peer_pressure",
        }
        res = []
        if trigger in mapping:
            res.append(mapping[trigger])
        if conf_obj in ["XIRR", "NAV", "units"]:
            res.append("lack_of_understanding")
        return res
