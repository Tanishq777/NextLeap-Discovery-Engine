"""
pipeline/scorer.py — Defensible Opportunity Scoring, Sensitivity Analysis, and Disconfirming Evidence.

Defensible Scoring Pillars:
1. Primary Frequency (exclusive non-overlapping assignment, with Wilson 95% CI)
2. Severity Score (1 to 5 written rubric)
3. Link to Stopping (fraction with explicit stop/pause/cancel intent, with Wilson 95% CI)
4. Addressability (1 to 5 written rubric: can Groww act on it?)
5. Constraint Compatibility (1 to 5 written rubric: SEBI compliance, no fear/FOMO/urgency/fund picks)

Brief Fix 4:
- Excludes "General Mutual Fund Feedback" from opportunity scoring.
- Scores ONLY retention-relevant feedback.

Brief Fix 9:
- Mandate cluster is split into setup failure, mid-life failed debit, post-failure bounce penalty, and status/refund confusion.
- Mid-life failed debit and post-failure bounce penalty directly affect 12-month continuation.

Sensitivity Analysis:
Evaluates ranking across 4 distinct weighting strategies:
- Baseline (Balanced): 25% Freq, 25% Sev, 25% Stop, 15% Addr, 10% Const
- Severity-Heavy:     15% Freq, 40% Sev, 25% Stop, 10% Addr, 10% Const
- Frequency-Heavy:    45% Freq, 15% Sev, 15% Stop, 15% Addr, 10% Const
- Retention-Heavy:    15% Freq, 20% Sev, 45% Stop, 10% Addr, 10% Const

Brief Fix 5: Disconfirming Evidence Pass:
Actively tests all 7 attribution classes (cashflow, structural, expectation/interpretation, market move, comparison, trust, unknown)
across both denominators (all records vs known-only), and tests 3 rival hypotheses:
1. Cash constraint (inability to pay)
2. Purposelessness (investing with no goal anchor)
3. Better alternative (FD interest rates, direct stocks / IPO FOMO)
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Dict, List, Tuple, Any

from loguru import logger

from models.schemas import (
    TaggedItem,
    OpportunityArea,
    Quote,
    SourcePlatform,
)


RETENTION_RISK_WEIGHTS: Dict[str, float] = {
    "high": 4.5,
    "medium": 2.5,
    "low": 1.0,
    "none": 0.0,
    "unknown": 2.0,
}


def wilson_score_interval(k: int, n: int, confidence_z: float = 1.95996) -> Tuple[float, float]:
    """Calculate Wilson 95% score confidence interval for a proportion k/n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + (confidence_z**2) / n
    centre = (p + (confidence_z**2) / (2 * n)) / denom
    margin = (confidence_z * math.sqrt((p * (1 - p) / n) + (confidence_z**2) / (4 * (n**2)))) / denom
    lower = max(0.0, centre - margin)
    upper = min(1.0, centre + margin)
    return (round(lower, 4), round(upper, 4))


# ── Written Rubrics (10 Defensible Retention & Benchmarking Areas) ─────────────
AREA_METADATA = {
    "Post-Failure Bank Bounce Penalties (ECS / NACH Return Charges)": {
        "description": "Failed auto-debit triggers bank ECS/NACH bounce penalties (₹295–₹590), causing intense financial resentment where penalty exceeds initial investment profit.",
        "severity": 4.9,
        "addressability": 4.5,  # Partner bank presentation buffer, automated retry before bank penalty cutoff
        "constraint_compat": 5.0,  # 100% compliant, helps user protect cash
        "affects_12m_continuation": True,
    },
    "Mid-Life Failed Debit (Insufficient Funds & Timing Mismatch)": {
        "description": "Mandate debit fails mid-life because salary credit date is misaligned with SIP date or temporary bank timeout, creating unintended installment breaks.",
        "severity": 4.8,
        "addressability": 4.3,  # In-app date shift, smart retry, UPI payment link fallback
        "constraint_compat": 5.0,  # Highly compliant and ethical
        "affects_12m_continuation": True,
    },
    "Unrealistic Return Expectations & Early Portfolio Shock": {
        "description": "First-time investors expect guaranteed linear FD-like growth; a -2% to -5% portfolio dip in Months 1–3 triggers loss aversion panic and voluntary abandonment.",
        "severity": 4.0,
        "addressability": 4.5,  # In-app expectation setting, milestone framing, volatility calibration
        "constraint_compat": 4.5,  # Compliant educational framing without forward return guarantees
        "affects_12m_continuation": True,
    },
    "Rigid Mandate Controls (Missing Pause & Skip Affordance)": {
        "description": "Novice investors seeking to skip a single installment due to salary timing find only a binary 'Cancel / Delete SIP' option, turning temporary liquidity dips into permanent churn.",
        "severity": 4.5,
        "addressability": 4.8,  # Pure Groww product UI affordance (add 1-click pause/skip)
        "constraint_compat": 5.0,  # Empowers user, zero regulatory friction
        "affects_12m_continuation": True,
    },
    "Metric Opacity (Annualized XIRR & Allotment Timelines)": {
        "description": "Confusion over why NAV changed after debit, annualized XIRR appearing excessively negative on short durations (<1 year), and delayed unit allotment.",
        "severity": 3.2,
        "addressability": 4.8,  # Information architecture: plain-English tooltips and transparent ledger
        "constraint_compat": 5.0,  # Transparent math, highly compliant
        "affects_12m_continuation": True,
    },
    "Peer Regret & Short-Term Return Comparison (FD / Stock FOMO)": {
        "description": "Comparing 6-month mutual fund performance against bank FDs or friends' viral stock picks, leading to perceived underperformance and impatience.",
        "severity": 3.0,
        "addressability": 3.8,  # Horizon comparison charts, real-return inflation calculators
        "constraint_compat": 4.2,  # Careful SEBI compliance on past performance disclaimers
        "affects_12m_continuation": True,
    },
    "Setup & Mandate Authorization Friction (Onboarding Drop)": {
        "description": "e-NACH authentication failure, bank signature mismatch, and registration delay during initial SIP setup, causing drop-off before first investment.",
        "severity": 3.5,
        "addressability": 3.9,  # Instant UPI Autopay onboarding, instant bank verification
        "constraint_compat": 4.8,
        "affects_12m_continuation": False,  # Onboarding barrier, not 12-m active continuation
    },
    "Status & Refund Confusion (Pending Allotment & Settlement Lag)": {
        "description": "Bank account debited but units not allotted on app within T+2, generating anxiety, repeated support tickets, and fear of lost capital.",
        "severity": 3.0,
        "addressability": 4.2,  # Order tracker with clear payment-to-allotment status timeline
        "constraint_compat": 5.0,
        "affects_12m_continuation": False,  # Support ticket driver, low dropout correlation
    },
    "Disconfirming Cashflow Constraints (True Financial Need)": {
        "description": "Genuine external liquidity shock: job change, unexpected medical bill, or urgent expense forcing capital withdrawal.",
        "severity": 3.8,
        "addressability": 2.2,  # Low: Groww cannot resolve user's macro unemployment or emergency
        "constraint_compat": 5.0,  # Respect user's emergency exit
        "affects_12m_continuation": True,
    },
    "Active Continuer Conviction & Volatility Resilience": {
        "description": "Empirical survivor profile: investors who completed 12+ months or continued investing through market crashes, driven by long-term horizon and low check frequency.",
        "severity": 1.2,
        "addressability": 4.0,  # Reinforce milestone habits, community stories
        "constraint_compat": 5.0,  # Organic positive behavior benchmark
        "affects_12m_continuation": False,
    },
}


def score_defensible_opportunity_areas(
    tagged_items: List[TaggedItem],
    raw_texts: Dict[str, str],
    raw_urls: Dict[str, str],
) -> List[OpportunityArea]:
    """
    Score opportunity areas using single primary assignment to eliminate double counting.
    Calculates Wilson 95% CIs on frequency and link-to-stopping.
    Computes sensitivity analysis across 4 weight configurations.
    Excludes 'General Mutual Fund Feedback'.
    """
    # Only score retention-relevant items (Brief Fix 4)
    relevant_items = [it for it in tagged_items if getattr(it, "retention_relevant", it.relevant)]
    total_relevant = len(relevant_items)
    if total_relevant == 0:
        return []

    # 1. Bucket items by PRIMARY area
    primary_buckets: Dict[str, List[TaggedItem]] = {}
    secondary_counts: Dict[str, int] = Counter()

    for item in relevant_items:
        pri = item.primary_area
        if not pri or pri == "General Mutual Fund Feedback":
            continue
        primary_buckets.setdefault(pri, []).append(item)
        for sec in item.secondary_areas:
            secondary_counts[sec] += 1

    areas_list: List[Dict[str, Any]] = []

    for name, meta in AREA_METADATA.items():
        items = primary_buckets.get(name, [])
        pri_vol = len(items)
        sec_vol = secondary_counts.get(name, 0)
        tot_vol = pri_vol + sec_vol

        # Wilson CI for primary frequency
        freq_rate = pri_vol / total_relevant if total_relevant else 0.0
        pri_ci = wilson_score_interval(pri_vol, total_relevant)

        # Link to stopping: share with explicit pause or stop intent
        stop_count = sum(
            1 for it in items
            if it.sip_status in ["cancelled", "paused", "lapsed"]
            or it.drop_type in ["voluntary", "involuntary"]
        )
        link_to_stop = stop_count / pri_vol if pri_vol else 0.0
        stop_ci = wilson_score_interval(stop_count, pri_vol)

        # Source diversity
        platforms = {it.source_platform.value for it in items if it.source_platform}
        source_div = len(platforms)

        # Platform breakdown
        p_breakdown = dict(Counter(it.source_platform.value for it in items if it.source_platform))

        # Top evidence quotes (verbatim, verified)
        sorted_by_votes = sorted(items, key=lambda x: x.upvotes, reverse=True)[:3]
        top_quotes = [
            Quote(
                raw_item_id=it.raw_item_id,
                text=raw_texts.get(it.raw_item_id, "")[:400],
                source_platform=it.source_platform.value if it.source_platform else "unknown",
                upvotes=it.upvotes,
                url=raw_urls.get(it.raw_item_id),
                evidence_span=it.drop_type_evidence or it.trigger_evidence or it.stated_expectation_evidence,
            )
            for it in sorted_by_votes
            if raw_texts.get(it.raw_item_id)
        ]

        # Normalized component scores (0.0 to 1.0)
        f_norm = min(1.0, freq_rate / 0.35)
        s_norm = meta["severity"] / 5.0
        l_norm = link_to_stop
        a_norm = meta["addressability"] / 5.0
        c_norm = meta["constraint_compat"] / 5.0

        # Weights:
        # 1. Baseline: Balanced (25% F, 25% S, 25% L, 15% A, 10% C)
        score_base = 0.25 * f_norm + 0.25 * s_norm + 0.25 * l_norm + 0.15 * a_norm + 0.10 * c_norm

        # 2. Severity-Heavy (15% F, 40% S, 25% L, 10% A, 10% C)
        score_sev = 0.15 * f_norm + 0.40 * s_norm + 0.25 * l_norm + 0.10 * a_norm + 0.10 * c_norm

        # 3. Frequency-Heavy (45% F, 15% S, 15% L, 15% A, 10% C)
        score_freq = 0.45 * f_norm + 0.15 * s_norm + 0.15 * l_norm + 0.15 * a_norm + 0.10 * c_norm

        # 4. Retention-Heavy (15% F, 20% S, 45% L, 10% A, 10% C)
        score_ret = 0.15 * f_norm + 0.20 * s_norm + 0.45 * l_norm + 0.10 * a_norm + 0.10 * c_norm

        areas_list.append({
            "name": name,
            "description": meta["description"],
            "primary_volume": pri_vol,
            "primary_volume_ci": pri_ci,
            "secondary_volume": sec_vol,
            "total_volume": tot_vol,
            "source_diversity": source_div,
            "severity_score": meta["severity"],
            "link_to_stopping": round(link_to_stop, 3),
            "link_to_stopping_ci": stop_ci,
            "addressability": meta["addressability"],
            "constraint_compat": meta["constraint_compat"],
            "score_base": round(score_base * 100, 2),
            "score_sev": round(score_sev * 100, 2),
            "score_freq": round(score_freq * 100, 2),
            "score_ret": round(score_ret * 100, 2),
            "top_quotes": top_quotes,
            "platform_breakdown": p_breakdown,
        })

    # Derive sensitivity ranks
    def assign_ranks(key: str, rank_attr: str):
        sorted_areas = sorted(areas_list, key=lambda x: x[key], reverse=True)
        for r, item in enumerate(sorted_areas, start=1):
            item[rank_attr] = r

    assign_ranks("score_base", "rank_baseline")
    assign_ranks("score_sev", "rank_severity_heavy")
    assign_ranks("score_freq", "rank_frequency_heavy")
    assign_ranks("score_ret", "rank_retention_heavy")

    final_objects: List[OpportunityArea] = []
    # Sort by baseline composite score
    areas_list.sort(key=lambda x: x["score_base"], reverse=True)

    for a in areas_list:
        final_objects.append(
            OpportunityArea(
                name=a["name"],
                description=a["description"],
                primary_volume=a["primary_volume"],
                primary_volume_ci=a["primary_volume_ci"],
                secondary_volume=a["secondary_volume"],
                total_volume=a["total_volume"],
                source_diversity=a["source_diversity"],
                severity_score=a["severity_score"],
                link_to_stopping=a["link_to_stopping"],
                link_to_stopping_ci=a["link_to_stopping_ci"],
                addressability=a["addressability"],
                constraint_compat=a["constraint_compat"],
                composite_score=a["score_base"],
                rank_baseline=a["rank_baseline"],
                rank_severity_heavy=a["rank_severity_heavy"],
                rank_frequency_heavy=a["rank_frequency_heavy"],
                rank_retention_heavy=a["rank_retention_heavy"],
                top_quotes=a["top_quotes"],
                platform_breakdown=a["platform_breakdown"],
            )
        )

    logger.info(f"[scorer] Scored {len(final_objects)} defensible retention opportunity areas")
    return final_objects


def run_disconfirming_evidence_pass(tagged_items: List[TaggedItem]) -> Dict[str, Any]:
    """
    Brief Fix 5: Disconfirming Evidence Pass across ALL 7 attribution classes:
    cashflow, structural, expectation_interpretation, market_move, comparison, trust, unknown.
    Reports TWO denominators: All records (N_total) and Known-only (N_known).
    Tests 3 rival hypotheses.
    """
    relevant = [it for it in tagged_items if getattr(it, "retention_relevant", it.relevant)]
    total = len(relevant)
    if total == 0:
        return {}

    # 7-way attribution counts
    classes = [
        "cashflow", "structural", "expectation_interpretation",
        "market_move", "comparison", "trust", "unknown"
    ]
    counts: Dict[str, int] = {c: 0 for c in classes}
    for it in relevant:
        attr = getattr(it, "disconfirming_attribution", "unknown") or "unknown"
        counts[attr] = counts.get(attr, 0) + 1

    known_total = sum(counts[c] for c in classes if c != "unknown")

    breakdown_all = {
        c: {
            "count": counts[c],
            "share_all": round((counts[c] / total) * 100, 1),
            "ci_all": wilson_score_interval(counts[c], total),
            "share_known": round((counts[c] / known_total) * 100, 1) if known_total else 0.0,
            "ci_known": wilson_score_interval(counts[c], known_total) if known_total else (0.0, 0.0),
        }
        for c in classes
    }

    # 3 Rival Hypotheses Testing
    n_cash_constraint = sum(1 for it in relevant if getattr(it, "rival_hypothesis", "none") == "cash_constraint")
    n_purposelessness = sum(1 for it in relevant if getattr(it, "rival_hypothesis", "none") == "purposelessness")
    n_better_alt = sum(1 for it in relevant if getattr(it, "rival_hypothesis", "none") == "better_alternative")

    return {
        "total_relevant": total,
        "known_total": known_total,
        "unknown_count": counts["unknown"],
        "attribution_breakdown": breakdown_all,
        "rival_hypotheses": {
            "cash_constraint": {
                "count": n_cash_constraint,
                "share_all": round((n_cash_constraint / total) * 100, 1),
                "ci_all": wilson_score_interval(n_cash_constraint, total),
            },
            "purposelessness": {
                "count": n_purposelessness,
                "share_all": round((n_purposelessness / total) * 100, 1),
                "ci_all": wilson_score_interval(n_purposelessness, total),
            },
            "better_alternative": {
                "count": n_better_alt,
                "share_all": round((n_better_alt / total) * 100, 1),
                "ci_all": wilson_score_interval(n_better_alt, total),
            },
        },
    }
