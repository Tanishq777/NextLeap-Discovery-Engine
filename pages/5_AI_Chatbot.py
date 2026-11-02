"""
pages/5_AI_Chatbot.py — AI Discovery Research Assistant ("Ask the Corpus").
Features a Groww Fintech dual-panel layout with chat thread, quick inquiry chips,
and a live Evidence Drawer showing verbatim investor reviews with platform and upvote citations.
"""
from __future__ import annotations

import html
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from pipeline.dashboard_data import inject_custom_css
from pipeline.chat_engine import (
    answer_research_question,
    get_corpus_cognitive_metrics,
    get_cognitive_recall_spectrum,
)

# Page Configuration
st.set_page_config(
    page_title="AI Research Assistant — Groww SIP Retention",
    page_icon="💬",
    layout="wide",
)
inject_custom_css()

# Fetch behavioral metrics
metrics = get_corpus_cognitive_metrics()

# ── Sidebar: Telemetry & Behavioral Charts ────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 14px;">
            <div style="width: 32px; height: 32px; border-radius: 8px; background: #00D09C; display: flex; align-items: center; justify-content: center; font-weight: 900; color: #121623;">
                G
            </div>
            <div>
                <div style="font-weight: 700; color: white; font-size: 0.95rem;">Retention Telemetry</div>
                <div style="font-size: 0.72rem; color: #00D09C;">Investor Psychology Model</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Behavioral Signals Chart
    bs_data = metrics.get("behavioral_signals", {})
    if bs_data:
        bs_labels = [k.replace("_", " ").title() for k in bs_data.keys()][:5]
        bs_vals = [bs_data[k]["pct"] for k in bs_data.keys()][:5]

        fig_bs = px.bar(
            x=bs_vals,
            y=bs_labels,
            orientation="h",
            labels={"x": "% of Investors Exhibiting", "y": ""},
            title="<b>Early-Warning Signals</b>",
            color=bs_vals,
            color_continuous_scale=["#00D09C", "#008765"],
        )
        fig_bs.update_layout(
            template="plotly_dark",
            margin=dict(l=5, r=10, t=35, b=20),
            height=210,
            coloraxis_showscale=False,
            font=dict(size=10, family="Inter, sans-serif", color="#FFFFFF"),
            paper_bgcolor="#1E2235",
            plot_bgcolor="#1E2235",
            xaxis=dict(tickfont=dict(color="#CBD5E1", size=9), title_font=dict(color="#FFFFFF", size=10)),
            yaxis=dict(tickfont=dict(color="#FFFFFF", size=9)),
        )
        st.plotly_chart(fig_bs, use_container_width=True)

    # Lifecycle Stage Hazard
    ls_data = metrics.get("lifecycle_stages", {})
    if ls_data:
        stage_names = {
            "first_month": "Month 1 (Onboard)",
            "early_1_3m": "Months 1–3 (Volatility)",
            "mid_4_6m": "Months 4–6 (Fatigue)",
            "late_7_12m": "Months 7–12 (Maturation)",
            "post_dropout": "Post-Dropout (Lapsed)",
        }
        ls_labels = [stage_names.get(k, k.replace("_", " ").title()) for k in ls_data.keys()][:4]
        ls_vals = [ls_data[k]["pct"] for k in ls_data.keys()][:4]

        fig_ls = px.bar(
            x=ls_vals,
            y=ls_labels,
            orientation="h",
            labels={"x": "% of Dropoff Signals", "y": ""},
            title="<b>Lifecycle Dropoff Points</b>",
            color=ls_vals,
            color_continuous_scale=["#EB5B56", "#c5221f"],
        )
        fig_ls.update_layout(
            template="plotly_dark",
            margin=dict(l=5, r=10, t=35, b=20),
            height=190,
            coloraxis_showscale=False,
            font=dict(size=10, family="Inter, sans-serif", color="#FFFFFF"),
            paper_bgcolor="#1E2235",
            plot_bgcolor="#1E2235",
            xaxis=dict(tickfont=dict(color="#CBD5E1", size=9), title_font=dict(color="#FFFFFF", size=10)),
            yaxis=dict(tickfont=dict(color="#FFFFFF", size=9)),
        )
        st.plotly_chart(fig_ls, use_container_width=True)

    st.divider()
    if st.button("🗑️ Reset Chat History", use_container_width=True):
        st.session_state.chatbot_page_messages = []
        st.rerun()

# ── Header Banner ─────────────────────────────────────────────────────────────
# ── Dual-Panel Layout (Left Chat Thread + Right Evidence Drawer) ──────────────
chat_col, evidence_col = st.columns([2.3, 1], gap="medium")

prompt_chips = [
    ("🔍 NAV & XIRR Opacity", "Why do investors struggle with NAV and annualized XIRR transparency?"),
    ("🧠 Linear Return Gap", "Why do first-time investors expect guaranteed linear returns like fixed deposits?"),
    ("❓ Why Debits Fail", "Why do mandate auto-debits fail mid-tenure and how does it trigger cancellation?"),
    ("📅 Salary Timing", "How does salary credit delay cause mid-life mandate failures?"),
    ("⚠️ Bank Bounce Charges", "What impact do bank ECS and NACH bounce penalties have on churn?"),
    ("🚪 Early Dropout", "Why do investors drop out within the first 1–3 months of starting a SIP?"),
    ("💡 Top Retention Levers", "What are the top opportunity areas and product interventions to boost 12-month retention?"),
]

selected_query = None

with chat_col:
    # Dark Chat Header Card matching reference screenshot
    st.markdown(
        """
        <div style="background: #121623; border-radius: 16px 16px 0 0; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #1E293B; border-bottom: none; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="position: relative; flex-shrink: 0;">
                    <div style="width: 40px; height: 40px; border-radius: 50%; background: linear-gradient(135deg, #6366F1, #8B5CF6, #EC4899); display: flex; align-items: center; justify-content: center; color: white; font-size: 1.15rem; font-weight: 700; box-shadow: 0 0 0 3px rgba(99,102,241,0.25);">
                        ✦
                    </div>
                    <span style="position: absolute; bottom: 1px; right: 1px; width: 10px; height: 10px; border-radius: 50%; background: #22C55E; border: 2px solid #121623;"></span>
                </div>
                <div>
                    <div style="font-weight: 700; color: #F8FAFC; font-size: 0.98rem; line-height: 1.2;">AI Discovery Assistant</div>
                    <div style="color: #94A3B8; font-size: 0.74rem; margin-top: 2px;">Powered by Groq · Grounded in your data</div>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="background: rgba(34,197,94,0.15); color: #4ADE80; border: 1px solid rgba(34,197,94,0.3); font-size: 0.72rem; font-weight: 700; padding: 4px 10px; border-radius: 9999px; letter-spacing: 0.02em;">
                    ● Live AI
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Interactive Prompt Chips Row
    chip_cols = st.columns(len(prompt_chips))
    for i, (chip_label, query_text) in enumerate(prompt_chips):
        with chip_cols[i]:
            if st.button(chip_label, key=f"p5_chip_btn_{i}", use_container_width=True):
                selected_query = query_text

    # Initialize session state for messages
    if "chatbot_page_messages" not in st.session_state:
        st.session_state.chatbot_page_messages = []

    # Empty state centered card if no conversation yet
    if not st.session_state.chatbot_page_messages and not selected_query:
        st.markdown(
            """
            <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-top: none; padding: 60px 30px; text-align: center; border-radius: 0 0 16px 16px; margin-bottom: 20px; min-height: 320px; display: flex; flex-direction: column; align-items: center; justify-content: center; box-shadow: 0 4px 20px -2px rgba(0,0,0,0.03); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                <div style="font-size: 2.2rem; color: #0F172A; margin-bottom: 12px; line-height: 1;">✦</div>
                <h3 style="font-size: 1.18rem; font-weight: 700; color: #0F172A; margin: 0 0 8px 0;">
                    AI Discovery Assistant
                </h3>
                <p style="font-size: 0.88rem; color: #475569; max-width: 500px; line-height: 1.5; margin: 0 0 12px 0;">
                    I'm grounded on <strong>511 verified customer signals</strong> from Google Play Store, Reddit, Apple App Store, YouTube, and Help Forums.
                </p>
                <p style="font-size: 0.82rem; color: #64748B; max-width: 480px; line-height: 1.45; margin: 0;">
                    Ask me anything — about the data, user behavior, dropout pain points, or product strategy. Click a prompt chip to get started!
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Message history
    for m in st.session_state.chatbot_page_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"], unsafe_allow_html=True)

    user_chat_input = st.chat_input("Ask anything about the data, user behavior, or product strategy...")
    active_query = selected_query or user_chat_input

    if active_query:
        st.session_state.chatbot_page_messages.append({"role": "user", "content": active_query, "quotes": []})
        with st.chat_message("user"):
            st.markdown(active_query)

        with st.chat_message("assistant"):
            with st.spinner("Synthesizing empirical investor telemetry & retention metrics..."):
                ans_data = answer_research_question(active_query)
                st.markdown(ans_data["answer"], unsafe_allow_html=True)
                st.session_state.p5_active_quotes = ans_data.get("quotes", [])
                st.session_state.chatbot_page_messages.append({
                    "role": "assistant",
                    "content": ans_data["answer"],
                    "quotes": ans_data.get("quotes", []),
                })
                st.rerun()

with evidence_col:
    p5_quotes = st.session_state.get("p5_active_quotes", [])
    if not p5_quotes and st.session_state.chatbot_page_messages:
        last_msg = st.session_state.chatbot_page_messages[-1]
        p5_quotes = last_msg.get("quotes", [])

    matched_count = len(p5_quotes)
    spectrum_items = get_cognitive_recall_spectrum()
    spectrum_html = ""
    for idx, s in enumerate(spectrum_items):
        mb = "margin-bottom: 12px;" if idx < len(spectrum_items) - 1 else "margin-bottom: 0;"
        pct = s.get("pct", 0.0)
        cnt = s.get("count", 0)
        color = s.get("color", "#2563EB")
        name = s.get("name", "")
        spectrum_html += f"""
        <div style="{mb}">
            <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: #334155; font-weight: 500; margin-bottom: 4px;">
                <span>{name}</span>
                <strong>{pct}% <span style="font-size: 0.7rem; color: #64748B; font-weight: 400;">({cnt})</span></strong>
            </div>
            <div style="width: 100%; height: 5px; background: #E2E8F0; border-radius: 4px; overflow: hidden;">
                <div style="width: {pct}%; height: 100%; background: {color}; border-radius: 4px;"></div>
            </div>
        </div>
        """

    # Evidence Drawer Card matching reference screenshot
    st.markdown(
        f"""
        <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 16px; padding: 22px 20px; box-shadow: 0 4px 20px -2px rgba(0,0,0,0.05); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <div style="font-weight: 700; font-size: 1.05rem; color: #0F172A; letter-spacing: -0.01em;">
                    Evidence Drawer
                </div>
                <span style="background: #EFF6FF; color: #2563EB; font-size: 0.75rem; font-weight: 700; border-radius: 9999px; padding: 3px 10px; border: 1px solid #DBEAFE;">
                    {matched_count} matched
                </span>
            </div>

            <!-- Cognitive Hazard / Recall Spectrum Card -->
            <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px; padding: 16px 18px; margin-bottom: 20px;">
                <div style="font-size: 0.7rem; font-weight: 700; color: #64748B; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 14px;">
                    COGNITIVE RECALL SPECTRUM
                </div>
                {spectrum_html}
            </div>

            <!-- Verbatim Customer Signals Header -->
            <div style="font-size: 0.72rem; font-weight: 700; color: #64748B; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 14px;">
                VERBATIM CUSTOMER SIGNALS
            </div>
        """,
        unsafe_allow_html=True,
    )

    if p5_quotes:
        for q in p5_quotes:
            src_name = q.get("source", "User").replace("_", " ").title()
            upvotes = q.get("upvotes", 0)
            up_text = f" · 👍 {upvotes} upvotes" if upvotes else ""
            q_text = html.escape(str(q.get("text", "")))
            st.markdown(
                f"""
                <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-left: 3px solid #2563EB; border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.02); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                    <div style="font-style: italic; font-size: 0.84rem; color: #334155; line-height: 1.45; margin-bottom: 6px;">"{q_text}"</div>
                    <div style="font-size: 0.74rem; color: #64748B; font-weight: 600;">
                        <span>🏷️ <b>{src_name}</b>{up_text}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            """
            <div style="font-size: 0.82rem; color: #94A3B8; text-align: center; padding: 36px 16px; line-height: 1.5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                Evidence records retrieved for each query will appear here.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)
