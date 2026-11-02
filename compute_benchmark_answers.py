"""
compute_benchmark_answers.py — Extracts empirical metrics and quotes answering the 9 Benchmark Questions.
Uses the 4,346 empirical records in SQLite. Zero synthetic items.
"""
from __future__ import annotations

import json
import sqlite3
import pandas as pd
import config
from pipeline.scorer import wilson_score_interval


def main():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    # Empirical filter
    df = pd.read_sql_query(
        """
        SELECT 
            r.id, r.source, r.app_name, r.text, r.upvotes, r.date,
            t.relevant, t.drop_type, t.sip_status, t.trigger, t.stated_expectation,
            t.what_they_checked, t.check_frequency, t.outside_app_action, t.influencer,
            t.income_stability, t.money_source, t.age_band, t.lifecycle_month,
            t.in_app_confusion_object, t.mandate_subcluster, t.disconfirming_attribution,
            t.rival_hypothesis, t.primary_area, t.is_continuer, t.problem_types,
            t.lifecycle_stage, t.behavioral_signals, t.emotional_state, t.trigger_types,
            t.retention_risk, t.unsure_question
        FROM raw_items r
        JOIN tagged_items t ON t.raw_item_id = r.id
        WHERE r.is_synthetic = 0
        """,
        conn,
    )

    total_records = len(df)
    rel_df = df[df["relevant"] == 1]
    total_rel = len(rel_df)

    print("=" * 80)
    print(f"EMPIRICAL DATASET OVERVIEW (N={total_records:,} Total Raw, N={total_rel:,} Relevant)")
    print("=" * 80)

    # 1. Why do people start a SIP, and what do they expect to happen?
    print("\n--- 1. Why people start & stated expectations ---")
    exp_counts = rel_df["stated_expectation"].value_counts()
    print(exp_counts)
    inf_counts = rel_df["influencer"].value_counts()
    print("\nInfluencers:")
    print(inf_counts)

    # 2. What changes in behaviour in the months after starting?
    print("\n--- 2. Behaviour changes across lifecycle stages ---")
    lc_counts = rel_df["lifecycle_stage"].value_counts()
    print(lc_counts)

    # 3. What leads investors to pause, reduce or stop a SIP?
    print("\n--- 3. Triggers for pause / reduce / stop ---")
    trig_counts = rel_df["trigger"].value_counts()
    print(trig_counts)
    drop_counts = rel_df["drop_type"].value_counts()
    print("\nDrop Types (voluntary vs involuntary):")
    print(drop_counts)
    mandate_counts = rel_df["mandate_subcluster"].value_counts()
    print("\nMandate Subclusters:")
    print(mandate_counts)

    # 4. What do investors check, and how often?
    print("\n--- 4. What they check & checking frequency ---")
    check_obj = rel_df["what_they_checked"].value_counts()
    print(check_obj)
    check_freq = rel_df["check_frequency"].value_counts()
    print("\nCheck Frequency:")
    print(check_freq)

    # 5. What confuses or worries them inside the app?
    print("\n--- 5. In-app confusion objects & emotional state ---")
    conf_counts = rel_df["in_app_confusion_object"].value_counts()
    print(conf_counts)
    emo_counts = rel_df["emotional_state"].value_counts()
    print("\nEmotional States:")
    print(emo_counts)

    # 6. What do they do outside the app when unsure?
    print("\n--- 6. Outside app action when unsure ---")
    out_counts = rel_df["outside_app_action"].value_counts()
    print(out_counts)

    # 7. What separates continuers from drop-offs?
    print("\n--- 7. Continuers vs Drop-offs ---")
    cont_counts = rel_df["is_continuer"].value_counts()
    print(cont_counts)
    status_counts = rel_df["sip_status"].value_counts()
    print("\nSIP Statuses:")
    print(status_counts)

    # 8. User segments (income stability, age, money source, influencer)
    print("\n--- 8. Demographic cuts ---")
    print("Income Stability:")
    print(rel_df["income_stability"].value_counts())
    print("\nMoney Source:")
    print(rel_df["money_source"].value_counts())
    print("\nAge Band:")
    print(rel_df["age_band"].value_counts())

    # 9. Unmet needs & Opportunity areas
    print("\n--- 9. Consistently Emerging Unmet Needs (Opportunity Areas) ---")
    opp_counts = rel_df["primary_area"].value_counts()
    print(opp_counts)

    conn.close()


if __name__ == "__main__":
    main()
