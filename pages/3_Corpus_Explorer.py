"""
pages/3_Corpus_Explorer.py — Raw & Tagged Feedback Corpus Explorer.
Supports multidimensional filtering, keyword and semantic search, pagination,
and CSV export of filtered records.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd

from pipeline.dashboard_data import get_filtered_corpus, inject_custom_css

# Page Configuration
st.set_page_config(page_title="Corpus Explorer — Discovery Engine", page_icon="🗂️", layout="wide")
inject_custom_css()

# Header
st.markdown(
    """
    <div style="padding: 1rem 0 1rem 0;">
        <h1 style="font-weight: 800; font-size: 2.2rem; color: #111827; margin-bottom: 0.2rem;">
            🗂️ Raw Corpus Explorer
        </h1>
        <p style="font-size: 1.05rem; color: #4B5563; line-height: 1.5;">
            Query, filter, and export verbatim customer feedback items along with all 8 LLM classification tags.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Multi-Dimensional Filters ────────────────────────────────────────────────
with st.expander("🔍 Filter & Search Criteria", expanded=True):
    # Search box and search mode toggle
    s_col1, s_col2 = st.columns([3, 1])
    with s_col1:
        search_query = st.text_input(
            "Search Text:",
            placeholder="e.g. searching for receipt, couldn't find concert photos, dog picture",
        )
    with s_col2:
        search_mode = st.radio(
            "Search Mode:",
            options=["keyword", "semantic"],
            format_func=lambda x: "Keyword (SQL LIKE)" if x == "keyword" else "Semantic (Chroma AI)",
            horizontal=True,
        )

    f_col1, f_col2, f_col3, f_col4 = st.columns(4)

    with f_col1:
        sources = st.multiselect(
            "Source Platform:",
            options=["play_store", "app_store", "reddit", "youtube", "help_forum", "web"],
            format_func=lambda x: x.replace("_", " ").title(),
        )

    with f_col2:
        problem_types = st.multiselect(
            "Problem Type:",
            options=[
                "returns_disappointment",
                "market_anxiety",
                "financial_pressure",
                "app_confusion",
                "lack_of_understanding",
                "trust_deficit",
                "goal_disconnect",
                "comparison_regret",
                "peer_pressure",
            ],
            format_func=lambda x: x.replace("_", " ").title(),
        )

    with f_col3:
        lifecycle_stages = st.multiselect(
            "SIP Lifecycle Stage:",
            options=["first_month", "early_1_3m", "mid_4_6m", "late_7_12m", "post_dropout"],
            format_func=lambda x: {
                "first_month": "Month 1 (Onboarding)",
                "early_1_3m": "Months 1–3 (Early Volatility)",
                "mid_4_6m": "Months 4–6 (Statement Fatigue)",
                "late_7_12m": "Months 7–12 (Habit Maturation)",
                "post_dropout": "Post-Dropout (Lapsed)",
            }.get(x, x),
        )

    with f_col4:
        retention_risks = st.multiselect(
            "Retention Risk:",
            options=["med", "high", "already_churned"],
            format_func=lambda x: x.replace("_", " ").title(),
        )

# Pagination state management
if "corpus_page" not in st.session_state:
    st.session_state.corpus_page = 1

PAGE_SIZE = 50

# Fetch filtered items
page_df, total_count, export_df = get_filtered_corpus(
    sources=sources if sources else None,
    problem_types=problem_types if problem_types else None,
    lifecycle_stages=lifecycle_stages if lifecycle_stages else None,
    retention_risks=retention_risks if retention_risks else None,
    search_query=search_query if search_query else None,
    search_mode=search_mode,
    page=st.session_state.corpus_page,
    page_size=PAGE_SIZE,
)

total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
if st.session_state.corpus_page > total_pages:
    st.session_state.corpus_page = 1

# ── Action Bar: Count & CSV Export ───────────────────────────────────────────
st.write("")
a_col1, a_col2 = st.columns([2, 1])

with a_col1:
    st.markdown(
        f"<div style='font-size: 1.1rem; padding-top: 6px;'>"
        f"Found <b>{total_count:,}</b> matching items "
        f"(Page <b>{st.session_state.corpus_page}</b> of <b>{total_pages}</b>)"
        f"</div>",
        unsafe_allow_html=True,
    )

with a_col2:
    if not export_df.empty:
        csv_data = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Export Filtered Results (CSV)",
            data=csv_data,
            file_name="discovery_engine_filtered_corpus.csv",
            mime="text/csv",
            use_container_width=True,
        )

st.write("")

# ── Paginated Results Table ───────────────────────────────────────────────────
if page_df.empty:
    st.info(
        "💡 No items match the specified filters.\n\n"
        "If you haven't run data collection or the tagging pipeline yet, run:\n"
        "```bash\n"
        "python run_collectors.py --sources all --limit 200\n"
        "python run_pipeline.py --step tag\n"
        "```"
    )
else:
    # Render table
    st.dataframe(
        page_df[[
            "Source",
            "Feedback Text",
            "Problem Types",
            "Lifecycle Stage",
            "Behavioral Signals",
            "Retention Risk",
            "Pattern",
            "Upvotes",
            "Date",
        ]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Source": st.column_config.TextColumn("Platform", width="small"),
            "Feedback Text": st.column_config.TextColumn("Verbatim Feedback", width="large"),
            "Problem Types": st.column_config.TextColumn("Problem Types", width="medium"),
            "Lifecycle Stage": st.column_config.TextColumn("Stage", width="small"),
            "Behavioral Signals": st.column_config.TextColumn("Signals", width="medium"),
            "Retention Risk": st.column_config.TextColumn("Risk", width="small"),
            "Pattern": st.column_config.TextColumn("Signal", width="small"),
            "Upvotes": st.column_config.NumberColumn("Upvotes", width="small"),
            "Date": st.column_config.TextColumn("Date", width="small"),
        },
    )

    # ── Pagination Controls ───────────────────────────────────────────────────
    p_col1, p_col2, p_col3, p_col4, p_col5 = st.columns([1, 1, 2, 1, 1])

    with p_col2:
        if st.button("◀ Previous Page", disabled=(st.session_state.corpus_page <= 1)):
            st.session_state.corpus_page -= 1
            st.rerun()

    with p_col3:
        st.markdown(
            f"<div style='text-align: center; padding-top: 8px; color: #4B5563; font-size: 0.9rem; font-weight: 600;'>"
            f"Page {st.session_state.corpus_page} of {total_pages}"
            f"</div>",
            unsafe_allow_html=True,
        )

    with p_col4:
        if st.button("Next Page ▶", disabled=(st.session_state.corpus_page >= total_pages)):
            st.session_state.corpus_page += 1
            st.rerun()

    # ── Detail Inspector ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("🔎 Verbatim Item Inspector")
    st.caption("Inspect the complete verbatim text and classification payload for any item on this page.")

    item_options = [
        f"[{row['Source']}] {row['Feedback Text'][:90]}... (ID: {row['ID'][:8]})"
        for _, row in page_df.iterrows()
    ]
    selected_idx = st.selectbox(
        "Select item to view full context:",
        options=range(len(item_options)),
        format_func=lambda i: item_options[i],
    )

    if selected_idx is not None and selected_idx < len(page_df):
        selected_item = page_df.iloc[selected_idx]

        st.markdown(
            f"""
            <div style="background: #ffffff; border: 1px solid #E5E7EB; border-left: 4px solid #00D09C; border-radius: 10px; padding: 22px; margin-top: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.03);">
                <div style="font-size: 1.05rem; line-height: 1.6; color: #111827; font-weight: 500; margin-bottom: 14px;">
                    "{selected_item['Feedback Text']}"
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 16px; font-size: 0.85rem; color: #4B5563; border-top: 1px solid #F3F4F6; padding-top: 12px;">
                    <span><b style="color: #111827;">Platform:</b> {selected_item['Source']}</span>
                    <span><b style="color: #111827;">Problem Types:</b> {selected_item['Problem Types']}</span>
                    <span><b style="color: #111827;">Lifecycle Stage:</b> {selected_item['Lifecycle Stage']}</span>
                    <span><b style="color: #111827;">Behavioral Signals:</b> {selected_item['Behavioral Signals']}</span>
                    <span><b style="color: #111827;">Retention Risk:</b> {selected_item['Retention Risk']}</span>
                    <span><b style="color: #111827;">Signal Pattern:</b> {selected_item['Pattern']}</span>
                    <span><b style="color: #111827;">Assigned Areas:</b> {selected_item['Assigned Areas']}</span>
                    <span><b style="color: #111827;">Engagement:</b> {selected_item['Upvotes']} upvotes</span>
                    {f"<span><a href='{selected_item['URL']}' target='_blank' style='color: #008765; font-weight: 700; text-decoration: none;'>Open Source ↗</a></span>" if selected_item['URL'] else ""}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
