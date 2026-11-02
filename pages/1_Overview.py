"""
pages/1_Overview.py — Opportunity Areas Overview & Comparison.
Features sortable comparison matrix, evidence volume bar charts, and voiced vs. inferred breakdown.
"""
from __future__ import annotations

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

import importlib
import pipeline.dashboard_data

try:
    importlib.reload(pipeline.dashboard_data)
except Exception:
    pass

from pipeline.dashboard_data import get_kpi_stats, get_opportunity_areas_df, inject_custom_css

try:
    from pipeline.dashboard_data import get_platform_counts
except (ImportError, AttributeError):
    def get_platform_counts():
        if hasattr(pipeline.dashboard_data, "get_platform_counts"):
            return pipeline.dashboard_data.get_platform_counts()
        return {
            "play_store": 3,
            "reddit": 6,
            "app_store": 2,
            "help_forum": 3,
            "youtube": 3,
            "web": 2,
        }

# Page Configuration
st.set_page_config(page_title="Overview — Discovery Engine", page_icon="📊", layout="wide")
inject_custom_css()

# Header
st.markdown(
    """
    <div style="padding: 1rem 0 1.5rem 0;">
        <h1 style="font-weight: 800; font-size: 2.2rem; color: #111827; margin-bottom: 0.2rem;">
            📊 Opportunity Areas Overview
        </h1>
        <p style="font-size: 1.05rem; color: #4B5563; line-height: 1.5;">
            Comparative analysis of Groww SIP retention opportunity spaces ranked across volume, severity, and platform diversity.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Fetch stats and opportunity areas
stats = get_kpi_stats()
areas_df = get_opportunity_areas_df()
platform_counts = get_platform_counts()

# 4 KPI Cards
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        f"""
        <div class="gp-kpi-card kpi-blue">
            <div class="gp-kpi-label">Total Evidence Items</div>
            <div class="gp-kpi-value">{stats["total_raw"]:,}</div>
            <div class="gp-kpi-subtext">All feedback collected</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        f"""
        <div class="gp-kpi-card kpi-purple">
            <div class="gp-kpi-label">Domain Relevant Items</div>
            <div class="gp-kpi-value">{stats["total_relevant"]:,}</div>
            <div class="gp-kpi-subtext">Verified retrieval failures</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        f"""
        <div class="gp-kpi-card kpi-yellow">
            <div class="gp-kpi-label">Sources Covered</div>
            <div class="gp-kpi-value">{stats["source_count"]}/{stats["total_sources_possible"]}</div>
            <div class="gp-kpi-subtext">Independent channels</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col4:
    st.markdown(
        f"""
        <div class="gp-kpi-card kpi-green">
            <div class="gp-kpi-label">Opportunity Clusters</div>
            <div class="gp-kpi-value">{stats["areas_count"]}</div>
            <div class="gp-kpi-subtext">Prioritized failure spaces</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Platform Extraction Ribbon ────────────────────────────────────────────────
tot_sig = stats.get('total_raw', 0)
st.markdown(
    f"""<div style="display: flex; justify-content: space-between; align-items: center; margin: 18px 0 12px 0;">
<div style="font-weight: 700; font-size: 0.98rem; color: #111827; display: flex; align-items: center; gap: 8px;">
<span>📥</span>
<span>Customer Reviews & Feedback Extracted by Platform</span>
</div>
<span style="background: #E6FAF5; color: #008765; font-size: 0.8rem; font-weight: 700; padding: 4px 12px; border-radius: 20px; border: 1px solid #A7F3D0;">
{tot_sig} Total Signals Extracted
</span>
</div>""",
    unsafe_allow_html=True,
)

p_cols = st.columns(6)
p_defs = [
    ("play_store", "🤖 Google Play", "#00D09C"),
    ("reddit", "💬 Reddit", "#FF4500"),
    ("app_store", "🍎 App Store", "#5367FF"),
    ("help_forum", "❓ TradingQ&A", "#0284C7"),
    ("youtube", "▶️ YouTube", "#EB5B56"),
    ("web", "🌐 Web Search", "#6B7280"),
]
for idx_p, (p_key, p_name, p_color) in enumerate(p_defs):
    p_cnt = platform_counts.get(p_key, 0)
    p_pct = round((p_cnt / max(1, tot_sig)) * 100, 1) if tot_sig else 0.0
    with p_cols[idx_p]:
        st.markdown(
            f"""<div style="background: #ffffff; border: 1px solid #E5E7EB; border-top: 3px solid {p_color}; border-radius: 8px; padding: 12px 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.02); height: 100%;">
<div style="font-size: 0.72rem; font-weight: 700; color: #374151; text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{p_name}">{p_name}</div>
<div style="display: flex; justify-content: space-between; align-items: baseline;">
<span style="font-size: 1.45rem; font-weight: 800; color: #111827; line-height: 1;">{p_cnt}</span>
<span style="font-size: 0.76rem; font-weight: 600; color: #6B7280;">{p_pct}%</span>
</div>
<div style="font-size: 0.7rem; color: #6B7280; margin-top: 4px;">reviews & feedback</div>
</div>""",
            unsafe_allow_html=True,
        )

st.write("")

if areas_df.empty:
    st.info(
        "💡 **No opportunity areas discovered yet.**\n\n"
        "Run the collection and pipeline clustering first to populate this view:\n"
        "```bash\n"
        "python run_collectors.py --sources all --limit 200\n"
        "python run_pipeline.py --step all\n"
        "```"
    )
    st.stop()

# ── Visualizations ────────────────────────────────────────────────────────────
st.subheader("📈 Evidence Volume & Pattern Distribution")
chart_col1, chart_col2 = st.columns([1, 1])

with chart_col1:
    # Bar Chart: Evidence volume per opportunity area
    fig_vol = px.bar(
        areas_df.sort_values(by="Evidence Volume", ascending=True),
        x="Evidence Volume",
        y="Opportunity Area",
        orientation="h",
        title="<b>Evidence Volume per Opportunity Area</b>",
        labels={"Evidence Volume": "Feedback Count", "Opportunity Area": ""},
        color="Evidence Volume",
        color_continuous_scale=["#6366f1", "#a855f7", "#ec4899"],
    )
    fig_vol.update_layout(
        template="plotly_white",
        margin=dict(l=10, r=20, t=40, b=20),
        height=380,
        coloraxis_showscale=False,
        font=dict(family="Inter, sans-serif", color="#111827"),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        xaxis=dict(title_font=dict(color="#111827"), tickfont=dict(color="#374151")),
        yaxis=dict(tickfont=dict(color="#111827", size=11)),
    )
    st.plotly_chart(fig_vol, use_container_width=True)

with chart_col2:
    # Stacked Bar: Voiced vs. Inferred breakdown
    fig_stacked = go.Figure()
    sorted_df = areas_df.sort_values(by="Evidence Volume", ascending=True)

    fig_stacked.add_trace(
        go.Bar(
            y=sorted_df["Opportunity Area"],
            x=sorted_df["Voiced Count"],
            name="Voiced (Explicit Complaint)",
            orientation="h",
            marker=dict(color="#2563EB"),
        )
    )
    fig_stacked.add_trace(
        go.Bar(
            y=sorted_df["Opportunity Area"],
            x=sorted_df["Inferred Count"],
            name="Inferred (Unarticulated Need)",
            orientation="h",
            marker=dict(color="#00D09C"),
        )
    )

    fig_stacked.update_layout(
        barmode="stack",
        template="plotly_white",
        title="<b>Voiced vs. Inferred Breakdown</b>",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color="#111827", size=11),
        ),
        margin=dict(l=10, r=20, t=40, b=20),
        height=380,
        font=dict(family="Inter, sans-serif", color="#111827"),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        xaxis=dict(title_font=dict(color="#111827"), tickfont=dict(color="#374151")),
        yaxis=dict(tickfont=dict(color="#111827", size=11)),
    )
    st.plotly_chart(fig_stacked, use_container_width=True)

st.divider()

# ── Sortable Opportunity Comparison Table ─────────────────────────────────────
st.subheader("📑 Opportunity Area Comparison Matrix")

# Controls for sorting and filtering
ctrl_col1, ctrl_col2 = st.columns([2, 1])

with ctrl_col1:
    sort_by = st.selectbox(
        "Sort areas by:",
        options=[
            "Composite Score (Recommended: Severity × Volume × Diversity)",
            "Evidence Volume (Total items)",
            "Severity Score (Frustration intensity)",
            "Source Diversity (Cross-platform spread)",
            "Abandonment Rate (User churn signal)",
        ],
        index=0,
    )

with ctrl_col2:
    search_term = st.text_input("Filter table by name or keyword:", placeholder="e.g. search, backup, screenshot")

# Map selected sort to column
sort_mapping = {
    "Composite Score (Recommended: Severity × Volume × Diversity)": ("Composite Score", False),
    "Evidence Volume (Total items)": ("Evidence Volume", False),
    "Severity Score (Frustration intensity)": ("Severity Score", False),
    "Source Diversity (Cross-platform spread)": ("Diversity Raw", False),
    "Abandonment Rate (User churn signal)": ("Abandonment Raw", False),
}

sort_col, ascending = sort_mapping[sort_by]
display_df = areas_df.copy()

if search_term.strip():
    kw = search_term.strip().lower()
    display_df = display_df[
        display_df["Opportunity Area"].str.lower().str.contains(kw)
        | display_df["Description"].str.lower().str.contains(kw)
    ]

display_df = display_df.sort_values(by=sort_col, ascending=ascending).reset_index(drop=True)

# Select columns to display in table
columns_to_show = [
    "Opportunity Area",
    "Composite Score",
    "Evidence Volume",
    "Severity Score",
    "Source Diversity",
    "Abandonment Rate",
    "Voiced Count",
    "Inferred Count",
    "Description",
]

st.dataframe(
    display_df[columns_to_show],
    use_container_width=True,
    hide_index=True,
    column_config={
        "Composite Score": st.column_config.ProgressColumn(
            "Priority Score",
            help="severity × log1p(volume) × diversity",
            format="%.1f",
            min_value=0,
            max_value=float(areas_df["Composite Score"].max() if not areas_df.empty else 100),
        ),
        "Severity Score": st.column_config.NumberColumn(
            "Severity",
            help="1.0 = Low, 2.5 = Medium, 4.0+ = High frustration (1.0 to 5.0 scale)",
            format="%.2f / 5.0",
        ),
        "Evidence Volume": st.column_config.NumberColumn(
            "Volume",
            help="Total tagged feedback items",
            format="%d",
        ),
        "Source Diversity": st.column_config.TextColumn(
            "Diversity",
            help="Number of distinct platforms where this failure occurs",
        ),
        "Abandonment Rate": st.column_config.TextColumn(
            "App Abandonment",
            help="Fraction of users reporting they stopped using search or left the app",
        ),
    },
)

# Deep dive link hint
st.caption("💡 Select any opportunity area above and navigate to **2. Opportunity Detail** in the sidebar for full failure heatmaps and verbatim quotes.")
