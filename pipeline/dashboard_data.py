"""
pipeline/dashboard_data.py — Data access and analytics layer for Groww SIP Retention Dashboard.
Provides cached queries, aggregations, and fallback logic for all dashboard pages.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

import config
from pipeline.raw_store import RawStore


def get_db_connection() -> sqlite3.Connection:
    """Return a read-only or standard sqlite3 connection with Row factory."""
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_kpi_stats() -> Dict[str, Any]:
    """
    Retrieve headline metrics across raw items, tagged items, and opportunity areas.
    Safe against empty or non-existent tables.
    """
    stats = {
        "total_raw": 0,
        "total_relevant": 0,
        "source_count": 0,
        "total_sources_possible": 6,
        "areas_count": 0,
        "voiced_total": 0,
        "inferred_total": 0,
        "avg_severity": 0.0,
        "has_data": False,
    }

    if not os.path.exists(config.DB_PATH):
        return stats

    try:
        with sqlite3.connect(config.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            try:
                row = cursor.execute(
                    "SELECT COUNT(*) as n, COUNT(DISTINCT source) as sources FROM raw_items"
                ).fetchone()
                if row:
                    stats["total_raw"] = row["n"] or 0
                    stats["source_count"] = row["sources"] or 0
            except sqlite3.OperationalError:
                pass

            try:
                row = cursor.execute(
                    """
                    SELECT 
                        SUM(CASE WHEN on_topic = 1 THEN 1 ELSE 0 END) as on_topic,
                        SUM(CASE WHEN retention_relevant = 1 THEN 1 ELSE 0 END) as retention_relevant,
                        SUM(CASE WHEN relevant = 1 THEN 1 ELSE 0 END) as relevant,
                        SUM(CASE WHEN pattern_type = 'voiced' THEN 1 ELSE 0 END) as voiced,
                        SUM(CASE WHEN pattern_type = 'inferred' THEN 1 ELSE 0 END) as inferred
                    FROM tagged_items
                    WHERE is_synthetic = 0
                    """
                ).fetchone()
                if row and row["relevant"] is not None:
                    stats["total_on_topic"] = row["on_topic"] or 0
                    stats["total_retention_relevant"] = row["retention_relevant"] or 0
                    stats["total_relevant"] = row["retention_relevant"] or row["relevant"] or 0
                    stats["voiced_total"] = row["voiced"] or 0
                    stats["inferred_total"] = row["inferred"] or 0
            except sqlite3.OperationalError:
                pass

            try:
                row = cursor.execute(
                    "SELECT COUNT(*) as n, AVG(severity_score) as avg_sev FROM opportunity_areas"
                ).fetchone()
                if row and row["n"]:
                    stats["areas_count"] = row["n"] or 0
                    stats["avg_severity"] = round(row["avg_sev"] or 0.0, 2)
            except sqlite3.OperationalError:
                pass

        stats["has_data"] = stats["total_raw"] > 0
    except Exception as e:
        logger.warning(f"[dashboard_data] Error fetching KPI stats: {e}")

    return stats


def get_platform_counts() -> Dict[str, int]:
    """Retrieve raw feedback counts grouped by source platform."""
    counts = {
        "play_store": 0,
        "reddit": 0,
        "app_store": 0,
        "help_forum": 0,
        "youtube": 0,
        "web": 0,
    }
    if not os.path.exists(config.DB_PATH):
        return counts
    try:
        with sqlite3.connect(config.DB_PATH) as conn:
            cursor = conn.cursor()
            rows = cursor.execute("SELECT source, COUNT(*) as cnt FROM raw_items GROUP BY source").fetchall()
            for src, cnt in rows:
                if src in counts:
                    counts[src] = cnt
                elif src:
                    counts[src] = cnt
    except Exception as e:
        logger.warning(f"[dashboard_data] Error fetching platform counts: {e}")
    return counts


def get_opportunity_areas_df() -> pd.DataFrame:
    """
    Fetch all opportunity areas from SQLite and return as a sorted DataFrame.
    Includes composite score calculation: severity × log1p(volume) × diversity.
    """
    store = RawStore()
    areas = store.get_all_opportunity_areas()
    if not areas:
        return pd.DataFrame()

    records = []
    for a in areas:
        vol = a.get("evidence_volume", 0) or a.get("total_volume", 0) or a.get("primary_volume", 0) or 0
        if vol == 0 and a.get("platform_breakdown"):
            vol = sum(a["platform_breakdown"].values())
        if vol == 0 and a.get("top_quotes"):
            vol = len(a["top_quotes"])

        sev = a.get("severity_score", 0.0) or 0.0
        div = a.get("source_diversity", 0) or (len(a.get("platform_breakdown", {})) if a.get("platform_breakdown") else 1)
        voiced = a.get("voiced_count", 0) or 0
        inferred = a.get("inferred_count", 0) or 0
        abandonment = a.get("abandonment_rate", 0.0) or a.get("link_to_stopping", 0.0) or 0.0

        composite_score = a.get("composite_score", 0.0) or round(sev * math.log1p(vol) * div, 2)

        records.append({
            "Opportunity Area": a.get("name", "Unnamed"),
            "Description": a.get("description", ""),
            "Evidence Volume": vol,
            "Source Diversity": f"{div}/6",
            "Diversity Raw": div,
            "Severity Score": round(sev, 2),
            "Abandonment Rate": f"{round(abandonment * 100, 1)}%",
            "Abandonment Raw": abandonment,
            "Voiced Count": voiced,
            "Inferred Count": inferred,
            "Composite Score": composite_score,
            "Top Quotes": a.get("top_quotes", []),
            "Platform Breakdown": a.get("platform_breakdown", {}),
        })

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values(by=["Severity Score", "Evidence Volume"], ascending=[False, False]).reset_index(drop=True)
    return df


def get_opportunity_area_detail(area_name: str) -> Dict[str, Any]:
    """
    Fetch comprehensive details for a single opportunity area:
    - Metadata and scores
    - Lifecycle Stages × Platform matrix for heatmap
    - Quotes with verbatim text, upvotes, and URLs
    - Voiced vs Inferred breakdown
    """
    detail: Dict[str, Any] = {
        "name": area_name,
        "description": "",
        "evidence_volume": 0,
        "source_diversity": 0,
        "severity_score": 0.0,
        "abandonment_rate": 0.0,
        "voiced_count": 0,
        "inferred_count": 0,
        "quotes": [],
        "heatmap_df": pd.DataFrame(),
        "stages_present": [],
    }

    if not os.path.exists(config.DB_PATH):
        return detail

    try:
        with sqlite3.connect(config.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            row = cursor.execute(
                "SELECT * FROM opportunity_areas WHERE name = ?", (area_name,)
            ).fetchone()
            if row:
                detail["name"] = row["name"]
                detail["description"] = row["description"] or ""
                detail["evidence_volume"] = row["evidence_volume"] or 0
                detail["source_diversity"] = row["source_diversity"] or 0
                detail["severity_score"] = round(row["severity_score"] or 0.0, 2)
                detail["abandonment_rate"] = round((row["abandonment_rate"] or 0.0) * 100, 1)
                detail["voiced_count"] = row["voiced_count"] or 0
                detail["inferred_count"] = row["inferred_count"] or 0
                detail["top_quotes"] = json.loads(row["top_quotes"] or "[]")

            search_pattern = f'%"{area_name}"%'
            tagged_rows = cursor.execute(
                """
                SELECT t.lifecycle_stage, t.source_platform, t.pattern_type, t.upvotes,
                       r.text, r.url, r.id as raw_id
                FROM tagged_items t
                JOIN raw_items r ON r.id = t.raw_item_id
                WHERE t.assigned_areas LIKE ?
                ORDER BY t.upvotes DESC
                LIMIT 500
                """,
                (search_pattern,),
            ).fetchall()

            platforms = ["play_store", "app_store", "reddit", "youtube", "help_forum", "web"]
            stages = ["first_month", "early_1_3m", "mid_4_6m", "late_7_12m", "post_dropout"]
            stage_labels = {
                "first_month": "Month 1 (Onboarding)",
                "early_1_3m": "Months 1–3 (Early Volatility)",
                "mid_4_6m": "Months 4–6 (Statement Fatigue)",
                "late_7_12m": "Months 7–12 (Habit Maturation)",
                "post_dropout": "Post-Dropout (Lapsed)",
            }

            counts = {stage_labels[s]: {p: 0 for p in platforms} for s in stages}
            stages_found = set()
            quotes_list = []

            for tr in tagged_rows:
                src = tr["source_platform"]
                ls = tr["lifecycle_stage"]
                if ls and ls in stage_labels:
                    stages_found.add(ls)
                    if src in counts[stage_labels[ls]]:
                        counts[stage_labels[ls]][src] += 1

                quotes_list.append({
                    "text": tr["text"],
                    "source": tr["source_platform"],
                    "upvotes": tr["upvotes"] or 0,
                    "url": tr["url"],
                })

            detail["stages_present"] = sorted(list(stages_found))
            detail["heatmap_df"] = pd.DataFrame.from_dict(counts, orient="index")
            detail["quotes"] = quotes_list if quotes_list else detail.get("top_quotes", [])

    except Exception as e:
        logger.warning(f"[dashboard_data] Error building area detail for '{area_name}': {e}")

    return detail


def get_filtered_corpus(
    sources: Optional[List[str]] = None,
    problem_types: Optional[List[str]] = None,
    lifecycle_stages: Optional[List[str]] = None,
    retention_risks: Optional[List[str]] = None,
    search_query: Optional[str] = None,
    search_mode: str = "keyword",
    page: int = 1,
    page_size: int = 50,
) -> Tuple[pd.DataFrame, int, pd.DataFrame]:
    """
    Query the corpus with multi-select filters and keyword/semantic search.
    Returns:
        (page_df, total_matched_count, full_export_df)
    """
    empty_df = pd.DataFrame(
        columns=[
            "ID", "Source", "Feedback Text", "Problem Types",
            "Lifecycle Stage", "Behavioral Signals", "Retention Risk",
            "Pattern", "Assigned Areas", "Upvotes", "URL", "Date"
        ]
    )
    if not os.path.exists(config.DB_PATH):
        return empty_df, 0, empty_df

    matched_ids: Optional[List[str]] = None

    if search_query and search_query.strip() and search_mode == "semantic":
        try:
            from pipeline.embedder import Embedder
            embedder = Embedder()
            if embedder.count() > 0:
                results = embedder.query_similar(search_query.strip(), n=250)
                matched_ids = [r["id"] for r in results]
                if not matched_ids:
                    matched_ids = ["__NO_MATCH__"]
        except Exception as e:
            logger.info(f"[dashboard_data] Semantic search fallback to keyword: {e}")
            search_mode = "keyword"

    where_clauses: List[str] = []
    params: List[Any] = []

    if sources:
        placeholders = ",".join("?" for _ in sources)
        where_clauses.append(f"r.source IN ({placeholders})")
        params.extend(sources)

    if retention_risks:
        placeholders = ",".join("?" for _ in retention_risks)
        where_clauses.append(f"t.retention_risk IN ({placeholders})")
        params.extend(retention_risks)

    if lifecycle_stages:
        placeholders = ",".join("?" for _ in lifecycle_stages)
        where_clauses.append(f"t.lifecycle_stage IN ({placeholders})")
        params.extend(lifecycle_stages)

    if problem_types:
        sub_clauses = []
        for pt in problem_types:
            sub_clauses.append("t.problem_types LIKE ?")
            params.append(f'%"{pt}"%')
        where_clauses.append(f"({' OR '.join(sub_clauses)})")

    if matched_ids is not None:
        placeholders = ",".join("?" for _ in matched_ids)
        where_clauses.append(f"r.id IN ({placeholders})")
        params.extend(matched_ids)
    elif search_query and search_query.strip() and search_mode == "keyword":
        where_clauses.append("r.text LIKE ?")
        params.append(f"%{search_query.strip()}%")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    base_from = """
        FROM raw_items r
        LEFT JOIN tagged_items t ON t.raw_item_id = r.id
    """

    count_sql = f"SELECT COUNT(*) {base_from} {where_sql}"

    select_sql = f"""
        SELECT 
            r.id,
            r.source,
            r.text,
            r.date,
            r.upvotes,
            r.url,
            t.relevant,
            t.problem_types,
            t.lifecycle_stage,
            t.behavioral_signals,
            t.retention_risk,
            t.pattern_type,
            t.assigned_areas
        {base_from}
        {where_sql}
        ORDER BY r.upvotes DESC, r.date DESC
    """

    try:
        with sqlite3.connect(config.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            total_count = cursor.execute(count_sql, params).fetchone()[0]

            if total_count == 0:
                return empty_df, 0, empty_df

            export_rows = cursor.execute(f"{select_sql} LIMIT 5000", params).fetchall()

            offset = max(0, (page - 1) * page_size)
            page_rows = cursor.execute(
                f"{select_sql} LIMIT ? OFFSET ?", params + [page_size, offset]
            ).fetchall()

        def parse_row(r: sqlite3.Row) -> dict:
            pts = json.loads(r["problem_types"] or "[]") if r["problem_types"] else []
            bs_list = json.loads(r["behavioral_signals"] or "[]") if r["behavioral_signals"] else []
            areas = json.loads(r["assigned_areas"] or "[]") if r["assigned_areas"] else []
            return {
                "ID": r["id"],
                "Source": r["source"],
                "Feedback Text": r["text"],
                "Problem Types": ", ".join(pts) if pts else "—",
                "Lifecycle Stage": (r["lifecycle_stage"] or "—").replace("_", " ").title(),
                "Behavioral Signals": ", ".join(bs_list) if bs_list else "—",
                "Retention Risk": (r["retention_risk"] or "—").replace("_", " ").title(),
                "Pattern": (r["pattern_type"] or "—").capitalize(),
                "Assigned Areas": ", ".join(areas) if areas else "—",
                "Upvotes": r["upvotes"] or 0,
                "URL": r["url"] or "",
                "Date": r["date"] or "",
            }

        page_df = pd.DataFrame([parse_row(r) for r in page_rows])
        export_df = pd.DataFrame([parse_row(r) for r in export_rows])

        return page_df, total_count, export_df

    except Exception as e:
        logger.warning(f"[dashboard_data] Error querying filtered corpus: {e}")
        return empty_df, 0, empty_df


def load_synthesis_report_markdown() -> str:
    """
    Read reports/synthesis_report.md or return dynamic preview.
    """
    report_path = config.SYNTHESIS_REPORT_PATH
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"[dashboard_data] Error reading report file: {e}")

    kpis = get_kpi_stats()
    areas_df = get_opportunity_areas_df()

    preview = [
        "# 📑 Groww SIP Retention Research — Executive Synthesis Report",
        "",
        "> **Objective:** Increase 12-Month Active SIP Retention for First-Time Mutual Fund Investors.",
        "",
        "## Executive Overview",
        f"- **Total Evidence Corpus:** {kpis['total_raw']:,} raw feedback items collected across {kpis['source_count']}/6 channels.",
        f"- **Domain Relevant Signals:** {kpis['total_relevant']:,} items classified as specific SIP investor friction cases.",
        f"- **Opportunity Clusters Identified:** {kpis['areas_count']} opportunity areas scored across retention severity, volume, and diversity.",
        "",
        "## Opportunity Areas Ranking Summary",
        "",
    ]

    if not areas_df.empty:
        summary_df = areas_df[[
            "Opportunity Area", "Composite Score", "Evidence Volume",
            "Severity Score", "Abandonment Rate", "Source Diversity"
        ]]
        try:
            preview.append(summary_df.to_markdown(index=False))
        except Exception:
            headers = list(summary_df.columns)
            preview.append("| " + " | ".join(headers) + " |")
            preview.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for _, row in summary_df.iterrows():
                preview.append("| " + " | ".join(str(val) for val in row.values) + " |")
    else:
        preview.append(
            "_No opportunity clusters computed yet. Execute `python run_pipeline.py --step all` to build clusters._"
        )

    return "\n".join(preview)


def inject_custom_css():
    """Inject cohesive Groww Design System aesthetic with high-contrast, WCAG-compliant colors."""
    import streamlit as st
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        
        :root {
            --groww-green: #00D09C;
            --groww-green-hover: #00B386;
            --groww-green-soft: #E6FAF5;
            --groww-navy: #121623;
            --groww-navy-surface: #1E2235;
            --groww-navy-light: #2A324B;
            --groww-red: #EB5B56;
            --groww-red-soft: #FDEEED;
            --groww-amber: #F7A800;
            --groww-amber-soft: #FEF6E6;
            --groww-blue: #2563EB;
            --groww-blue-soft: #EFF6FF;
            --canvas-bg: #F4F6F8;
            --card-bg: #ffffff;
            --card-border: #E5E7EB;
            --text-dark: #111827;
            --text-muted: #4B5563;
        }

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        .stApp {
            background-color: var(--canvas-bg);
            color: var(--text-dark);
        }

        /* ── Hide Streamlit Default Multipage Navigation in Sidebar ── */
        [data-testid="stSidebarNav"],
        [data-testid="stSidebarNavItems"],
        [data-testid="stSidebarNavSeparator"],
        div[data-testid="stSidebarNav"],
        ul[data-testid="stSidebarNavItems"] {
            display: none !important;
        }

        /* ── Sidebar: Groww Dark Navy Theme (High-Contrast White Text) ── */
        section[data-testid="stSidebar"] {
            background-color: #121623 !important;
            border-right: 1px solid rgba(255, 255, 255, 0.08);
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] p:not(button p):not([data-testid="stBaseButton-secondary"] p):not([data-testid="stBaseButton-primary"] p),
        section[data-testid="stSidebar"] span:not([data-baseweb="tag"] span):not(button span):not([data-testid="stBaseButton-secondary"] span):not([data-testid="stBaseButton-primary"] span) {
            color: #FFFFFF !important;
        }
        section[data-testid="stSidebar"] label[data-testid="stWidgetLabel"] {
            color: #94A3B8 !important;
            font-size: 0.78rem !important;
            font-weight: 700 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.06em !important;
        }
        /* Sidebar Inputs: Dark surface with crisp white text */
        section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
            background-color: #1E2235 !important;
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
            color: #FFFFFF !important;
        }
        section[data-testid="stSidebar"] div[data-baseweb="select"] span {
            color: #FFFFFF !important;
        }
        section[data-testid="stSidebar"] div[data-baseweb="select"] input {
            color: #FFFFFF !important;
        }
        section[data-testid="stSidebar"] div[data-baseweb="select"] svg {
            fill: #94A3B8 !important;
        }
        /* Multiselect selected chips in sidebar */
        section[data-testid="stSidebar"] span[data-baseweb="tag"] {
            background-color: #2A324B !important;
            border: 1px solid #475569 !important;
            border-radius: 14px !important;
            padding: 2px 8px !important;
        }
        section[data-testid="stSidebar"] span[data-baseweb="tag"] span {
            color: #FFFFFF !important;
            font-weight: 600 !important;
            font-size: 0.78rem !important;
        }

        /* ── BaseWeb Dropdown Menus & Popovers (Clean Light Mode Popup) ── */
        div[data-baseweb="popover"],
        div[data-baseweb="menu"],
        ul[role="listbox"] {
            background-color: #FFFFFF !important;
            border: 1px solid #E5E7EB !important;
            border-radius: 8px !important;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.12) !important;
        }
        ul[role="listbox"] li[role="option"] {
            color: #111827 !important;
            background-color: #FFFFFF !important;
            font-size: 0.9rem !important;
            font-weight: 500 !important;
            padding: 8px 14px !important;
        }
        ul[role="listbox"] li[role="option"]:hover,
        ul[role="listbox"] li[aria-selected="true"] {
            background-color: #E6FAF5 !important;
            color: #008765 !important;
            font-weight: 700 !important;
        }

        /* ── Primary Buttons ── */
        .stButton > button {
            border-radius: 8px !important;
            font-weight: 600 !important;
            transition: all 0.2s ease !important;
        }
        .stButton > button[kind="primary"],
        button[data-testid="stBaseButton-primary"] {
            background-color: #00D09C !important;
            color: #0B1E19 !important;
            border: none !important;
            font-weight: 700 !important;
            box-shadow: 0 2px 8px rgba(0, 208, 156, 0.25) !important;
        }
        .stButton > button[kind="primary"] p,
        .stButton > button[kind="primary"] span,
        button[data-testid="stBaseButton-primary"] p,
        button[data-testid="stBaseButton-primary"] span {
            color: #0B1E19 !important;
            font-weight: 700 !important;
        }
        .stButton > button[kind="primary"]:hover,
        button[data-testid="stBaseButton-primary"]:hover {
            background-color: #00B386 !important;
            box-shadow: 0 4px 12px rgba(0, 208, 156, 0.35) !important;
        }

        /* ── Sidebar Secondary / Reset Button (Dark Theme - NO WHITE ON WHITE) ── */
        section[data-testid="stSidebar"] .stButton > button:not([kind="primary"]),
        section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"],
        section[data-testid="stSidebar"] button[kind="secondary"] {
            background-color: #1E2235 !important;
            color: #F1F5F9 !important;
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
        }
        section[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) p,
        section[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) span,
        section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] p,
        section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] span,
        section[data-testid="stSidebar"] button[kind="secondary"] p,
        section[data-testid="stSidebar"] button[kind="secondary"] span {
            color: #F1F5F9 !important;
            font-weight: 600 !important;
        }
        section[data-testid="stSidebar"] .stButton > button:not([kind="primary"]):hover,
        section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover,
        section[data-testid="stSidebar"] button[kind="secondary"]:hover {
            border-color: #00D09C !important;
            background-color: #272F47 !important;
        }
        section[data-testid="stSidebar"] .stButton > button:not([kind="primary"]):hover p,
        section[data-testid="stSidebar"] .stButton > button:not([kind="primary"]):hover span,
        section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover p,
        section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover span {
            color: #00D09C !important;
        }

        /* ── Main Canvas Secondary Buttons ── */
        .stButton > button:not([kind="primary"]),
        button[data-testid="stBaseButton-secondary"],
        button[kind="secondary"] {
            background-color: #FFFFFF !important;
            color: #111827 !important;
            border: 1px solid #D1D5DB !important;
        }
        .stButton > button:not([kind="primary"]) p,
        .stButton > button:not([kind="primary"]) span,
        button[data-testid="stBaseButton-secondary"] p,
        button[data-testid="stBaseButton-secondary"] span,
        button[kind="secondary"] p,
        button[kind="secondary"] span {
            color: #111827 !important;
            font-weight: 600 !important;
        }
        .stButton > button:not([kind="primary"]):hover,
        button[data-testid="stBaseButton-secondary"]:hover,
        button[kind="secondary"]:hover {
            border-color: #00D09C !important;
            color: #008765 !important;
            background-color: #F9FAFB !important;
        }
        .stButton > button:not([kind="primary"]):hover p,
        .stButton > button:not([kind="primary"]):hover span,
        button[data-testid="stBaseButton-secondary"]:hover p,
        button[data-testid="stBaseButton-secondary"]:hover span {
            color: #008765 !important;
        }

        /* ── Prompt Chips in Tab 4 AI Assistant ── */
        div[data-testid="column"] button[key*="chip_btn"] {
            border-radius: 20px !important;
            background: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            color: #334155 !important;
            font-size: 0.78rem !important;
            font-weight: 500 !important;
            padding: 4px 12px !important;
            white-space: nowrap !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
            transition: all 0.18s ease !important;
        }
        div[data-testid="column"] button[key*="chip_btn"]:hover {
            background-color: #F8FAFC !important;
            border-color: #2563EB !important;
            color: #2563EB !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.12) !important;
        }
        div[data-testid="column"] button[key*="chip_btn"]:hover p,
        div[data-testid="column"] button[key*="chip_btn"]:hover span {
            color: #2563EB !important;
        }

        /* ── Groww KPI Cards ── */
        .gp-kpi-card {
            background: #ffffff !important;
            border: 1px solid #E5E7EB !important;
            border-radius: 12px !important;
            padding: 20px 24px !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04) !important;
            position: relative;
            overflow: hidden;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .gp-kpi-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08) !important;
        }
        .gp-kpi-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
        }
        .kpi-blue::before { background: #00D09C !important; }
        .kpi-red::before { background: #EB5B56 !important; }
        .kpi-yellow::before { background: #F7A800 !important; }
        .kpi-green::before { background: #2563EB !important; }
        .kpi-purple::before { background: #8B5CF6 !important; }

        .gp-kpi-label {
            font-size: 0.8rem !important;
            font-weight: 700 !important;
            color: #4B5563 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.06em !important;
            margin-bottom: 6px !important;
        }
        .gp-kpi-value {
            font-size: 2.2rem !important;
            font-weight: 800 !important;
            color: #111827 !important;
            line-height: 1.1 !important;
        }
        .gp-kpi-subtext {
            font-size: 0.82rem !important;
            color: #4B5563 !important;
            margin-top: 6px !important;
            font-weight: 500 !important;
        }

        /* ── Opportunity Spaces Cards ── */
        .gp-opp-card {
            background: #ffffff !important;
            border: 1px solid #E5E7EB !important;
            border-radius: 12px !important;
            padding: 20px !important;
            margin-bottom: 16px !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03) !important;
            height: 100% !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: space-between !important;
            transition: all 0.2s ease !important;
        }
        .gp-opp-card:hover {
            border-color: #00D09C !important;
            box-shadow: 0 8px 24px rgba(0, 208, 156, 0.18) !important;
            transform: translateY(-2px) !important;
        }
        .gp-opp-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .gp-rank-pill {
            background: #121623 !important;
            color: #ffffff !important;
            font-size: 0.75rem !important;
            font-weight: 700 !important;
            padding: 3px 10px !important;
            border-radius: 20px !important;
        }
        .gp-opp-title {
            font-size: 1.05rem !important;
            font-weight: 700 !important;
            color: #111827 !important;
            margin-bottom: 8px !important;
            line-height: 1.35 !important;
        }
        .gp-opp-desc {
            font-size: 0.86rem !important;
            color: #4B5563 !important;
            line-height: 1.55 !important;
            margin-bottom: 16px !important;
            flex-grow: 1 !important;
        }
        .gp-opp-metrics {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-top: 1px solid #F3F4F6;
            padding-top: 12px;
            font-size: 0.8rem;
            color: #374151 !important;
        }

        /* ── Ground-Truth Quote & Evidence Cards ── */
        .evidence-card, .quote-card {
            background: #ffffff !important;
            border: 1px solid #E5E7EB !important;
            border-left: 4px solid #00D09C !important;
            border-radius: 8px !important;
            padding: 14px 16px !important;
            margin-bottom: 10px !important;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03) !important;
        }
        .quote-text {
            font-size: 0.92rem !important;
            line-height: 1.6 !important;
            color: #111827 !important;
            font-style: italic !important;
            margin-bottom: 8px !important;
        }
        .quote-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            font-size: 0.78rem !important;
            color: #4B5563 !important;
            border-top: 1px solid #F3F4F6;
            padding-top: 8px;
        }
        .quote-meta span b {
            color: #111827 !important;
        }

        /* ── Badges & Pill Tags ── */
        .gp-pill {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 16px;
            font-size: 0.76rem;
            font-weight: 700;
            margin-right: 4px;
            margin-bottom: 4px;
        }
        .pill-high { background: #FDEEED !important; color: #B91C1C !important; border: 1px solid #FECACA !important; }
        .pill-med { background: #FEF6E6 !important; color: #B45309 !important; border: 1px solid #FDE68A !important; }
        .pill-low { background: #E6FAF5 !important; color: #047857 !important; border: 1px solid #A7F3D0 !important; }
        
        .stage-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 16px;
            font-size: 0.78rem;
            font-weight: 700;
            margin-right: 6px;
            margin-bottom: 4px;
        }
        .badge-stage-a { background: #E6FAF5 !important; color: #047857 !important; border: 1px solid #A7F3D0 !important; }
        .badge-stage-b { background: #EFF6FF !important; color: #1D4ED8 !important; border: 1px solid #BFDBFE !important; }
        .badge-stage-c { background: #FFFBEB !important; color: #B45309 !important; border: 1px solid #FDE68A !important; }
        .badge-stage-d { background: #F5F3FF !important; color: #6D28D9 !important; border: 1px solid #DDD6FE !important; }

        /* ── Pipeline Status Card (Intuitive Fintech Telemetry) ── */
        .pipeline-status-card {
            background: linear-gradient(180deg, #1A2035 0%, #121623 100%) !important;
            border: 1px solid rgba(0, 208, 156, 0.25) !important;
            border-radius: 12px !important;
            padding: 14px 16px !important;
            margin-top: 20px !important;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25) !important;
            position: relative;
            overflow: hidden;
        }
        .pipeline-status-card::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 2px;
            background: linear-gradient(90deg, #00D09C 0%, #5468FF 100%);
        }
        .psc-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }
        .psc-title-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .psc-title {
            font-size: 0.72rem !important;
            font-weight: 800 !important;
            color: #94A3B8 !important;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .psc-badge {
            background: rgba(0, 208, 156, 0.15);
            color: #00D09C !important;
            font-size: 0.68rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 12px;
            border: 1px solid rgba(0, 208, 156, 0.3);
            letter-spacing: 0.04em;
        }
        .psc-live-pulse {
            width: 8px;
            height: 8px;
            background-color: #00D09C;
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 0 0 rgba(0, 208, 156, 0.7);
            animation: pulse-green 2s infinite;
        }
        @keyframes pulse-green {
            0% {
                transform: scale(0.95);
                box-shadow: 0 0 0 0 rgba(0, 208, 156, 0.7);
            }
            70% {
                transform: scale(1);
                box-shadow: 0 0 0 6px rgba(0, 208, 156, 0);
            }
            100% {
                transform: scale(0.95);
                box-shadow: 0 0 0 0 rgba(0, 208, 156, 0);
            }
        }
        .psc-metrics-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 10px;
        }
        .psc-metric-item {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 8px;
            padding: 8px 10px;
        }
        .psc-metric-label {
            font-size: 0.65rem !important;
            font-weight: 700 !important;
            color: #94A3B8 !important;
            letter-spacing: 0.04em;
            margin-bottom: 2px;
        }
        .psc-metric-val {
            font-size: 1.1rem !important;
            font-weight: 800 !important;
            color: #FFFFFF !important;
            line-height: 1.2;
        }
        .psc-metric-sub {
            font-size: 0.65rem !important;
            color: #64748B !important;
            margin-top: 2px;
        }
        .psc-verification {
            background: rgba(255, 255, 255, 0.02);
            border-radius: 6px;
            padding: 6px 8px;
            margin-bottom: 10px;
            border: 1px dashed rgba(255, 255, 255, 0.08);
        }
        .psc-verify-row {
            display: flex;
            justify-content: space-between;
            font-size: 0.72rem !important;
            line-height: 1.4;
        }
        .psc-check {
            color: #CBD5E1 !important;
            font-weight: 500 !important;
        }
        .psc-verify-text {
            color: #00D09C !important;
            font-weight: 700 !important;
        }
        .psc-goal-banner {
            background: linear-gradient(135deg, rgba(0, 208, 156, 0.12) 0%, rgba(84, 104, 255, 0.12) 100%);
            border: 1px solid rgba(0, 208, 156, 0.2);
            border-radius: 8px;
            padding: 8px 10px;
        }
        .psc-goal-title {
            font-size: 0.72rem !important;
            font-weight: 700 !important;
            color: #00D09C !important;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .psc-goal-text {
            font-size: 0.72rem !important;
            color: #E2E8F0 !important;
            margin-top: 2px;
            font-weight: 500 !important;
        }

        /* ── Tabs Navigation ── */
        .stTabs [data-baseweb="tab-list"] {
            gap: 24px;
            background-color: transparent;
            border-bottom: 2px solid #E5E7EB;
            padding-bottom: 2px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 48px;
            font-size: 0.95rem;
            font-weight: 600;
            color: #4B5563 !important;
            border: none !important;
            background-color: transparent !important;
            padding: 0 4px;
        }
        .stTabs [aria-selected="true"] {
            color: #008765 !important;
            border-bottom: 3px solid #00D09C !important;
            font-weight: 700 !important;
        }

        /* ── Chat Messages (High Contrast) ── */
        div[data-testid="stChatMessage"] {
            background-color: #FFFFFF !important;
            border: 1px solid #E5E7EB !important;
            border-radius: 10px !important;
            color: #111827 !important;
            padding: 14px 18px !important;
            margin-bottom: 12px !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02) !important;
        }
        div[data-testid="stChatMessage"] p,
        div[data-testid="stChatMessage"] li,
        div[data-testid="stChatMessage"] strong,
        div[data-testid="stChatMessage"] span {
            color: #111827 !important;
        }
        div[data-testid="stChatMessage"] blockquote {
            border-left: 3px solid #00D09C !important;
            background-color: #F8FAFC !important;
            padding: 8px 12px !important;
            color: #374151 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

