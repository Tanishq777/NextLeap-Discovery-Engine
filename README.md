# Groww SIP Retention Discovery Engine (v3.0)

An autonomous, end-to-end empirical research engine and interactive dashboard built for Growth Product Managers and Quantitative UX Researchers at **Groww**.

> **Strategic Objective:** Increase the percentage of first-time mutual fund investors who maintain an **active SIP 12 months** after starting their first one (active SIP = at least one successful monthly instalment debited and allocated in the preceding 30 days).

The engine ingests public user feedback at real scale across 6 balanced channels (Google Play Store, Apple App Store, Reddit, YouTube comments, TradingQ&A / Help Forums, Web Queries), applies a **Two-Level Relevance Filter**, isolates **308 synthetic test cases** under strict Rule 0 mocking segregation, and maps empirical friction across 10 brief-aligned dimensions to **10 defensible opportunity spaces** using multi-model sensitivity analysis.

---

## 1. Corpus Scale & Funnel Architecture

Every number reported is verifiable directly from SQLite (`data/discovery_engine.db`) via `python3 verify_dossier.py`:

* **Total Raw Empirical Items `[Q-01]`:** **1,739 items** collected across 6 channels (Play Store: 708, App Store: 373, Help Forums: 317, YouTube: 299, Reddit: 34, Web: 8).
* **Level 1 On-Topic MF Items `[Q-02]`:** **948 / 1,739** (54.5% `[95% CI: 52.2%–56.9%]`).
* **Level 2 Retention-Relevant Dilemmas `[Q-03]`:** **511 / 1,739** (29.4% `[95% CI: 27.3%–31.6%]`).
* **General MF Feedback Excluded `[Q-03b]`:** **437 / 1,739** (25.1% `[95% CI: 23.1%–27.2%]`) — moved out of opportunity scoring to avoid diluting retention priorities.
* **Segregated Synthetic Items `[Q-22]`:** **308 items** (Rule 0: 100% excluded from all empirical percentages, CIs, and scores).
* **Golden Evaluation Set v2:** **105 audited retail questions** (35 must-decline guardrails, 92 real/paraphrased, 13 synthetic) with worked calculations and regulatory circular citations.

```
┌─────────────────────────────────┬───────┬────────────┬───────────────────────────────────────────────────────┐
│ Channel                         │ Count │ Pct Share  │ Wilson 95% Confidence Interval                        │
├─────────────────────────────────┼───────┼────────────┼───────────────────────────────────────────────────────┤
│ Google Play Store               │ 708   │ 40.7%      │ [38.4% – 43.1%]                                       │
│ Apple App Store                 │ 373   │ 21.5%      │ [19.6% – 23.5%]                                       │
│ Help Forums (TradingQ&A / VP)   │ 317   │ 18.2%      │ [16.5% – 20.1%]                                       │
│ YouTube Video Comments          │ 299   │ 17.2%      │ [15.5% – 19.1%]                                       │
│ Reddit Subreddits (Audited)     │ 34    │ 2.0% ⚠️    │ [1.4% – 2.8%]                                         │
│ Web Financial Queries           │ 8     │ 0.5% ⚠️    │ [0.2% – 0.9%] (low sample size)                       │
├─────────────────────────────────┼───────┼────────────┼───────────────────────────────────────────────────────┤
│ Total Empirical Raw Corpus      │ 1,739 │ 100.0%     │ —                                                     │
└─────────────────────────────────┴───────┴────────────┴───────────────────────────────────────────────────────┘
```

---

## 2. 10-Dimensional Brief Taxonomy (Retention-Relevant Corpus: $N = 511$)

Every classified record in SQLite (`data/discovery_engine.db`) includes an evidence span (verbatim quote) and confidence score:

1. **`drop_type` `[Q-11]`:** `involuntary` (1.6% ⚠️), `voluntary` (1.0% ⚠️), `unknown` (97.5%).
2. **`sip_status`:** `cancelled` (1.2% ⚠️), `continuing` (1.0% ⚠️), `lapsed` (1.0% ⚠️), `paused` (0.0% — reflects lack of in-app pause affordance), `unknown` (96.9%).
3. **`trigger` `[Q-12]`:** `market move` (2.7% ⚠️), `comparison` (2.2% ⚠️), `failed debit` (1.6% ⚠️), `cashflow` (0.6% ⚠️), `trust` (0.4% ⚠️), `unknown` (92.6%).
4. **`stage_of_mention` `[Q-10]`:** `unknown` (92.6%), `early_1_3m` (2.7% ⚠️), `late_7_12m` (1.6% ⚠️), `post_dropout` (1.6% ⚠️), `mid_4_6m` (1.4% ⚠️), `first_month` (0.2% ⚠️). On known-stage records ($N=38$), Months 1–3 represents 36.8% `[Q-10b]`.
5. **`outside_app_action` `[Q-21]`:** Derived strictly from text; unknown (97.5%), asked friends/family (1.6% ⚠️), asked reddit/forum (0.8% ⚠️). Cramér's V = 0.0791 (passed < 0.80 channel independence threshold).
6. **`stoppers_vs_continuers` `[Q-15]`:** Daily checking difference: $+27.3\%$ `[95% CI: +0.9% to +53.6%, p = 0.0425]`.
7. **`disconfirming_pass` `[Q-16]`:** 7-way attribution across Denominator A ($N=511$) and Denominator B ($N_{\text{known}}=47$): Structural (31.9% in known), Comparison (27.7%), Expectation (19.1%), Market Move (10.6%), Cashflow (6.4%), Trust (4.3%).
8. **`rival_hypotheses` `[Q-17]`:** Better alternative (FD/stocks) 2.5% ⚠️, Purposelessness 0.6% ⚠️, Cash constraint 0.6% ⚠️.
9. **`mandate_subcluster` `[Q-18]`:** Mid-life failed debit (0.8% ⚠️, stop link: 75.0%), Post-failure bounce penalty (0.8% ⚠️, stop link: 75.0%), Setup failure (0.4% ⚠️), Status/refund confusion (0.0%).
10. **`segment_availability` `[Q-19]`:** Income stability (0.8% known), Money source (0.8%), Age band (1.6%), Lifecycle month (2.5%). All labeled `⚠️ NOT ANALYSABLE FROM PUBLIC TEXT (Requires in-depth user interviews)`.

---

## 3. Defensible Opportunity Area Rankings `[Q-20]`

With General Mutual Fund Feedback excluded from scoring, the 10 opportunity spaces rank as follows:

```
-----------------------------------------------------------------------------------------------------------------------------------------
Rank  Opportunity Area                                    Primary Vol   Sev   Stop Pct   Addr   Base Score   Sev Rank   Frq Rank   Ret Rank
-----------------------------------------------------------------------------------------------------------------------------------------
1     Post-Failure Bank Bounce Penalties                  4 (0.8%) ⚠️   4.9   75.0%      4.2    67.3         1          5          1       
2     Mid-Life Failed Debit Mechanics                     4 (0.8%) ⚠️   4.8   75.0%      4.0    66.2         2          6          2       
3     Metric Opacity (XIRR, NAV & Unit Allotment Math)    109 (21.3%)   3.2   0.0%       4.8    55.6         7          1          6       
4     Unrealistic Return Expectations & Portfolio Shock   13 (2.5%) ⚠️  4.0   23.1%      4.5    50.1         3          3          3       
5     Rigid Mandate Controls (Missing Pause & Skip)       9 (1.8%) ⚠️   4.5   0.0%       4.8    48.2         4          4          5       
6     Peer Regret & Short-Term Return Comparison          14 (2.7%) ⚠️  3.0   14.3%      3.8    40.3         6          2          4       
7     Setup & Authorization Friction                      2 (0.4%) ⚠️   3.5   0.0%       3.8    39.1         8          7          8       
8     Status & Refund Confusion                           0 (0.0%)      3.0   0.0%       4.0    37.6         9          9          9       
9     Disconfirming Cashflow Constraints (True Need)      3 (0.6%) ⚠️   3.8   0.0%       2.2    36.0         5          8          7       
10    Active Continuer Conviction (Survivors)             5 (1.0%) ⚠️   1.2   0.0%       4.5    28.7         10         10         10      
-----------------------------------------------------------------------------------------------------------------------------------------
```

---

## 4. Single-Command Reproducibility Gate

All numbers and tables in this repository are reproducible and verified via automated CLI commands:

```bash
# 1. Compute all metrics directly from SQLite:
python3 compute_metrics.py

# 2. Run the reproducibility gate (fails if any document figure mismatches or Cramér's V >= 0.80):
python3 verify_dossier.py

# 3. Launch the interactive Streamlit research dashboard:
python3 -m streamlit run app.py
```

---

## 5. Key Documentation & Artifacts

* **Handoff Dossier (v3):** [`GROWW_SIP_RETENTION_INSIGHTS_DEEP_DIVE.md`](file:///Users/tanishq/Desktop/scrapper_next_leap/google_Scapper/GROWW_SIP_RETENTION_INSIGHTS_DEEP_DIVE.md) — Comprehensive strategic analysis, grounded quotes, verified worked calculations, and SEBI/RBI-compliant product specs.
* **Classifier Evidence Log:** [`reports/classifier_evidence_log.md`](file:///Users/tanishq/Desktop/scrapper_next_leap/google_Scapper/reports/classifier_evidence_log.md) — Precision/recall against keyword baseline, Cohen's kappa $\kappa = 1.0000$, and failure case deep-dives.
* **Segregated Synthetic Test Cases (Rule 0):** [`data/synthetic_items.json`](file:///Users/tanishq/Desktop/scrapper_next_leap/google_Scapper/data/synthetic_items.json).
* **Question Bank v2 (Golden Eval Set):** [`data/unsure_question_bank_v2.json`](file:///Users/tanishq/Desktop/scrapper_next_leap/google_Scapper/data/unsure_question_bank_v2.json) and [`.csv`](file:///Users/tanishq/Desktop/scrapper_next_leap/google_Scapper/data/unsure_question_bank_v2.csv) (105 audited questions with 35 must-decline guardrails).
* **Opportunity Matrix Data:** [`data/opportunity_areas.csv`](file:///Users/tanishq/Desktop/scrapper_next_leap/google_Scapper/data/opportunity_areas.csv).
* **Classified Dataset:** [`data/tagged_items.csv`](file:///Users/tanishq/Desktop/scrapper_next_leap/google_Scapper/data/tagged_items.csv).
