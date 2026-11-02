"""
pipeline/export_bundle.py — Pre-compiles the entire Discovery Engine dataset into a single
high-performance bundle.json for the web application and API.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import sqlite3
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config
from pipeline.raw_store import RawStore
from pipeline.dashboard_data import (
    get_kpi_stats,
    get_opportunity_areas_df,
    load_synthesis_report_markdown,
)
from pipeline.chat_engine import get_corpus_cognitive_metrics


def build_bundle() -> dict:
    """Build unified data bundle for the web application."""
    store = RawStore()

    # 1. KPIs & High-level stats
    kpi_stats = get_kpi_stats()

    # 2. Opportunity Areas
    opp_areas_df = get_opportunity_areas_df()
    opp_areas = opp_areas_df.to_dict(orient="records") if not opp_areas_df.empty else []

    # 3. Behavioral metrics
    behavioral_metrics = get_corpus_cognitive_metrics()

    # 4. Merged Raw + Tagged Items
    items = []
    try:
        with sqlite3.connect(config.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT 
                    r.id, r.source, r.app_name, r.text, r.date, r.upvotes, r.url,
                    t.relevant, t.on_topic, t.retention_relevant, t.sip_status, t.drop_type,
                    t.problem_types, t.lifecycle_stage, t.behavioral_signals,
                    t.emotional_state, t.trigger_types, t.retention_risk,
                    t.pattern_type, t.assigned_areas, t.primary_area
                FROM raw_items r
                LEFT JOIN tagged_items t ON t.raw_item_id = r.id
                ORDER BY r.upvotes DESC
                """
            ).fetchall()

            for r in rows:
                pts = json.loads(r["problem_types"] or "[]") if r["problem_types"] else []
                bs_list = json.loads(r["behavioral_signals"] or "[]") if r["behavioral_signals"] else []
                trigs = json.loads(r["trigger_types"] or "[]") if r["trigger_types"] else []
                areas = json.loads(r["assigned_areas"] or "[]") if r["assigned_areas"] else []

                is_abandoned = (
                    "already_paused" in bs_list
                    or r["retention_risk"] == "already_churned"
                    or r["sip_status"] in ["cancelled", "paused", "lapsed"]
                    or r["drop_type"] in ["voluntary", "involuntary"]
                )

                items.append({
                    "id": r["id"],
                    "source": r["source"],
                    "app_name": r["app_name"] or "",
                    "text": r["text"],
                    "date": r["date"] or "",
                    "upvotes": r["upvotes"] or 0,
                    "url": r["url"] or "",
                    "relevant": bool(r["relevant"]),
                    "on_topic": bool(r["on_topic"]),
                    "retention_relevant": bool(r["retention_relevant"]),
                    "sip_status": r["sip_status"] or "unknown",
                    "drop_type": r["drop_type"] or "unknown",
                    "problem_types": pts,
                    "lifecycle_stage": r["lifecycle_stage"] or "unknown",
                    "behavioral_signals": bs_list,
                    "emotional_state": r["emotional_state"] or "anxious",
                    "trigger_types": trigs,
                    "retention_risk": r["retention_risk"] or "med",
                    "abandoned_app": is_abandoned,
                    "pattern_type": r["pattern_type"] or "voiced",
                    "primary_area": r["primary_area"] or "",
                    "assigned_areas": areas,
                })
    except Exception as e:
        print(f"Error merging items: {e}")

    # 5. Synthesis Report Markdown
    report_markdown = load_synthesis_report_markdown()

    bundle = {
        "kpis": kpi_stats,
        "cognitive_metrics": behavioral_metrics,
        "opportunity_areas": opp_areas,
        "items": items,
        "report_markdown": report_markdown,
    }

    out_path = os.path.join(config.DATA_DIR, "bundle.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)

    print(f"Exported bundle to {out_path} ({len(items)} items, {len(opp_areas)} areas)")
    return bundle


if __name__ == "__main__":
    build_bundle()
