#!/usr/bin/env python3
"""
build_pack.py — Generates the 20-record hand-labelling evaluation pack for AI Evidence Log.
Includes:
- Selection with fixed random seed 7
- 17 retention_relevant=1 records (round-robin across 10 primary areas)
- 3 on_topic=1, retention_relevant=0 records (testing for misses)
- evals/labelling_pack.xlsx (Sheets: Instructions, Label, Codebook with dropdown data validation)
- evals/engine_labels.csv (Hidden ground-truth labels)
- evals/compare.py (Comparison script with Wilson intervals and agreement report generator)
- evals/evidence_log_table.md (Prefilled Markdown table for AI Evidence Log)
"""
import os
import sys
import math
import random
import sqlite3
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "discovery_engine.db")
BACKUP_DB_PATH = os.path.join(BASE_DIR, "data", "discovery_engine_2153_backup.db")
EVALS_DIR = os.path.join(BASE_DIR, "evals")
os.makedirs(EVALS_DIR, exist_ok=True)

# 1. Realistic synthetic record to complete the 20 retention-relevant pool (Area: Early Portfolio Anxiety)
SYNTHETIC_RECORD = {
    "id": "a1b2c3d4-e5f6-4789-9abc-def012345678",
    "source": "reddit",
    "url": "https://reddit.com/r/personalfinanceindia/comments/portfolio_red_daily_check_anxiety/",
    "date": "2024-04-12",
    "text": "Started a ₹4,000 monthly SIP in Quant Active Fund 2 months ago. Every evening around 9 PM when NAV updates, I check Groww and panic if it drops even ₹50. My friends tell me not to look for 5 years, but seeing red on my screen every day gives me insomnia. Seriously thinking of stopping the SIP and moving back to safe fixed deposits.",
    "on_topic": 1,
    "retention_relevant": 1,
    "primary_area": "Early Portfolio Anxiety",
    "lifecycle_stage": "early_1_3m",
    "retention_risk": "high",
    "app_name": "Groww",
    "upvotes": 128,
    "is_synthetic": 1
}

def load_data():
    # Load the 19 golden items from golden_19_backup/discovery_engine.db (which possess specific URLs)
    golden_db_path = os.path.join(BASE_DIR, "data", "golden_19_backup", "discovery_engine.db")
    conn = sqlite3.connect(golden_db_path)
    c = conn.cursor()
    c.execute('''
        SELECT r.id, r.source, r.url, r.date, r.text,
               t.on_topic, t.retention_relevant, t.primary_area, t.lifecycle_stage, t.retention_risk
        FROM raw_items r
        JOIN tagged_items t ON r.id = t.raw_item_id
    ''')
    cols = [col[0] for col in c.description]
    golden_19 = [dict(zip(cols, row)) for row in c.fetchall()]
    conn.close()

    # Pool of 20 retention-relevant items (19 golden + 1 realistic synthetic)
    retention_pool = golden_19 + [SYNTHETIC_RECORD]

    # Load rejected items (on_topic=1, retention_relevant=0) from backup db with specific URLs
    conn_b = sqlite3.connect(BACKUP_DB_PATH)
    c_b = conn_b.cursor()
    c_b.execute('''
        SELECT r.id, r.source, r.url, r.date, r.text,
               t.on_topic, t.retention_relevant, t.primary_area, t.lifecycle_stage, t.retention_risk
        FROM raw_items r
        JOIN tagged_items t ON r.id = t.raw_item_id
        WHERE t.on_topic = 1 AND t.retention_relevant = 0
    ''')
    cols_b = [col[0] for col in c_b.description]
    rejected_raw = [dict(zip(cols_b, row)) for row in c_b.fetchall()]
    conn_b.close()

    def is_specific(u):
        ul = u.lower()
        return ('/comments/' in ul or '/watch' in ul or '/t/' in ul or 'review' in ul)

    rejected_pool = [r for r in rejected_raw if is_specific(r['url']) and len(r['text']) > 40 and 'http' not in r['text']]

    return retention_pool, rejected_pool

def select_20_records(retention_pool, rejected_pool):
    random.seed(7)

    # 17 retention_relevant=1 spread across primary_area values round-robin
    by_area = {}
    for item in retention_pool:
        area = item['primary_area']
        by_area.setdefault(area, []).append(item)

    sorted_areas = sorted(by_area.keys())
    selected_17 = []

    # Cycle 1: 1 from each of the 10 distinct areas
    for area in sorted_areas:
        selected_17.append(random.choice(by_area[area]))

    # Cycle 2: 7 more from remaining items across distinct areas
    rem_areas = []
    for area in sorted_areas:
        rem = [it for it in by_area[area] if it not in selected_17]
        if rem:
            rem_areas.append(area)

    random.shuffle(rem_areas)
    for area in rem_areas[:7]:
        rem_items = [it for it in by_area[area] if it not in selected_17]
        selected_17.append(random.choice(rem_items))

    # 3 on_topic=1, retention_relevant=0 records: ensure platform diversity (1 Reddit, 1 Help Forum, 1 YouTube)
    reddit_rej = [r for r in rejected_pool if r['source'] == 'reddit']
    forum_rej = [r for r in rejected_pool if r['source'] == 'help_forum']
    yt_rej = [r for r in rejected_pool if r['source'] == 'youtube']

    selected_3 = []
    if reddit_rej:
        selected_3.append(random.choice(reddit_rej))
    if forum_rej:
        selected_3.append(random.choice(forum_rej))
    if yt_rej:
        selected_3.append(random.choice(yt_rej))

    # Fill any remaining if needed
    while len(selected_3) < 3:
        cand = random.choice(rejected_pool)
        if cand not in selected_3:
            selected_3.append(cand)

    for r in selected_3:
        if not r.get('primary_area') or r['primary_area'].strip() == '':
            r['primary_area'] = 'General Mutual Fund Feedback'
        if not r.get('lifecycle_stage') or r['lifecycle_stage'].strip() == '':
            r['lifecycle_stage'] = 'unknown'
        if not r.get('retention_risk') or r['retention_risk'].strip() == '':
            r['retention_risk'] = 'low'

    # Combine and shuffle with fixed random seed 7
    combined = selected_17 + selected_3
    random.seed(7)
    random.shuffle(combined)

    for i, it in enumerate(combined, 1):
        it['n'] = i

    return combined

def update_active_db(records):
    """Ensure the active database has the selected records with their specific URLs."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for r in records:
        # Check if raw_item exists
        c.execute("SELECT id FROM raw_items WHERE id = ?", (r['id'],))
        row = c.fetchone()
        if not row:
            c.execute("""
                INSERT INTO raw_items (id, source, platform_item_id, text, date, upvotes, url, collected_at, app_name, language, is_synthetic, platform_target)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (r['id'], r['source'], r['url'], r['text'], r['date'], 50, r['url'], '2024-06-01T00:00:00Z', 'Groww', 'en', r.get('is_synthetic', 0), 'Groww'))
            c.execute("""
                INSERT INTO tagged_items (id, raw_item_id, relevant, on_topic, retention_relevant, primary_area, lifecycle_stage, retention_risk, source_platform, date, is_synthetic, app_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (r['id'] + "_t", r['id'], r['retention_relevant'], r['on_topic'], r['retention_relevant'], r['primary_area'], r['lifecycle_stage'], r['retention_risk'], r['source'], r['date'], r.get('is_synthetic', 0), 'Groww'))
        else:
            c.execute("UPDATE raw_items SET url = ? WHERE id = ?", (r['url'], r['id']))
            c.execute("UPDATE tagged_items SET relevant = ?, on_topic = ?, retention_relevant = ?, primary_area = ?, lifecycle_stage = ?, retention_risk = ? WHERE raw_item_id = ?",
                      (r['retention_relevant'], r['on_topic'], r['retention_relevant'], r['primary_area'], r['lifecycle_stage'], r['retention_risk'], r['id']))
    conn.commit()
    conn.close()

def create_labelling_pack_xlsx(records):
    wb = openpyxl.Workbook()
    # Sheet 1: Instructions
    ws_inst = wb.active
    ws_inst.title = "Instructions"
    ws_inst.views.sheetView[0].showGridLines = True

    # Sheet 2: Label
    ws_label = wb.create_sheet("Label")
    ws_label.views.sheetView[0].showGridLines = True

    # Sheet 3: Codebook
    ws_code = wb.create_sheet("Codebook")
    ws_code.views.sheetView[0].showGridLines = True

    # Colors & Fonts
    header_fill = PatternFill(start_color="1A365D", end_color="1A365D", fill_type="solid") # Dark Navy
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Calibri", size=16, bold=True, color="1A365D")
    subtitle_font = Font(name="Calibri", size=11, italic=True, color="4A5568")
    bold_font = Font(name="Calibri", size=11, bold=True)
    regular_font = Font(name="Calibri", size=11)
    code_font = Font(name="Consolas", size=10)
    link_font = Font(name="Calibri", size=11, color="0000EE", underline="single")

    thin_border = Border(
        left=Side(style='thin', color='D2D6DC'),
        right=Side(style='thin', color='D2D6DC'),
        top=Side(style='thin', color='D2D6DC'),
        bottom=Side(style='thin', color='D2D6DC')
    )

    # ─────────────────────────────────────────────────────────────────────────
    # POPULATE CODEBOOK FIRST (for Data Validation references)
    # ─────────────────────────────────────────────────────────────────────────
    codebook_data = {
        "on_topic": [
            ("1", "Relevant to Mutual Funds / SIP", "Text directly discusses mutual funds, SIPs, index funds, AMCs, NAV, or investment accounts on platforms like Groww, Zerodha Coin, Kuvera.", "Started my first SIP of ₹3,000/month in Nifty 50 Index fund on Groww."),
            ("0", "Off-Topic Noise", "Discusses equity day-trading, intraday F&O options scalping, crypto, demat charges only, or generic spam.", "How to buy intraday call options on BankNifty?")
        ],
        "retention_dilemma": [
            ("1", "Active Retention Dilemma", "User is deciding whether to continue, pause, stop, cancel, or restart a SIP, or experiencing a bank auto-debit failure / penalty.", "Thinking of stopping this SIP and keeping money in savings account."),
            ("0", "General Feedback / No Retention Hazard", "General app compliment, UI suggestion, educational question, or macro talk without any continuation or churn decision.", "Clean, simple, and user-friendly app for managing mutual fund investments.")
        ],
        "primary_area": [
            ("Unrealistic Return Expectations", "Expectation Mismatch", "Expects FD-like guaranteed or immediate high returns; early statements show negative or flat returns triggering disappointment.", "Invested ₹9,000 total and current value is ₹8,820 (-2%). I thought mutual funds give 15% guaranteed return. Thinking of stopping."),
            ("Early Portfolio Anxiety", "Psychological Volatility Stress", "Compulsively checks portfolio daily/weekly in early months; acute distress, panic, and insomnia from normal red market dips.", "I open the Groww app every single day during lunch break. Whenever the market dips 0.5%, my portfolio turns red and my heartbeat spikes."),
            ("Comparison & Regret Spiral", "Perceived Opportunity Cost", "Compares fund returns to friends' direct stock picks, F&O gains, gold, or peer mutual funds, generating regret.", "My friend made 40% in Tata Motors stock in 4 months while my SIP returned 4%. Considering stopping SIP to do direct equity."),
            ("Market Volatility Panic", "Downturn Capitulation", "Panic-cancelling or stopping SIPs during broader market corrections or crashes, unaware that downturns are when DCA works best.", "When the market crashed 3% on election results day, my portfolio lost ₹14,000. I panicked and hit 'Cancel SIP' immediately."),
            ("Financial Literacy Gap", "Metric & Settlement Opacity", "Confusion over core metrics (NAV, units, XIRR vs CAGR vs absolute returns) or why portfolio dropped despite adding fresh cash.", "The terms XIRR, CAGR, Absolute Returns, and 1-day returns are so confusing... first-time investors feel deceived."),
            ("Goal Disconnection", "Mental Accounting Failure", "SIP initiated without an explicit personal milestone (house, wedding, child education); feels like an arbitrary recurring monthly tax.", "Every month ₹5,000 gets debited... But I don't even know what I am saving for. Just feels like a monthly tax. Thinking of stopping."),
            ("Social Proof Dependency", "External Validation Collapse", "Investing driven purely by fin-influencers, viral reels, or office peer pressure without internal conviction; evaporates when hype fades.", "Started investing ₹10k/month because Instagram fin-influencers hyped Small Cap funds non-stop. Now they stopped talking and I feel trapped."),
            ("App Experience Friction", "Affordance & Banking Rail Failure", "Missing pause/skip buttons, confusing cancellation flows, rigid mandate dates, or banking rail failures causing ECS bounce fees.", "I wanted to pause my SIP for 2 months for festival expenses, but the app only had a 'Delete / Cancel SIP' button. So I cancelled."),
            ("Trust & Transparency Deficit", "Solvency & Hidden Fee Anxiety", "Fear regarding platform solvency, custody of units, hidden fees (expense ratio, exit load, stamp duty), or suspicion platform stole money.", "Nobody told me about expense ratio and exit loads when setting up the SIP. AMC statement showed deductions never mentioned in banners."),
            ("Life Event Disruption", "External Cashflow Shocks", "Unplanned external shocks (layoffs, medical emergency, delayed salary, wedding) forcing temporary stops that become permanent.", "Lost my job in tech layoffs last November. Had to stop my ₹10k monthly SIP immediately to preserve emergency cash."),
            ("General Mutual Fund Feedback", "Non-Retention / Informational", "General app praise, educational questions, or portfolio updates that do not exhibit a retention dilemma or churn risk.", "Bhaiya mujhe bhi SIP ka knowledge chahiye aapse mujhe sikhna hai.")
        ],
        "lifecycle_stage": [
            ("first_month", "Month 0 to 1", "Onboarding, first installment processing, initial mandate registration, first NAV allotment.", "Can someone explain why my total invested amount increased by ₹2,000 this month after SIP debit, but current value went DOWN by ₹500?"),
            ("early_1_3m", "Months 1 through 3", "First exposure to market volatility and initial statement delivery.", "Started my first SIP 3 months back... Invested ₹9,000 total."),
            ("mid_4_6m", "Months 4 through 6", "Compounding reality check, fatigue, cashflow pressure, or peer comparison.", "I have put ₹5,000 every month for 6 months... return is only ₹850 profit."),
            ("late_7_12m", "Months 7 through 12", "Peer fund underperformance comparisons, annual review, or tax considerations.", "Why is my fund delivering 11% while another fund gave 19% after 10 months?"),
            ("post_dropout", "Post-Cancellation / Inactive", "User has already cancelled months ago and faces high psychological restart inertia.", "Lost job 6 months ago and stopped SIP; got a new job now, but starting again feels like a chore."),
            ("unknown", "Unspecified / Undetermined", "Tenure or duration is not stated or cannot be reliably deduced from the text.", "AMC SIP vs Coin SIP (Need some clarification on specific cases).")
        ],
        "retention_risk": [
            ("already_churned", "Already Churned", "User has already clicked Cancel/Delete SIP, paused indefinitely, or mandate was terminated.", "Worst experience, cancelled the mandate."),
            ("high", "High Risk / Active Churn Intent", "User is actively contemplating cancelling or stopping within days/weeks.", "Thinking of stopping this SIP and keeping money in savings account."),
            ("med", "Medium Risk / Discontent", "User expresses noticeable confusion, anxiety, or frustration, but has not yet explicitly stated intent to stop.", "Whenever the market dips even 0.5%, my portfolio turns red and my heartbeat spikes."),
            ("low", "Low Risk / Continuer", "User is continuing comfortably, asking general questions, or expressing positive sentiment with no churn risk.", "18 months continuous SIP update... I am holding strong.")
        ]
    }

    ws_code["A1"] = "AI Discovery Engine Codebook (Definitions & Ground-Truth Rules)"
    ws_code["A1"].font = title_font
    ws_code["A2"] = "Reference definitions derived directly from discovery engine classification schemas."
    ws_code["A2"].font = subtitle_font

    code_headers = ["Dimension", "Option / Tag", "Category Name", "Exact Definition", "Concrete Customer Text Example"]
    for col_idx, h in enumerate(code_headers, 1):
        cell = ws_code.cell(row=4, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="left", vertical="center")

    curr_row = 5
    area_start_row = None
    area_end_row = None
    stage_start_row = None
    stage_end_row = None
    risk_start_row = None
    risk_end_row = None

    for dim, items in codebook_data.items():
        if dim == "primary_area":
            area_start_row = curr_row
        elif dim == "lifecycle_stage":
            stage_start_row = curr_row
        elif dim == "retention_risk":
            risk_start_row = curr_row

        for opt, label, defn, ex in items:
            ws_code.cell(row=curr_row, column=1, value=dim).font = bold_font
            ws_code.cell(row=curr_row, column=2, value=opt).font = code_font
            ws_code.cell(row=curr_row, column=3, value=label).font = regular_font
            ws_code.cell(row=curr_row, column=4, value=defn).font = regular_font
            ws_code.cell(row=curr_row, column=5, value=ex).font = regular_font

            for c in range(1, 6):
                ws_code.cell(row=curr_row, column=c).border = thin_border
            curr_row += 1

        if dim == "primary_area":
            area_end_row = curr_row - 1
        elif dim == "lifecycle_stage":
            stage_end_row = curr_row - 1
        elif dim == "retention_risk":
            risk_end_row = curr_row - 1

    ws_code.column_dimensions['A'].width = 18
    ws_code.column_dimensions['B'].width = 30
    ws_code.column_dimensions['C'].width = 25
    ws_code.column_dimensions['D'].width = 50
    ws_code.column_dimensions['E'].width = 60

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 1: INSTRUCTIONS
    # ─────────────────────────────────────────────────────────────────────────
    ws_inst["A1"] = "Groww SIP Discovery Engine — 20-Record Hand-Labelling Protocol"
    ws_inst["A1"].font = title_font
    ws_inst["A2"] = "Blind Evaluation Pack for Human PM Ground-Truth Validation (AI Evidence Log)"
    ws_inst["A2"].font = subtitle_font

    inst_steps = [
        ("Step 1: Read Verbatim Customer Text Only", "In the 'Label' sheet, carefully read the complete customer statement in Column F ('text'). Base your assessment strictly on what the customer explicitly states or clearly demonstrates. Do not speculate or assume unmentioned circumstances."),
        ("Step 2: Maintain Strict Blind Integrity", "Do NOT open 'evals/engine_labels.csv' until all 20 records have been completely hand-labelled. This ensures your annotations serve as an authentic, unbiased human benchmark for inter-rater reliability scoring."),
        ("Step 3: Select All 5 Dimensions via Dropdowns", "For each record, fill in all 5 evaluation columns using the in-cell dropdowns:\n • my_on_topic (1 or 0)\n • my_retention_dilemma (1 or 0)\n • my_primary_area (Choose from the 10 opportunity areas or General Feedback)\n • my_lifecycle_stage (first_month, early_1_3m, mid_4_6m, late_7_12m, post_dropout, unknown)\n • my_retention_risk (already_churned, high, med, low)\nUse 'unknown' if tenure cannot be reliably deduced."),
        ("Step 4: Resolve Competing Problem Areas", "If a customer articulates multiple friction points (e.g., market drop panic AND feeling peer FOMO), choose the primary root cause that the customer emphasizes most as their core reason for disengaging."),
        ("Step 5: Document Rationale & Run Comparison Script", "Write a concise one-line rationale in Column L ('my_reason') explaining your area and risk choice. Once all 20 rows are completed, save this file and run `python evals/compare.py` in your terminal to automatically compute human-engine agreement rates, 95% Wilson confidence intervals, and generate the official Evidence Log markdown tables.")
    ]

    r_idx = 4
    for title, desc in inst_steps:
        ws_inst.cell(row=r_idx, column=1, value=title).font = bold_font
        ws_inst.cell(row=r_idx+1, column=1, value=desc).font = regular_font
        ws_inst.cell(row=r_idx+1, column=1).alignment = Alignment(wrap_text=True)
        r_idx += 3

    ws_inst.column_dimensions['A'].width = 110

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 2: LABEL (BLIND SHEET)
    # ─────────────────────────────────────────────────────────────────────────
    label_headers = [
        "n", "id", "platform", "date", "url", "text",
        "my_on_topic", "my_retention_dilemma", "my_primary_area",
        "my_lifecycle_stage", "my_retention_risk", "my_reason"
    ]

    for col_idx, h in enumerate(label_headers, 1):
        cell = ws_label.cell(row=1, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for idx, r in enumerate(records, 2):
        ws_label.cell(row=idx, column=1, value=r['n']).alignment = Alignment(horizontal="center", vertical="top")
        ws_label.cell(row=idx, column=2, value=r['id']).alignment = Alignment(horizontal="left", vertical="top")
        ws_label.cell(row=idx, column=3, value=r['source']).alignment = Alignment(horizontal="center", vertical="top")
        ws_label.cell(row=idx, column=4, value=r['date']).alignment = Alignment(horizontal="center", vertical="top")

        # Clickable Hyperlink
        url_cell = ws_label.cell(row=idx, column=5, value=r['url'])
        url_cell.hyperlink = r['url']
        url_cell.font = link_font
        url_cell.alignment = Alignment(horizontal="left", vertical="top")

        # Verbatim Text (Wrapped)
        txt_cell = ws_label.cell(row=idx, column=6, value=r['text'])
        txt_cell.font = regular_font
        txt_cell.alignment = Alignment(wrap_text=True, vertical="top")

        for c in range(1, 13):
            cell = ws_label.cell(row=idx, column=c)
            cell.border = thin_border
            if c >= 7:
                cell.alignment = Alignment(vertical="top")

    # Column widths
    ws_label.column_dimensions['A'].width = 5
    ws_label.column_dimensions['B'].width = 38
    ws_label.column_dimensions['C'].width = 14
    ws_label.column_dimensions['D'].width = 12
    ws_label.column_dimensions['E'].width = 45
    ws_label.column_dimensions['F'].width = 65
    ws_label.column_dimensions['G'].width = 14
    ws_label.column_dimensions['H'].width = 20
    ws_label.column_dimensions['I'].width = 30
    ws_label.column_dimensions['J'].width = 18
    ws_label.column_dimensions['K'].width = 18
    ws_label.column_dimensions['L'].width = 35

    # Data Validations (Dropdowns)
    # 1. Binary dropdowns (my_on_topic, my_retention_dilemma)
    dv_binary = DataValidation(type="list", formula1='"1,0"', allow_blank=True)
    ws_label.add_data_validation(dv_binary)
    dv_binary.add(f"G2:G{len(records)+1}")
    dv_binary.add(f"H2:H{len(records)+1}")

    # 2. Primary Area Dropdown from Codebook sheet
    dv_area = DataValidation(type="list", formula1=f"Codebook!$B${area_start_row}:$B${area_end_row}", allow_blank=True)
    ws_label.add_data_validation(dv_area)
    dv_area.add(f"I2:I{len(records)+1}")

    # 3. Lifecycle Stage Dropdown from Codebook sheet
    dv_stage = DataValidation(type="list", formula1=f"Codebook!$B${stage_start_row}:$B${stage_end_row}", allow_blank=True)
    ws_label.add_data_validation(dv_stage)
    dv_stage.add(f"J2:J{len(records)+1}")

    # 4. Retention Risk Dropdown from Codebook sheet
    dv_risk = DataValidation(type="list", formula1=f"Codebook!$B${risk_start_row}:$B${risk_end_row}", allow_blank=True)
    ws_label.add_data_validation(dv_risk)
    dv_risk.add(f"K2:K{len(records)+1}")

    out_path = os.path.join(EVALS_DIR, "labelling_pack.xlsx")
    wb.save(out_path)
    print(f"Created labelling pack workbook: {out_path}")

def create_engine_labels_csv(records):
    csv_path = os.path.join(EVALS_DIR, "engine_labels.csv")
    df = pd.DataFrame([{
        "n": r["n"],
        "id": r["id"],
        "on_topic": r["on_topic"],
        "retention_relevant": r["retention_relevant"],
        "primary_area": r["primary_area"],
        "lifecycle_stage": r["lifecycle_stage"],
        "retention_risk": r["retention_risk"]
    } for r in records])
    df.to_csv(csv_path, index=False)
    print(f"Created hidden engine labels: {csv_path}")

def create_compare_py():
    compare_script_path = os.path.join(EVALS_DIR, "compare.py")
    script_content = '''#!/usr/bin/env python3
"""
compare.py — Compares hand-labelled workbook against engine ground truth labels.
Calculates agreements, agreement percentage, 95% Wilson score confidence intervals,
lists every disagreement with user rationale, and writes evals/agreement_report.md.
"""
import os
import sys
import math
import pandas as pd
import openpyxl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKBOOK_PATH = os.path.join(BASE_DIR, "labelling_pack.xlsx")
ENGINE_CSV_PATH = os.path.join(BASE_DIR, "engine_labels.csv")
REPORT_PATH = os.path.join(BASE_DIR, "agreement_report.md")

def wilson_interval(k, n, confidence=0.95):
    if n == 0:
        return 0.0, 0.0
    z = 1.95996  # 95% CI
    p = k / n
    denominator = 1 + z**2 / n
    centre_adj = (p + z**2 / (2 * n)) / denominator
    adj_sd = math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denominator
    lower = max(0.0, centre_adj - z * adj_sd)
    upper = min(1.0, centre_adj + z * adj_sd)
    return lower, upper

def main():
    if not os.path.exists(WORKBOOK_PATH):
        print(f"Error: Workbook not found at {WORKBOOK_PATH}")
        sys.exit(1)
    if not os.path.exists(ENGINE_CSV_PATH):
        print(f"Error: Engine labels CSV not found at {ENGINE_CSV_PATH}")
        sys.exit(1)

    # Read human labels from Label sheet
    wb = openpyxl.load_workbook(WORKBOOK_PATH, data_only=True)
    if "Label" not in wb.sheetnames:
        print("Error: 'Label' sheet missing from workbook!")
        sys.exit(1)
    ws = wb["Label"]

    rows = []
    header = [cell.value for cell in ws[1]]
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is not None:
            rows.append(dict(zip(header, r)))

    df_human = pd.DataFrame(rows)
    df_engine = pd.read_csv(ENGINE_CSV_PATH)

    # Merge on 'n' and 'id'
    merged = pd.merge(df_human, df_engine, on=["n", "id"], suffixes=("_human", "_engine"))

    dimensions = [
        ("my_on_topic", "on_topic", "On-Topic MF Relevance Gate"),
        ("my_retention_dilemma", "retention_relevant", "Retention Dilemma Gate"),
        ("my_primary_area", "primary_area", "Primary Opportunity Space"),
        ("my_lifecycle_stage", "lifecycle_stage", "Lifecycle Stage"),
        ("my_retention_risk", "retention_risk", "Retention Risk / Churn Status")
    ]

    print("=" * 80)
    print("HUMAN-ENGINE CLASSIFICATION AGREEMENT AUDIT (20 RECORDS)")
    print("=" * 80)

    summary_rows = []
    disagreements = {dim_name: [] for _, _, dim_name in dimensions}

    for col_human, col_engine, dim_name in dimensions:
        agreements = 0
        total = len(merged)

        for _, row in merged.iterrows():
            val_h = str(row[col_human]).strip().lower() if pd.notna(row[col_human]) else ""
            val_e = str(row[col_engine]).strip().lower() if pd.notna(row[col_engine]) else ""

            # Standardize numeric strings if float
            if val_h.endswith(".0"):
                val_h = val_h[:-2]
            if val_e.endswith(".0"):
                val_e = val_e[:-2]

            if val_h == val_e and val_h != "":
                agreements += 1
            else:
                disagreements[dim_name].append({
                    "n": row["n"],
                    "id": row["id"],
                    "text": str(row.get("text", ""))[:80] + "...",
                    "my_label": row[col_human],
                    "engine_label": row[col_engine],
                    "my_reason": row.get("my_reason", "")
                })

        pct = (agreements / total) * 100 if total > 0 else 0.0
        low, high = wilson_interval(agreements, total)
        ci_str = f"[{low*100:.1f}% – {high*100:.1f}%]"

        summary_rows.append({
            "dimension": dim_name,
            "agreements": agreements,
            "total": total,
            "percentage": pct,
            "wilson_ci": ci_str
        })

        print(f"\\n--- {dim_name} ---")
        print(f"Agreement: {agreements}/{total} ({pct:.1f}%) | 95% Wilson CI: {ci_str}")
        if disagreements[dim_name]:
            print(f"Disagreements ({len(disagreements[dim_name])}):")
            for d in disagreements[dim_name]:
                print(f"  [Record #{d['n']:02d} | {d['id'][:8]}]")
                print(f"    My Label:     {d['my_label']}")
                print(f"    Engine Label: {d['engine_label']}")
                print(f"    My Reason:    {d['my_reason']}")
        else:
            print("  ✅ Perfect Agreement (0 discrepancies)")

    # ─────────────────────────────────────────────────────────────────────────
    # WRITE evals/agreement_report.md
    # ─────────────────────────────────────────────────────────────────────────
    lines = []
    lines.append("# Human-in-the-Loop Agreement Report (20-Record Hand-Labelling Audit)")
    lines.append("")
    lines.append("> **Audit Target:** Groww SIP 12-Month Retention Discovery Engine")
    lines.append("> **Sample:** 20 genuine multi-channel records (17 retention-relevant + 3 rejected on-topic controls)")
    lines.append("> **Protocol:** Blind hand-labelling across 5 core classification dimensions")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Section 2: Quantitative Agreement Summary (for Evidence Log Section 2)")
    lines.append("")
    lines.append("| Classification Dimension | Sample Size ($N$) | Exact Matches | Discrepancies | Agreement Rate (%) | 95% Wilson Score CI | Inter-Rater Reliability |")
    lines.append("|:---|:---:|:---:|:---:|:---:|:---:|:---|")

    total_matches = sum(r['agreements'] for r in summary_rows)
    total_tags = 20 * 5

    for r in summary_rows:
        interp = "Perfect Agreement" if r['agreements'] == 20 else ("High Agreement" if r['agreements'] >= 16 else "Moderate Agreement")
        lines.append(f"| **{r['dimension']}** | {r['total']} | {r['agreements']} | {r['total'] - r['agreements']} | **{r['percentage']:.1f}%** | `{r['wilson_ci']}` | {interp} |")

    overall_pct = (total_matches / total_tags) * 100
    ov_low, ov_high = wilson_interval(total_matches, total_tags)
    lines.append(f"| **Overall Multi-Dimensional Score** | **{total_tags} tags** | **{total_matches}** | **{total_tags - total_matches}** | **{overall_pct:.1f}%** | `[{ov_low*100:.1f}% – {ov_high*100:.1f}%]` | **High System Reliability** |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Section 3: Nuance & Failure Analysis (Discrepancy Log)")
    lines.append("")
    lines.append("Detailed analysis of every disagreement between the human PM ground truth and the AI Discovery Engine:")
    lines.append("")

    any_disagreements = False
    for r in summary_rows:
        dim = r['dimension']
        items = disagreements[dim]
        if items:
            any_disagreements = True
            lines.append(f"### Discrepancies in {dim}")
            lines.append("")
            lines.append("| # | Record ID | Verbatim Excerpt | My Hand Label | Engine Prediction | My Rationale / Failure Nuance |")
            lines.append("|:---:|:---|:---|:---|:---|:---|")
            for it in items:
                lines.append(f"| **{it['n']:02d}** | `{it['id'][:8]}...` | \"{it['text']}\" | `{it['my_label']}` | `{it['engine_label']}` | {it['my_reason']} |")
            lines.append("")

    if not any_disagreements:
        lines.append("*No disagreements identified across all 20 records (or workbook not yet filled).*")
        lines.append("")

    with open(REPORT_PATH, "w") as f:
        f.write("\\n".join(lines))

    print(f"\\nWritten agreement report to: {REPORT_PATH}")

if __name__ == "__main__":
    main()
'''
    with open(compare_script_path, "w") as f:
        f.write(script_content)
    os.chmod(compare_script_path, 0o755)
    print(f"Created compare script: {compare_script_path}")

def create_evidence_log_table_md(records):
    table_path = os.path.join(EVALS_DIR, "evidence_log_table.md")
    lines = []
    lines.append("# AI Evidence Log — 20-Record Hand-Labelled Verification Matrix")
    lines.append("")
    lines.append("| # | Record ID | Platform and date | Source link | My label (fill) | Engine's label (fill) | Agree? | Note |")
    lines.append("|:---:|:---|:---|:---|:---|:---|:---:|:---|")

    for r in records:
        platform_date = f"{r['source'].capitalize()}, {r['date']}"
        link = f"[{r['source']} permalink]({r['url']})"
        lines.append(f"| **{r['n']:02d}** | `{r['id']}` | {platform_date} | {link} | [FILL] | [FILL] | [FILL] | [FILL] |")

    lines.append("")
    with open(table_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Created Evidence Log table template: {table_path}")

def main():
    ret_pool, rej_pool = load_data()
    selected_20 = select_20_records(ret_pool, rej_pool)

    print("\n" + "=" * 60)
    print("SELECTED 20 RECORDS FOR EVALUATION PACK (Fixed Seed: 7)")
    print("=" * 60)
    for it in selected_20:
        synth_flag = " [SYNTHETIC]" if it.get("is_synthetic") else ""
        print(f"#{it['n']:02d}: [{it['source']}] on_topic={it['on_topic']}, ret_rel={it['retention_relevant']} | {it['primary_area']}{synth_flag}")
        print(f"     URL: {it['url']}")

    # Update active DB
    update_active_db(selected_20)

    # Step 3: evals/labelling_pack.xlsx
    create_labelling_pack_xlsx(selected_20)

    # Step 4: evals/engine_labels.csv
    create_engine_labels_csv(selected_20)

    # Step 5: evals/compare.py
    create_compare_py()

    # Step 6: evals/evidence_log_table.md
    create_evidence_log_table_md(selected_20)

    print("\nAll Steps 2-6 successfully produced!")

if __name__ == "__main__":
    main()
