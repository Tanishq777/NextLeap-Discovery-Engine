"""
models/schemas.py — Pydantic data models for the Discovery Engine.
All pipeline layers share these models to enforce a consistent schema.
Domain: Groww SIP Retention — First-Time Mutual Fund Investor Behavior.

Updated Schema answering the brief:
- drop_type: voluntary / involuntary / unclear / unknown
- sip_status: continuing / paused / reduced / cancelled / lapsed / restarted / unknown
- trigger: market move, expectation gap, cashflow, failed debit, comparison, family or peer pressure, confusion, trust, unknown
- stated_expectation: what they thought would happen ("Why start, what did they expect?")
- what_they_checked & check_frequency: ("What do they check, how often?")
- outside_app_action: asked Reddit or forum, asked family, searched Google, watched YouTube, did nothing, unknown
- influencer: finfluencer, parent, peer, colleague, self, unknown
- segment cuts: income_stability, money_source, age_band, lifecycle_month
- in_app_confusion_object: XIRR, NAV, units, statement, fees, pause flow, mandate, none_or_unknown
- evidence spans and confidence scores on all classified dimensions
- primary_area (single primary) + secondary_areas (prevent double-counting)
"""
from __future__ import annotations

from typing import Optional, List, Tuple, Dict, Any
from enum import Enum
from pydantic import BaseModel, field_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class SourcePlatform(str, Enum):
    PLAY_STORE = "play_store"
    APP_STORE  = "app_store"
    REDDIT     = "reddit"
    YOUTUBE    = "youtube"
    HELP_FORUM = "help_forum"
    WEB        = "web"


class AnxietyLevel(str, Enum):
    LOW  = "low"
    MED  = "med"
    HIGH = "high"


class PatternType(str, Enum):
    VOICED   = "voiced"
    INFERRED = "inferred"


class RetentionRisk(str, Enum):
    LOW             = "low"
    MED             = "med"
    HIGH            = "high"
    ALREADY_CHURNED = "already_churned"


class LanguageTag(str, Enum):
    EN       = "en"
    HI       = "hi"
    HINGLISH = "hinglish"


# ── Raw Item (Layer 1/2 output) ───────────────────────────────────────────────

class RawItem(BaseModel):
    """
    Normalised representation of a single piece of user feedback,
    collected from the source (before classification).
    """
    id: str                          # UUID v4
    source: SourcePlatform
    platform_item_id: Optional[str] = None   # original ID or URL from source
    app_name: Optional[str] = None           # Groww, Zerodha Coin, Kuvera, INDmoney, ET Money, etc.
    text: str                        # cleaned feedback text (max 2,000 chars)
    language: str = "en"             # en, hi, hinglish
    date: Optional[str]   = None     # ISO 8601 date string, or None
    upvotes: int          = 0        # engagement proxy (votes, likes, etc.)
    url: Optional[str]    = None     # permalink to original content
    collected_at: str     = ""       # ISO 8601 timestamp of collection
    is_synthetic: bool    = False    # Rule 0: False for all empirical items
    platform_target: str  = "generic"# Groww, competitor, generic

    @field_validator("text")
    @classmethod
    def text_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("RawItem.text must not be empty")
        return v.strip()


# ── Tagged Item (Layer 4 output) ──────────────────────────────────────────────

class TaggedItem(BaseModel):
    """
    Classified version of a RawItem after analysis.
    Implements all required brief dimensions, evidence spans, confidence scores,
    segment cuts, and primary/secondary opportunity areas.
    """
    id: str                                          # UUID v4
    raw_item_id: str                                 # FK → RawItem.id

    # Core Relevance
    relevant: bool                                   # Is this about SIP/MF investing behavior?

    # Brief Question 1: Drop Type (voluntary vs involuntary vs unclear vs unknown)
    # Failed mandates and deliberate stops need different fixes
    drop_type: str = "unknown"                       # voluntary, involuntary, unclear, unknown
    drop_type_evidence: Optional[str] = None
    drop_type_confidence: float = 0.0

    # Brief Question 2: SIP Status (continuing vs paused vs reduced vs cancelled vs lapsed vs restarted)
    # Separates survivors from churners
    sip_status: str = "unknown"                      # continuing, paused, reduced, cancelled, lapsed, restarted, unknown
    sip_status_evidence: Optional[str] = None
    sip_status_confidence: float = 0.0

    # Brief Question 3: Root-cause Trigger
    # market move, expectation gap, cashflow, failed debit, comparison, family or peer pressure, confusion, trust, unknown
    trigger: str = "unknown"
    trigger_evidence: Optional[str] = None
    trigger_confidence: float = 0.0

    # Brief Question 4: Stated Expectation
    # "Why start, what did they expect?" (e.g. 15% guaranteed, FD replacement, wealth creation)
    stated_expectation: str = "unknown"
    stated_expectation_evidence: Optional[str] = None
    stated_expectation_confidence: float = 0.0

    # Brief Question 5: What They Checked & Checking Frequency
    # "What do they check, how often?"
    what_they_checked: str = "unknown"               # portfolio_value, returns, NAV, XIRR, daily_pnl, index, unknown
    what_they_checked_evidence: Optional[str] = None
    what_they_checked_confidence: float = 0.0

    check_frequency: str = "unknown"                 # daily, multiple_times_a_day, weekly, monthly, only_on_dip, unknown
    check_frequency_evidence: Optional[str] = None
    check_frequency_confidence: float = 0.0

    # Brief Question 6: Outside App Action
    # Strongest hypothesis testing: asked Reddit or forum, asked family, searched Google, watched YouTube, did nothing, unknown
    outside_app_action: str = "unknown"
    outside_app_action_evidence: Optional[str] = None
    outside_app_action_confidence: float = 0.0

    # Brief Question 7: Influencer
    # Segment cut: finfluencer, parent, peer, colleague, self, unknown
    influencer: str = "unknown"
    influencer_evidence: Optional[str] = None
    influencer_confidence: float = 0.0

    # Brief Question 8: Demographic & Segment Cuts (unknown allowed and preferred when unstated)
    income_stability: str = "unknown"                # stable, variable, student, freelance, unknown
    money_source: str = "unknown"                    # salary, pocket_money, savings, bonus, business, unknown
    age_band: str = "unknown"                        # 18-24, 25-34, 35-44, 45+, unknown
    lifecycle_month: Optional[int] = None            # Month number if stated (1, 2, 3, etc.) else None

    # Brief Question 9: In-App Confusion Object
    # Product-level targeting: XIRR, NAV, units, statement, fees, pause flow, mandate, none_or_unknown
    in_app_confusion_object: str = "none_or_unknown"
    in_app_confusion_evidence: Optional[str] = None
    in_app_confusion_confidence: float = 0.0

    # Two-level relevance filter (Brief Fix 4)
    on_topic: bool = True                            # Mutual fund / SIP investing topic
    retention_relevant: bool = False                 # Affects continuing/churn/pause/failure/confusion

    # Platform Target & Claims Hygiene (Brief Fix 8)
    platform_target: str = "generic"                 # Groww, competitor, generic

    # Rule 0: Mocking & Synthetic Isolation
    is_synthetic: bool = False                       # True only for synthetic test cases

    # Brief Fix 9: Mandate Sub-cluster Decomposition
    # setup_failure, mid_life_failed_debit, post_failure_bounce_penalty, status_refund_confusion, none
    mandate_subcluster: str = "none"

    # Brief Fix 5: Disconfirming Pass Attribution (All 7 classes)
    # cashflow, structural, expectation_interpretation, market_move, comparison, trust, unknown
    disconfirming_attribution: str = "unknown"

    # Rival Hypotheses Testing: cash_constraint, purposelessness, better_alternative, none
    rival_hypothesis: str = "none"

    # Language tagging (Hinglish, Hindi, English)
    language: str = "en"                             # en, hi, hinglish

    # Opportunity Area assignment: single primary (stops double counting) + optional secondary
    primary_area: Optional[str] = None
    secondary_areas: List[str] = []

    # Survivorship / Continuation flag
    is_continuer: bool = False

    # Unsure moment extraction (for Golden Evaluation set)
    unsure_question: Optional[str] = None

    # Existing taxonomy dimensions (preserved for dashboard continuity)
    problem_types: List[str] = []
    lifecycle_stage: Optional[str] = None            # pre_sip, first_month, early_1_3m, mid_4_6m, late_7_12m, post_dropout
    behavioral_signals: List[str] = []
    emotional_state: Optional[str] = None
    trigger_types: List[str] = []
    retention_risk: Optional[RetentionRisk] = None
    pattern_type: Optional[PatternType] = None       # voiced vs inferred
    assigned_areas: List[str] = []

    # Classifier metadata
    classifier_error: bool = False

    # Denormalised source info
    source_platform: Optional[SourcePlatform] = None
    app_name: Optional[str] = None
    date: Optional[str]   = None
    upvotes: int          = 0


# ── Opportunity Area (Layer 5 output) ─────────────────────────────────────────

class Quote(BaseModel):
    """A verbatim user quote selected as evidence for an opportunity area."""
    raw_item_id: str
    text: str
    source_platform: str
    upvotes: int = 0
    url: Optional[str] = None
    evidence_span: Optional[str] = None


class OpportunityArea(BaseModel):
    """
    A scored, defensibly ranked cluster of feedback items.
    Primary volume prevents double-counting across areas.
    """
    name: str
    description: str
    evidence_volume: int = 0                        # Total evidence volume assigned to area
    primary_volume: int = 0                         # Non-overlapping count (exclusive assignment)
    primary_volume_ci: Tuple[float, float] = (0.0, 0.0)  # Wilson 95% CI on primary share
    secondary_volume: int = 0                       # Optional multi-tag count
    total_volume: int = 0                           # primary + secondary
    source_diversity: int = 0                       # distinct platforms (1–6)
    severity_score: float = 0.0                     # 1 to 5 written rubric
    link_to_stopping: float = 0.0                   # Share with explicit pause/stop intent (0.0 to 1.0)
    link_to_stopping_ci: Tuple[float, float] = (0.0, 0.0) # Wilson 95% CI
    addressability: float = 0.0                     # 1 to 5 written rubric (can Groww act?)
    constraint_compat: float = 0.0                  # 1 to 5 written rubric (no fear, FOMO, urgency, fund picks)
    composite_score: float = 0.0                    # Weighted composite score
    rank_baseline: int = 1                          # Baseline rank
    rank_severity_heavy: int = 1                    # Sensitivity rank 1
    rank_frequency_heavy: int = 1                   # Sensitivity rank 2
    rank_retention_heavy: int = 1                   # Sensitivity rank 3
    abandonment_rate: float = 0.0                   # Share of churned users (0.0 to 1.0)
    voiced_count: int = 0                           # Voiced pattern count
    inferred_count: int = 0                         # Inferred pattern count
    top_quotes: List[Quote] = []
    platform_breakdown: Dict[str, int] = {}
    cluster_source: str = "defensible_scoring"
