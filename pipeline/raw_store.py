"""
pipeline/raw_store.py — SQLite persistence layer for raw collected items and tagged insights.
Manages the raw_items, tagged_items, opportunity_areas, and quotes tables.
Thread-safe with WAL mode enabled.
Supports brief-aligned schema:
- drop_type, sip_status, trigger, stated_expectation, what_they_checked, check_frequency
- outside_app_action, influencer, segment cuts (income_stability, money_source, age_band, lifecycle_month)
- in_app_confusion_object, language, primary_area, secondary_areas, unsure_question, is_continuer
- evidence spans and confidence scores
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Generator, List, Optional, Set, Dict, Any, Tuple

import pandas as pd
from loguru import logger

from models.schemas import (
    RawItem,
    TaggedItem,
    OpportunityArea,
    Quote,
    SourcePlatform,
    RetentionRisk,
    PatternType,
)
import config


class RawStore:
    """
    Manages the discovery_engine SQLite database.
    Tables: raw_items, tagged_items, opportunity_areas, quotes.
    """

    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self._init_db()

    # ── Connection management ─────────────────────────────────────────────────

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager that yields an open connection and commits on exit."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Schema initialisation & Migration ─────────────────────────────────────

    def _init_db(self) -> None:
        """Create all tables and migrate columns if needed."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS raw_items (
                    id                TEXT PRIMARY KEY,
                    source            TEXT NOT NULL,
                    platform_item_id  TEXT,
                    app_name          TEXT,
                    text              TEXT NOT NULL,
                    language          TEXT DEFAULT 'en',
                    date              TEXT,
                    upvotes           INTEGER DEFAULT 0,
                    url               TEXT,
                    collected_at      TEXT
                );

                CREATE TABLE IF NOT EXISTS tagged_items (
                    id                           TEXT PRIMARY KEY,
                    raw_item_id                  TEXT NOT NULL,
                    relevant                     INTEGER NOT NULL,
                    drop_type                    TEXT DEFAULT 'unknown',
                    drop_type_evidence           TEXT,
                    drop_type_confidence         REAL DEFAULT 0.0,
                    sip_status                   TEXT DEFAULT 'unknown',
                    sip_status_evidence          TEXT,
                    sip_status_confidence        REAL DEFAULT 0.0,
                    trigger                      TEXT DEFAULT 'unknown',
                    trigger_evidence             TEXT,
                    trigger_confidence           REAL DEFAULT 0.0,
                    stated_expectation           TEXT DEFAULT 'unknown',
                    stated_expectation_evidence  TEXT,
                    stated_expectation_confidence REAL DEFAULT 0.0,
                    what_they_checked            TEXT DEFAULT 'unknown',
                    what_they_checked_evidence   TEXT,
                    what_they_checked_confidence REAL DEFAULT 0.0,
                    check_frequency              TEXT DEFAULT 'unknown',
                    check_frequency_evidence     TEXT,
                    check_frequency_confidence   REAL DEFAULT 0.0,
                    outside_app_action           TEXT DEFAULT 'unknown',
                    outside_app_action_evidence  TEXT,
                    outside_app_action_confidence REAL DEFAULT 0.0,
                    influencer                   TEXT DEFAULT 'unknown',
                    influencer_evidence          TEXT,
                    influencer_confidence        REAL DEFAULT 0.0,
                    income_stability             TEXT DEFAULT 'unknown',
                    money_source                 TEXT DEFAULT 'unknown',
                    age_band                     TEXT DEFAULT 'unknown',
                    lifecycle_month              INTEGER,
                    in_app_confusion_object      TEXT DEFAULT 'none_or_unknown',
                    in_app_confusion_evidence    TEXT,
                    in_app_confusion_confidence  REAL DEFAULT 0.0,
                    language                     TEXT DEFAULT 'en',
                    primary_area                 TEXT,
                    secondary_areas              TEXT DEFAULT '[]',
                    is_continuer                 INTEGER DEFAULT 0,
                    unsure_question              TEXT,
                    problem_types                TEXT DEFAULT '[]',
                    lifecycle_stage              TEXT,
                    behavioral_signals           TEXT DEFAULT '[]',
                    emotional_state              TEXT,
                    trigger_types                TEXT DEFAULT '[]',
                    retention_risk               TEXT,
                    pattern_type                 TEXT,
                    assigned_areas               TEXT DEFAULT '[]',
                    classifier_error             INTEGER DEFAULT 0,
                    source_platform              TEXT,
                    app_name                     TEXT,
                    date                         TEXT,
                    upvotes                      INTEGER DEFAULT 0,
                    FOREIGN KEY (raw_item_id) REFERENCES raw_items(id)
                );

                CREATE TABLE IF NOT EXISTS opportunity_areas (
                    name                 TEXT PRIMARY KEY,
                    description          TEXT,
                    primary_volume       INTEGER DEFAULT 0,
                    primary_volume_ci    TEXT DEFAULT '[0.0, 0.0]',
                    secondary_volume     INTEGER DEFAULT 0,
                    total_volume         INTEGER DEFAULT 0,
                    evidence_volume      INTEGER DEFAULT 0,
                    source_diversity     INTEGER DEFAULT 0,
                    severity_score       REAL DEFAULT 0.0,
                    link_to_stopping     REAL DEFAULT 0.0,
                    link_to_stopping_ci  TEXT DEFAULT '[0.0, 0.0]',
                    addressability       REAL DEFAULT 0.0,
                    constraint_compat    REAL DEFAULT 0.0,
                    composite_score      REAL DEFAULT 0.0,
                    rank_baseline        INTEGER DEFAULT 1,
                    rank_severity_heavy  INTEGER DEFAULT 1,
                    rank_frequency_heavy INTEGER DEFAULT 1,
                    rank_retention_heavy INTEGER DEFAULT 1,
                    abandonment_rate     REAL DEFAULT 0.0,
                    voiced_count         INTEGER DEFAULT 0,
                    inferred_count       INTEGER DEFAULT 0,
                    top_quotes           TEXT DEFAULT '[]',
                    platform_breakdown   TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS quotes (
                    id               TEXT PRIMARY KEY,
                    area_name        TEXT NOT NULL,
                    text             TEXT NOT NULL,
                    source_platform  TEXT,
                    upvotes          INTEGER DEFAULT 0,
                    url              TEXT,
                    evidence_span    TEXT
                );

                CREATE TABLE IF NOT EXISTS synthetic_items (
                    id                TEXT PRIMARY KEY,
                    source            TEXT NOT NULL,
                    platform_item_id  TEXT,
                    app_name          TEXT,
                    text              TEXT NOT NULL,
                    language          TEXT DEFAULT 'en',
                    is_synthetic      INTEGER DEFAULT 1,
                    synthetic_reason  TEXT,
                    generator_model   TEXT,
                    date              TEXT,
                    url               TEXT,
                    upvotes           INTEGER DEFAULT 0,
                    collected_at      TEXT
                );

            """)

            # Ensure any new columns exist if table was already created
            self._ensure_columns(conn, "raw_items", {
                "app_name": "TEXT",
                "language": "TEXT DEFAULT 'en'",
                "is_synthetic": "INTEGER DEFAULT 0",
                "platform_target": "TEXT DEFAULT 'generic'",
            })
            self._ensure_columns(conn, "tagged_items", {
                "on_topic": "INTEGER DEFAULT 1",
                "retention_relevant": "INTEGER DEFAULT 0",
                "platform_target": "TEXT DEFAULT 'generic'",
                "is_synthetic": "INTEGER DEFAULT 0",
                "mandate_subcluster": "TEXT DEFAULT 'none'",
                "disconfirming_attribution": "TEXT DEFAULT 'unknown'",
                "rival_hypothesis": "TEXT DEFAULT 'none'",
                "drop_type": "TEXT DEFAULT 'unknown'",
                "drop_type_evidence": "TEXT",
                "drop_type_confidence": "REAL DEFAULT 0.0",
                "sip_status": "TEXT DEFAULT 'unknown'",
                "sip_status_evidence": "TEXT",
                "sip_status_confidence": "REAL DEFAULT 0.0",
                "trigger": "TEXT DEFAULT 'unknown'",
                "trigger_evidence": "TEXT",
                "trigger_confidence": "REAL DEFAULT 0.0",
                "stated_expectation": "TEXT DEFAULT 'unknown'",
                "stated_expectation_evidence": "TEXT",
                "stated_expectation_confidence": "REAL DEFAULT 0.0",
                "what_they_checked": "TEXT DEFAULT 'unknown'",
                "what_they_checked_evidence": "TEXT",
                "what_they_checked_confidence": "REAL DEFAULT 0.0",
                "check_frequency": "TEXT DEFAULT 'unknown'",
                "check_frequency_evidence": "TEXT",
                "check_frequency_confidence": "REAL DEFAULT 0.0",
                "outside_app_action": "TEXT DEFAULT 'unknown'",
                "outside_app_action_evidence": "TEXT",
                "outside_app_action_confidence": "REAL DEFAULT 0.0",
                "influencer": "TEXT DEFAULT 'unknown'",
                "influencer_evidence": "TEXT",
                "influencer_confidence": "REAL DEFAULT 0.0",
                "income_stability": "TEXT DEFAULT 'unknown'",
                "money_source": "TEXT DEFAULT 'unknown'",
                "age_band": "TEXT DEFAULT 'unknown'",
                "lifecycle_month": "INTEGER",
                "in_app_confusion_object": "TEXT DEFAULT 'none_or_unknown'",
                "in_app_confusion_evidence": "TEXT",
                "in_app_confusion_confidence": "REAL DEFAULT 0.0",
                "language": "TEXT DEFAULT 'en'",
                "primary_area": "TEXT",
                "secondary_areas": "TEXT DEFAULT '[]'",
                "is_continuer": "INTEGER DEFAULT 0",
                "unsure_question": "TEXT",
                "app_name": "TEXT",
            })
            self._ensure_columns(conn, "opportunity_areas", {
                "primary_volume": "INTEGER DEFAULT 0",
                "primary_volume_ci": "TEXT DEFAULT '[0.0, 0.0]'",
                "secondary_volume": "INTEGER DEFAULT 0",
                "total_volume": "INTEGER DEFAULT 0",
                "link_to_stopping": "REAL DEFAULT 0.0",
                "link_to_stopping_ci": "TEXT DEFAULT '[0.0, 0.0]'",
                "addressability": "REAL DEFAULT 0.0",
                "constraint_compat": "REAL DEFAULT 0.0",
                "composite_score": "REAL DEFAULT 0.0",
                "rank_baseline": "INTEGER DEFAULT 1",
                "rank_severity_heavy": "INTEGER DEFAULT 1",
                "rank_frequency_heavy": "INTEGER DEFAULT 1",
                "rank_retention_heavy": "INTEGER DEFAULT 1",
            })
            self._ensure_columns(conn, "quotes", {
                "evidence_span": "TEXT",
            })

            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_raw_source         ON raw_items(source);
                CREATE INDEX IF NOT EXISTS idx_raw_app            ON raw_items(app_name);
                CREATE INDEX IF NOT EXISTS idx_raw_lang           ON raw_items(language);
                CREATE INDEX IF NOT EXISTS idx_tagged_relevant     ON tagged_items(relevant);
                CREATE INDEX IF NOT EXISTS idx_tagged_raw_id       ON tagged_items(raw_item_id);
                CREATE INDEX IF NOT EXISTS idx_tagged_sip_status   ON tagged_items(sip_status);
                CREATE INDEX IF NOT EXISTS idx_tagged_drop_type    ON tagged_items(drop_type);
                CREATE INDEX IF NOT EXISTS idx_tagged_trigger      ON tagged_items(trigger);
                CREATE INDEX IF NOT EXISTS idx_tagged_primary_area ON tagged_items(primary_area);
            """)
        logger.debug(f"[raw_store] Database initialised at {self.db_path}")

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
        """Add any missing columns to an existing table."""
        cursor = conn.cursor()
        existing = {row["name"] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
        for col_name, col_def in columns.items():
            if col_name not in existing:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                except Exception as e:
                    logger.debug(f"[raw_store] Note on column add {table}.{col_name}: {e}")

    # ── Raw Items ─────────────────────────────────────────────────────────────

    def insert_batch(self, items: List[RawItem]) -> int:
        """
        Upsert a batch of RawItems into the raw_items table.
        Returns the number of newly inserted rows.
        """
        if not items:
            return 0

        rows = [
            (
                item.id,
                item.source.value if hasattr(item.source, "value") else str(item.source),
                item.platform_item_id,
                item.app_name or "",
                item.text,
                item.language or "en",
                item.date,
                item.upvotes,
                item.url,
                item.collected_at,
                1 if getattr(item, "is_synthetic", False) else 0,
                getattr(item, "platform_target", "generic") or "generic",
            )
            for item in items
        ]

        with self._conn() as conn:
            cursor = conn.executemany(
                """
                INSERT OR IGNORE INTO raw_items
                    (id, source, platform_item_id, app_name, text, language, date, upvotes, url, collected_at, is_synthetic, platform_target)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            inserted = cursor.rowcount

        logger.debug(f"[raw_store] Inserted {inserted}/{len(items)} items")
        return inserted

    def count(self, source: Optional[str] = None) -> int:
        """Return total raw items count."""
        with self._conn() as conn:
            if source:
                row = conn.execute(
                    "SELECT COUNT(*) FROM raw_items WHERE source = ?", (source,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM raw_items").fetchone()
        return row[0] if row else 0

    def get_all_hashes(self) -> Set[str]:
        """Return SHA-256 hashes of existing raw items."""
        import hashlib
        with self._conn() as conn:
            rows = conn.execute("SELECT source, text FROM raw_items").fetchall()
        hashes: Set[str] = set()
        for row in rows:
            key = f"{row['source']}::{row['text'][:200].lower().strip()}"
            hashes.add(hashlib.sha256(key.encode()).hexdigest())
        return hashes

    def get_all_raw_items(self) -> List[RawItem]:
        """Fetch all empirical raw items (excluding synthetic)."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM raw_items WHERE is_synthetic = 0").fetchall()
        return [
            RawItem(
                id=r["id"],
                source=SourcePlatform(r["source"]),
                platform_item_id=r["platform_item_id"],
                app_name=r["app_name"],
                text=r["text"],
                language=r["language"] or "en",
                date=r["date"],
                upvotes=r["upvotes"] or 0,
                url=r["url"],
                collected_at=r["collected_at"] or "",
                is_synthetic=bool(r["is_synthetic"]) if "is_synthetic" in r.keys() else False,
                platform_target=r["platform_target"] if "platform_target" in r.keys() else "generic",
            )
            for r in rows
        ]

    def get_untagged_items(self) -> List[RawItem]:
        """Fetch raw items that have no entry in tagged_items yet."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT r.* FROM raw_items r
                LEFT JOIN tagged_items t ON t.raw_item_id = r.id
                WHERE t.id IS NULL AND (r.is_synthetic IS NULL OR r.is_synthetic = 0)
                """
            ).fetchall()

        return [
            RawItem(
                id=row["id"],
                source=SourcePlatform(row["source"]),
                platform_item_id=row["platform_item_id"],
                app_name=row["app_name"],
                text=row["text"],
                language=row["language"] or "en",
                date=row["date"],
                upvotes=row["upvotes"] or 0,
                url=row["url"],
                collected_at=row["collected_at"] or "",
                is_synthetic=bool(row["is_synthetic"]) if "is_synthetic" in row.keys() else False,
                platform_target=row["platform_target"] if "platform_target" in row.keys() else "generic",
            )
            for row in rows
        ]

    # ── Tagged Items ──────────────────────────────────────────────────────────

    def insert_tagged_item(self, item: TaggedItem) -> None:
        """Upsert a single TaggedItem into tagged_items table."""
        self.insert_tagged_items_batch([item])

    def insert_tagged_items_batch(self, items: List[TaggedItem]) -> int:
        """Upsert a batch of TaggedItems."""
        if not items:
            return 0

        rows = []
        for item in items:
            rows.append((
                item.id,
                item.raw_item_id,
                1 if item.relevant else 0,
                1 if getattr(item, "on_topic", True) else 0,
                1 if getattr(item, "retention_relevant", False) else 0,
                getattr(item, "platform_target", "generic") or "generic",
                1 if getattr(item, "is_synthetic", False) else 0,
                getattr(item, "mandate_subcluster", "none") or "none",
                getattr(item, "disconfirming_attribution", "unknown") or "unknown",
                getattr(item, "rival_hypothesis", "none") or "none",
                item.drop_type or "unknown",
                item.drop_type_evidence,
                item.drop_type_confidence,
                item.sip_status or "unknown",
                item.sip_status_evidence,
                item.sip_status_confidence,
                item.trigger or "unknown",
                item.trigger_evidence,
                item.trigger_confidence,
                item.stated_expectation or "unknown",
                item.stated_expectation_evidence,
                item.stated_expectation_confidence,
                item.what_they_checked or "unknown",
                item.what_they_checked_evidence,
                item.what_they_checked_confidence,
                item.check_frequency or "unknown",
                item.check_frequency_evidence,
                item.check_frequency_confidence,
                item.outside_app_action or "unknown",
                item.outside_app_action_evidence,
                item.outside_app_action_confidence,
                item.influencer or "unknown",
                item.influencer_evidence,
                item.influencer_confidence,
                item.income_stability or "unknown",
                item.money_source or "unknown",
                item.age_band or "unknown",
                item.lifecycle_month,
                item.in_app_confusion_object or "none_or_unknown",
                item.in_app_confusion_evidence,
                item.in_app_confusion_confidence,
                item.language or "en",
                item.primary_area or "",
                json.dumps(item.secondary_areas or []),
                1 if item.is_continuer else 0,
                item.unsure_question or "",
                json.dumps(item.problem_types or []),
                item.lifecycle_stage or "unknown",
                json.dumps(item.behavioral_signals or []),
                item.emotional_state or "",
                json.dumps(item.trigger_types or []),
                item.retention_risk.value if item.retention_risk else None,
                item.pattern_type.value if item.pattern_type else None,
                json.dumps(item.assigned_areas or []),
                1 if item.classifier_error else 0,
                item.source_platform.value if item.source_platform else None,
                item.app_name or "",
                item.date,
                item.upvotes,
            ))

        with self._conn() as conn:
            cursor = conn.executemany(
                """
                INSERT OR REPLACE INTO tagged_items (
                    id, raw_item_id, relevant,
                    on_topic, retention_relevant, platform_target, is_synthetic,
                    mandate_subcluster, disconfirming_attribution, rival_hypothesis,
                    drop_type, drop_type_evidence, drop_type_confidence,
                    sip_status, sip_status_evidence, sip_status_confidence,
                    trigger, trigger_evidence, trigger_confidence,
                    stated_expectation, stated_expectation_evidence, stated_expectation_confidence,
                    what_they_checked, what_they_checked_evidence, what_they_checked_confidence,
                    check_frequency, check_frequency_evidence, check_frequency_confidence,
                    outside_app_action, outside_app_action_evidence, outside_app_action_confidence,
                    influencer, influencer_evidence, influencer_confidence,
                    income_stability, money_source, age_band, lifecycle_month,
                    in_app_confusion_object, in_app_confusion_evidence, in_app_confusion_confidence,
                    language, primary_area, secondary_areas, is_continuer, unsure_question,
                    problem_types, lifecycle_stage, behavioral_signals,
                    emotional_state, trigger_types, retention_risk,
                    pattern_type, assigned_areas, classifier_error,
                    source_platform, app_name, date, upvotes
                ) VALUES (
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                rows,
            )
            return cursor.rowcount

    def segregate_synthetic_items(self, export_path: str = "data/synthetic_items.json") -> int:
        """
        Rule 0 enforcement:
        Move all simulated/synthetic items into the synthetic_items table
        and export them to data/synthetic_items.json.
        Excludes them from raw_items and tagged_items.
        """
        import os
        with self._conn() as conn:
            # Find all synthetic items (e.g. rd_gen_%)
            synths = conn.execute(
                """
                SELECT * FROM raw_items 
                WHERE platform_item_id LIKE 'rd_gen_%' 
                   OR is_synthetic = 1 
                   OR text LIKE '%(Ref #%'
                """
            ).fetchall()

            if not synths:
                logger.info("[raw_store] No synthetic items detected in raw_items.")
                return 0

            synth_records = []
            for s in synths:
                rec = {
                    "id": s["id"],
                    "source": s["source"],
                    "platform_item_id": s["platform_item_id"],
                    "app_name": s["app_name"],
                    "text": s["text"],
                    "language": s["language"] or "en",
                    "is_synthetic": 1,
                    "synthetic_reason": "simulated retail investor dilemma / edge case",
                    "generator_model": "synthetic_template_generator_v2",
                    "date": s["date"],
                    "url": s["url"],
                    "upvotes": s["upvotes"] or 0,
                    "collected_at": s["collected_at"] or "",
                }
                synth_records.append(rec)

            conn.executemany(
                """
                INSERT OR REPLACE INTO synthetic_items (
                    id, source, platform_item_id, app_name, text, language,
                    is_synthetic, synthetic_reason, generator_model, date, url, upvotes, collected_at
                ) VALUES (
                    :id, :source, :platform_item_id, :app_name, :text, :language,
                    :is_synthetic, :synthetic_reason, :generator_model, :date, :url, :upvotes, :collected_at
                )
                """,
                synth_records,
            )

            synth_ids = [s["id"] for s in synths]
            placeholders = ",".join("?" for _ in synth_ids)
            conn.execute(f"DELETE FROM tagged_items WHERE raw_item_id IN ({placeholders})", synth_ids)
            conn.execute(f"DELETE FROM raw_items WHERE id IN ({placeholders})", synth_ids)

        os.makedirs(os.path.dirname(export_path) or ".", exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump({
                "description": "Rule 0: Segregated synthetic test cases. Excluded from all empirical metrics, CIs, opportunity scores, and quote banks.",
                "total_synthetic_items": len(synth_records),
                "is_synthetic": True,
                "label": "synthetic test cases",
                "items": synth_records,
            }, f, indent=2, ensure_ascii=False)

        logger.info(f"[raw_store] Segregated {len(synth_records)} synthetic test cases to synthetic_items table and {export_path}")
        return len(synth_records)

    def get_tagging_stats(self) -> dict:
        """Return tagging counts."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)                                      AS total,
                    SUM(CASE WHEN relevant = 1 THEN 1 ELSE 0 END) AS relevant,
                    SUM(CASE WHEN relevant = 0 AND classifier_error = 0
                             THEN 1 ELSE 0 END)                   AS irrelevant,
                    SUM(classifier_error)                         AS errors,
                    SUM(CASE WHEN is_continuer = 1 THEN 1 ELSE 0 END) AS continuers
                FROM tagged_items
                """
            ).fetchone()

        total      = row["total"]      or 0
        relevant   = row["relevant"]   or 0
        irrelevant = row["irrelevant"] or 0
        errors     = row["errors"]     or 0
        continuers = row["continuers"] or 0
        error_rate = (errors / total) if total else 0.0

        return {
            "total":      total,
            "relevant":   relevant,
            "irrelevant": irrelevant,
            "errors":     errors,
            "continuers": continuers,
            "error_rate": round(error_rate, 4),
        }

    def get_relevant_tagged_items(self) -> List[TaggedItem]:
        """Return all relevant tagged items."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT t.*, r.url
                FROM tagged_items t
                LEFT JOIN raw_items r ON r.id = t.raw_item_id
                WHERE t.relevant = 1 AND t.classifier_error = 0
                """
            ).fetchall()

        items: List[TaggedItem] = []
        for r in rows:
            items.append(self._row_to_tagged_item(r))
        return items

    def _row_to_tagged_item(self, r: sqlite3.Row) -> TaggedItem:
        rr_val = r["retention_risk"]
        pt_val = r["pattern_type"]
        sp_val = r["source_platform"]
        keys = r.keys()
        return TaggedItem(
            id=r["id"],
            raw_item_id=r["raw_item_id"],
            relevant=bool(r["relevant"]),
            on_topic=bool(r["on_topic"]) if "on_topic" in keys else True,
            retention_relevant=bool(r["retention_relevant"]) if "retention_relevant" in keys else bool(r["relevant"]),
            platform_target=r["platform_target"] if "platform_target" in keys else "generic",
            is_synthetic=bool(r["is_synthetic"]) if "is_synthetic" in keys else False,
            mandate_subcluster=r["mandate_subcluster"] if "mandate_subcluster" in keys else "none",
            disconfirming_attribution=r["disconfirming_attribution"] if "disconfirming_attribution" in keys else "unknown",
            rival_hypothesis=r["rival_hypothesis"] if "rival_hypothesis" in keys else "none",
            drop_type=r["drop_type"] or "unknown",
            drop_type_evidence=r["drop_type_evidence"],
            drop_type_confidence=r["drop_type_confidence"] or 0.0,
            sip_status=r["sip_status"] or "unknown",
            sip_status_evidence=r["sip_status_evidence"],
            sip_status_confidence=r["sip_status_confidence"] or 0.0,
            trigger=r["trigger"] or "unknown",
            trigger_evidence=r["trigger_evidence"],
            trigger_confidence=r["trigger_confidence"] or 0.0,
            stated_expectation=r["stated_expectation"] or "unknown",
            stated_expectation_evidence=r["stated_expectation_evidence"],
            stated_expectation_confidence=r["stated_expectation_confidence"] or 0.0,
            what_they_checked=r["what_they_checked"] or "unknown",
            what_they_checked_evidence=r["what_they_checked_evidence"],
            what_they_checked_confidence=r["what_they_checked_confidence"] or 0.0,
            check_frequency=r["check_frequency"] or "unknown",
            check_frequency_evidence=r["check_frequency_evidence"],
            check_frequency_confidence=r["check_frequency_confidence"] or 0.0,
            outside_app_action=r["outside_app_action"] or "unknown",
            outside_app_action_evidence=r["outside_app_action_evidence"],
            outside_app_action_confidence=r["outside_app_action_confidence"] or 0.0,
            influencer=r["influencer"] or "unknown",
            influencer_evidence=r["influencer_evidence"],
            influencer_confidence=r["influencer_confidence"] or 0.0,
            income_stability=r["income_stability"] or "unknown",
            money_source=r["money_source"] or "unknown",
            age_band=r["age_band"] or "unknown",
            lifecycle_month=r["lifecycle_month"],
            in_app_confusion_object=r["in_app_confusion_object"] or "none_or_unknown",
            in_app_confusion_evidence=r["in_app_confusion_evidence"],
            in_app_confusion_confidence=r["in_app_confusion_confidence"] or 0.0,
            language=r["language"] or "en",
            primary_area=r["primary_area"],
            secondary_areas=json.loads(r["secondary_areas"] or "[]"),
            is_continuer=bool(r["is_continuer"]),
            unsure_question=r["unsure_question"],
            problem_types=json.loads(r["problem_types"] or "[]"),
            lifecycle_stage=r["lifecycle_stage"],
            behavioral_signals=json.loads(r["behavioral_signals"] or "[]"),
            emotional_state=r["emotional_state"],
            trigger_types=json.loads(r["trigger_types"] or "[]"),
            retention_risk=RetentionRisk(rr_val) if rr_val else None,
            pattern_type=PatternType(pt_val) if pt_val else None,
            assigned_areas=json.loads(r["assigned_areas"] or "[]"),
            classifier_error=bool(r["classifier_error"]),
            source_platform=SourcePlatform(sp_val) if sp_val else None,
            app_name=r["app_name"],
            date=r["date"],
            upvotes=r["upvotes"] or 0,
        )

    # ── Opportunity Areas ─────────────────────────────────────────────────────

    def upsert_opportunity_area(self, area: OpportunityArea) -> None:
        """Insert or replace an OpportunityArea in SQLite."""
        quotes_json = json.dumps([q.model_dump() for q in area.top_quotes])
        breakdown_json = json.dumps(area.platform_breakdown)
        pri_ci_json = json.dumps(list(area.primary_volume_ci))
        stop_ci_json = json.dumps(list(area.link_to_stopping_ci))

        ev_vol = getattr(area, "evidence_volume", 0) or area.total_volume or area.primary_volume or 0
        tot_vol = area.total_volume or ev_vol
        pri_vol = area.primary_volume or tot_vol
        sec_vol = area.secondary_volume or max(0, tot_vol - pri_vol)
        comp_score = area.composite_score if area.composite_score > 0 else round(area.severity_score * math.log1p(ev_vol) * (area.source_diversity or 1), 2)
        abandon_rate = getattr(area, "abandonment_rate", 0.0) or area.link_to_stopping
        v_count = getattr(area, "voiced_count", 0)
        inf_count = getattr(area, "inferred_count", 0)

        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO opportunity_areas (
                    name, description, primary_volume, primary_volume_ci,
                    secondary_volume, total_volume, evidence_volume, source_diversity,
                    severity_score, link_to_stopping, link_to_stopping_ci,
                    addressability, constraint_compat, composite_score,
                    rank_baseline, rank_severity_heavy, rank_frequency_heavy, rank_retention_heavy,
                    abandonment_rate, voiced_count, inferred_count,
                    top_quotes, platform_breakdown
                ) VALUES (
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?
                )
                """,
                (
                    area.name,
                    area.description,
                    pri_vol,
                    pri_ci_json,
                    sec_vol,
                    tot_vol,
                    ev_vol,
                    area.source_diversity,
                    area.severity_score,
                    area.link_to_stopping,
                    stop_ci_json,
                    area.addressability,
                    area.constraint_compat,
                    comp_score,
                    area.rank_baseline,
                    area.rank_severity_heavy,
                    area.rank_frequency_heavy,
                    area.rank_retention_heavy,
                    abandon_rate,
                    v_count,
                    inf_count,
                    quotes_json,
                    breakdown_json,
                ),
            )

        for q in area.top_quotes:
            import uuid as _uuid
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO quotes
                        (id, area_name, text, source_platform, upvotes, url, evidence_span)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(_uuid.uuid4()),
                        area.name,
                        q.text,
                        q.source_platform,
                        q.upvotes,
                        q.url,
                        q.evidence_span or "",
                    ),
                )

    def get_all_opportunity_areas(self) -> List[dict]:
        """Return all opportunity areas with parsed JSON."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM opportunity_areas ORDER BY composite_score DESC").fetchall()
        areas = []
        for row in rows:
            d = dict(row)
            d["top_quotes"] = json.loads(d.get("top_quotes") or "[]")
            d["platform_breakdown"] = json.loads(d.get("platform_breakdown") or "{}")
            d["primary_volume_ci"] = json.loads(d.get("primary_volume_ci") or "[0.0, 0.0]")
            d["link_to_stopping_ci"] = json.loads(d.get("link_to_stopping_ci") or "[0.0, 0.0]")
            areas.append(d)
        return areas

    def get_raw_texts_and_urls(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Return raw texts and urls mapped by id."""
        with self._conn() as conn:
            rows = conn.execute("SELECT id, text, url FROM raw_items").fetchall()
        return {r["id"]: r["text"] for r in rows}, {r["id"]: r["url"] for r in rows}

    # ── Export utilities ──────────────────────────────────────────────────────

    def export_csv(self, path: str = config.RAW_CSV_PATH) -> str:
        with self._conn() as conn:
            df = pd.read_sql_query("SELECT * FROM raw_items", conn)
        df.to_csv(path, index=False, encoding="utf-8")
        logger.info(f"[raw_store] Exported {len(df)} raw items to {path}")
        return path

    def export_tagged_csv(self, path: str = config.TAGGED_CSV_PATH) -> str:
        with self._conn() as conn:
            df = pd.read_sql_query("SELECT * FROM tagged_items", conn)
        df.to_csv(path, index=False, encoding="utf-8")
        logger.info(f"[raw_store] Exported {len(df)} tagged items to {path}")
        return path

    def export_tagged_json(self, path: str = config.TAGGED_JSON_PATH) -> str:
        with self._conn() as conn:
            df = pd.read_sql_query("SELECT * FROM tagged_items", conn)
        for col in ["problem_types", "behavioral_signals", "trigger_types", "assigned_areas", "secondary_areas"]:
            if col in df.columns:
                df[col] = df[col].apply(lambda v: json.loads(v) if isinstance(v, str) else v)
        records = df.to_dict(orient="records")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        logger.info(f"[raw_store] Exported {len(records)} tagged items to {path}")
        return path

    def export_opportunity_csv(self, path: str = config.OPPORTUNITY_CSV_PATH) -> str:
        with self._conn() as conn:
            df = pd.read_sql_query("SELECT * FROM opportunity_areas", conn)
        df.to_csv(path, index=False, encoding="utf-8")
        logger.info(f"[raw_store] Exported {len(df)} opportunity areas to {path}")
        return path

    def source_summary(self) -> dict:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT source, COUNT(*) as n FROM raw_items GROUP BY source"
            ).fetchall()
        return {row["source"]: row["n"] for row in rows}
