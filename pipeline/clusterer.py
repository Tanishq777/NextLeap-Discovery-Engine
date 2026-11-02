"""
pipeline/clusterer.py — Clustering Layer (Phase 4).

Two-pass clustering strategy for SIP retention opportunity areas:
  Pass 1 — Rule-Based: map (problem_types × trigger_types) combinations to
            predefined named opportunity areas. Items may be assigned to
            multiple areas (multi-label).

  Pass 2 — Semantic (HDBSCAN): cluster raw embeddings from Chroma using
            HDBSCAN, then use Groq to generate a name + description for
            each discovered semantic cluster. Merged with rule-based areas;
            overlapping items tracked to avoid double-counting.

  Items that match no rule → assigned to "Emerging / Uncategorized".
  Voiced vs. Inferred pattern already set by tagger (Phase 3); this module
  reads those values and aggregates them per area.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

from models.schemas import TaggedItem, OpportunityArea, PatternType
import config

# ── 4.1 Rule-Based Opportunity Map ───────────────────────────────────────────
# Keys: (problem_type_match, trigger_type_match)
#   - problem_type_match: exact problem_type value OR "*" (any)
#   - trigger_type_match: single trigger type OR comma-separated OR "*"
# An item matches a rule if it has the problem_type AND any of the
# trigger_types listed in the key.

OPPORTUNITY_RULES: List[Tuple[str, str, str, str]] = [
    # (problem_type, trigger_types, area_name, area_description)
    (
        "returns_disappointment", "*",
        "Unrealistic Return Expectations",
        "First-time investors expect FD-like guaranteed or high returns from day one. "
        "When early SIP statements show negative or flat returns, disappointment triggers "
        "disengagement. The mental model of 'investing = instant growth' clashes with "
        "the reality of compounding over years.",
    ),
    (
        "market_anxiety", "market_downturn",
        "Market Volatility Panic",
        "During market corrections, first-time investors panic-stop SIPs, unaware that "
        "downturns are when SIPs add the most value through rupee cost averaging. The "
        "app's red portfolio screen amplifies fear without providing educational context.",
    ),
    (
        "*", "market_downturn",
        "Early Portfolio Anxiety",
        "Users check their portfolio daily/weekly in the first few months, get stressed "
        "by red numbers, and confuse short-term volatility with permanent loss. The "
        "compulsive checking behavior is a leading indicator of eventual dropout.",
    ),
    (
        "goal_disconnect", "*",
        "Goal Disconnection",
        "SIPs started without a clear financial goal feel arbitrary. Without a visible "
        "connection between monthly debits and a future milestone (home, education, "
        "emergency fund), the SIP feels like an expense rather than progress toward "
        "something meaningful.",
    ),
    (
        "lack_of_understanding", "*",
        "Financial Literacy Gap",
        "Users don't understand NAV, units, CAGR vs absolute returns, or why their "
        "portfolio is 'down' despite adding money monthly. The gap between what the "
        "app shows and what users can interpret creates confusion and distrust.",
    ),
    (
        "peer_pressure", "peer_influence",
        "Social Proof Dependency",
        "Investors who started because a friend, family member, or influencer told "
        "them to have no internal conviction. When that external validation fades or "
        "the influencer changes their stance, the user's commitment evaporates.",
    ),
    (
        "app_confusion", "app_experience",
        "App Experience Friction",
        "Confusing portfolio screens, unclear return displays, misleading notifications, "
        "missing progress indicators, or aggressive upselling push users toward "
        "disengagement. The app becomes a source of anxiety rather than confidence.",
    ),
    (
        "financial_pressure", "life_event,financial_need",
        "Life Event Disruption",
        "Job loss, unexpected expenses, salary delays, marriage costs, or lifestyle "
        "inflation causes users to pause SIPs 'temporarily'. Most never restart because "
        "the psychological barrier to resuming is higher than starting fresh.",
    ),
    (
        "comparison_regret", "*",
        "Comparison & Regret Spiral",
        "Comparing their fund's returns to a friend's stock pick, another fund, FD rates, "
        "or even gold creates regret and perceived opportunity cost. The 'grass is greener' "
        "effect makes their current SIP feel like the wrong choice.",
    ),
    (
        "trust_deficit", "*",
        "Trust & Transparency Deficit",
        "Users feel they don't understand where their money is going, what fees or "
        "expense ratios they're paying, or whether the platform is acting in their "
        "interest. Hidden charges or unclear fund selection erode long-term trust.",
    ),
]

UNCATEGORIZED_AREA = "Emerging / Uncategorized"
UNCATEGORIZED_DESC = (
    "Feedback items that don't fit the predefined opportunity areas. "
    "May represent emerging themes or edge cases worth manual review."
)


# ── 4.2 Rule-Based Clustering ────────────────────────────────────────────────

def rule_based_cluster(
    tagged_items: List[TaggedItem],
) -> Dict[str, List[TaggedItem]]:
    """
    Assign each tagged item to one or more opportunity areas using
    the predefined rules. Returns {area_name: [items...]}.
    """
    area_map: Dict[str, List[TaggedItem]] = defaultdict(list)

    for item in tagged_items:
        matched = False

        for (pt_match, trigger_match, area_name, _desc) in OPPORTUNITY_RULES:
            if _item_matches_rule(item, pt_match, trigger_match):
                area_map[area_name].append(item)
                matched = True

        if not matched:
            area_map[UNCATEGORIZED_AREA].append(item)

    logger.info(
        f"[clusterer] Rule-based: {sum(len(v) for v in area_map.values())} assignments "
        f"across {len(area_map)} areas"
    )
    return dict(area_map)


def _item_matches_rule(
    item: TaggedItem, pt_match: str, trigger_match: str
) -> bool:
    """Check if a tagged item matches a single clustering rule."""
    # Check problem_type match
    pt_ok = pt_match == "*" or pt_match in item.problem_types

    # Check trigger_type match
    if trigger_match == "*":
        trigger_ok = True
    else:
        rule_triggers = {t.strip() for t in trigger_match.split(",")}
        trigger_ok = bool(rule_triggers & set(item.trigger_types))

    return pt_ok and trigger_ok


# ── 4.3 Semantic Clustering (HDBSCAN) ────────────────────────────────────────

def semantic_cluster(
    embedder,  # pipeline.embedder.Embedder
    tagged_items: List[TaggedItem],
    min_cluster_size: int = 5,
    min_samples: int = 3,
) -> Dict[str, List[TaggedItem]]:
    """
    Cluster items by embedding similarity using HDBSCAN.
    Returns {cluster_label: [items...]}, where labels are auto-generated
    or LLM-named.
    """
    try:
        import hdbscan
    except ImportError:
        logger.warning("[clusterer] hdbscan not installed — skipping semantic clustering.")
        return {}

    # Get embeddings from Chroma for all tagged items
    item_ids = [it.raw_item_id for it in tagged_items]
    embeddings, valid_ids = embedder.get_embeddings_for_ids(item_ids)

    if len(embeddings) < min_cluster_size * 2:
        logger.info(
            f"[clusterer] Only {len(embeddings)} embeddings — "
            f"too few for HDBSCAN (need ≥{min_cluster_size * 2})."
        )
        return {}

    # Run HDBSCAN
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
    )
    labels = clusterer.fit_predict(np.array(embeddings))

    # Build id → TaggedItem lookup
    id_to_item = {it.raw_item_id: it for it in tagged_items}

    # Group items by cluster label (skip noise label -1)
    clusters: Dict[str, List[TaggedItem]] = defaultdict(list)
    for idx, label in enumerate(labels):
        if label == -1:
            continue
        cluster_key = f"Semantic Cluster {label + 1}"
        item_id = valid_ids[idx]
        if item_id in id_to_item:
            clusters[cluster_key].append(id_to_item[item_id])

    logger.info(
        f"[clusterer] HDBSCAN found {len(clusters)} semantic clusters "
        f"({sum(len(v) for v in clusters.values())} items, "
        f"{sum(1 for l in labels if l == -1)} noise)"
    )

    return dict(clusters)


# ── 4.4 Merge ────────────────────────────────────────────────────────────────

def merge_clusters(
    rule_areas: Dict[str, List[TaggedItem]],
    sem_areas: Dict[str, List[TaggedItem]],
) -> Dict[str, List[TaggedItem]]:
    """
    Merge rule-based and semantic clusters. Items appearing in both
    are kept in their rule-based area; semantic clusters are added as
    additional areas.
    """
    merged = dict(rule_areas)

    for area_name, items in sem_areas.items():
        if area_name not in merged:
            merged[area_name] = items
        else:
            existing_ids = {it.id for it in merged[area_name]}
            for item in items:
                if item.id not in existing_ids:
                    merged[area_name].append(item)

    return merged


# ── 4.5 Update assigned_areas on TaggedItems ─────────────────────────────────

def update_assigned_areas(
    area_map: Dict[str, List[TaggedItem]],
) -> List[TaggedItem]:
    """
    Write assigned_areas back to each TaggedItem.
    Returns a flat list of all updated items (may contain duplicates
    if an item is assigned to multiple areas).
    """
    item_areas: Dict[str, List[str]] = defaultdict(list)
    all_items: Dict[str, TaggedItem] = {}

    for area_name, items in area_map.items():
        for item in items:
            item_areas[item.id].append(area_name)
            all_items[item.id] = item

    updated: List[TaggedItem] = []
    for item_id, areas in item_areas.items():
        item = all_items[item_id]
        item.assigned_areas = sorted(set(areas))
        updated.append(item)

    return updated
