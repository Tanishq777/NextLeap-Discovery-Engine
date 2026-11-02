"""
test_refined_filter.py — Validates refined Two-Level Relevance Filter on empirical corpus.
Eliminates false signals (F&O, intraday, Demat AMC, stock trading, candle charts, login OTP bugs).
"""
import re
import sqlite3
import pandas as pd
import config

# ── 1. Strict Negative Disqualifiers (Off-Topic Kill Patterns) ────────────────
OFF_TOPIC_PATTERNS = [
    # F&O / Derivatives
    r"\b(f&o|fno|futures|options? trading|call option|put option|call and put|call put|strike price|expiry|per lot|lot size|scalping|option buying|option selling|hedging?|bank nifty option|nifty option|ce/pe|ce pe|option chain|open interest|oi)\b",
    # Intraday & Equity Trading
    r"\b(intraday|day trading|swing trading|stop loss|sl order|gtt order|limit order|market order|delivery trading|target price|buy share|sell share|bought share|sold share|buyed a share|penny stock|delivery charges|brokerage per order|60rs per lot|20rs brokerage|t\+1 settlement of share|dividend on share|shares price|share market profit)\b",
    # Charting / Technical Indicators
    r"\b(tradingview|candlestick|candle chart|indicators?|rsi|moving average|chart lag|chart stuck|chart loading|super trend|macd)\b",
    # Demat Account / Stock Broker Maintenance / IPO
    r"\b(demat amc|annual maintenance charge for demat|demat account opening|ipo allotment|ipo mandate|gmp|apply for ipo|bidding in ipo|ipo application)\b",
    # US Stocks & Crypto
    r"\b(us stocks?|us equity|apple stock|tesla stock|crypto|bitcoin|ethereum|binance|wazirx|coinbase)\b",
    # Pure Hardware / App System Glitches with ZERO investment context
    r"\b(camera not opening|biometric login|fingerprint sensor|dark mode option|screen flickering|app crashing on open|aadhaar otp not coming|digilocker otp)\b",
]

# ── 2. Mutual Fund & SIP Core Anchors (Required for On-Topic) ──────────────────
# Must explicitly mention Mutual Funds, SIP, or fund-specific terms
MF_CORE_PATTERNS = [
    r"\b(sip|sips|mutual funds?|mf|mfs|index funds?|small cap funds?|mid cap funds?|large cap funds?|flexi cap|elss|tax saver funds?|debt funds?|liquid funds?|hybrid funds?)\b",
    r"\b(parag parikh|mirae asset|quant small cap|hdfc top 100|nippon india|sbi mutual fund|uti mutual fund|motilal oswal mutual fund|tata digital india|axis bluechip)\b",
    r"\b(amc|amfi|cams|kfintech|folio|folio number|sip installment|sip mandate|sip debit|sip cancel|sip pause|sip bounce|nach mandate|autopay mandate|e-mandate|monthly sip|daily sip|weekly sip)\b",
    r"(एसआईपी|म्यूचुअल फंड|म्युचुअल फंड|सिप|मंथली इन्वेस्टमेंट|एनएवी)",
]

# Dedicated Mutual Fund apps (Zerodha Coin is 100% mutual funds)
COIN_MF_PATTERNS = [
    r"\b(nav|xirr|cagr|units?|allotment|redemption|lumpsum|cut off time|exit load|expense ratio)\b",
]

# ── 3. Retention Signals (Level 2 Gate) ─────────────────────────────────────────
RETENTION_SIGNALS = [
    # Actions on SIP
    r"\b(stop|stopped|cancel|cancelled|pause|paused|skip|skipped|hold|holding|continue|continuing|survive|anniversary|milestone|streak|restarted?)\b",
    # Friction / Banking Failures
    r"\b(bounce|penalty|mandate|auto debit|debit failed|ecs|nach|charge|charges|deducted?|cut|kata|kat gaya|fine|insufficient balance)\b",
    # Metrics confusion / Distress
    r"\b(xirr|nav|units?|statement|negative|loss|crash|dip|red|down|disappoint|guaranteed|expected|compare|fd|fixed deposit|underperform)\b",
    # Financial constraints & Trust
    r"\b(cashflow|salary|emergency|afford|tight|safe|safety|trust|scam|cheat|fraud|worst|bad|waste|pathetic|useless|bug|error|fail|pending|delay)\b",
    r"(बंद|रोक|पॉज़|बाउंस|पेनल्टी|नुकसान|लगातार|पैसा कट|फंस)",
]


def check_refined_relevance(text: str, app_name: str) -> tuple[bool, bool, str]:
    low = text.lower()

    # Rule A: Check for explicit off-topic trading/F&O/crypto keywords
    has_off_topic = any(re.search(p, low) for p in OFF_TOPIC_PATTERNS)

    # Check for core mutual fund / SIP anchor
    has_mf_anchor = any(re.search(p, low) for p in MF_CORE_PATTERNS)
    
    # If app is Zerodha Coin (pure MF platform), also allow standard MF metrics
    if not has_mf_anchor and app_name == "Zerodha Coin":
        has_mf_anchor = any(re.search(p, low) for p in COIN_MF_PATTERNS)

    # If it has off-topic trading keywords AND no explicit SIP/MF keyword, reject immediately!
    if has_off_topic and not has_mf_anchor:
        return False, False, "rejected_off_topic_trading"

    # If it mentions trading but ALSO explicitly mentions SIP/MF comparison (e.g. "stopped SIP to do F&O"), keep it!
    # Otherwise, it MUST have a valid MF/SIP anchor:
    if not has_mf_anchor:
        return False, False, "rejected_no_mf_anchor"

    # It passed Level 1 (On-Topic Mutual Fund)
    on_topic = True

    # Level 2: Retention Relevant
    ret_rel = any(re.search(p, low) for p in RETENTION_SIGNALS)
    if ret_rel:
        return True, True, "passed_retention_relevant"
    else:
        return True, False, "passed_general_mf_feedback"


def main():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, app_name, text FROM raw_items WHERE is_synthetic = 0").fetchall()
    conn.close()

    total = len(rows)
    on_topic_count = 0
    ret_count = 0
    rejected_trading = 0
    rejected_no_anchor = 0
    general_mf = 0

    app_breakdown = {}

    for r in rows:
        app = r["app_name"] or "Unknown"
        text = r["text"]
        ot, rr, reason = check_refined_relevance(text, app)
        
        if app not in app_breakdown:
            app_breakdown[app] = {"total": 0, "on_topic": 0, "retention": 0, "rejected": 0}
        app_breakdown[app]["total"] += 1

        if ot:
            on_topic_count += 1
            app_breakdown[app]["on_topic"] += 1
            if rr:
                ret_count += 1
                app_breakdown[app]["retention"] += 1
            else:
                general_mf += 1
        else:
            app_breakdown[app]["rejected"] += 1
            if reason == "rejected_off_topic_trading":
                rejected_trading += 1
            else:
                rejected_no_anchor += 1

    print("=" * 70)
    print("REFINED TWO-LEVEL RELEVANCE FILTER SIMULATION")
    print(f"Total Raw Items Analyzed: {total:,}")
    print("=" * 70)
    print(f"• Level 1 On-Topic MF Items    : {on_topic_count:,} / {total:,} ({on_topic_count/total*100:.1f}%)")
    print(f"• Level 2 Retention Dilemmas   : {ret_count:,} / {total:,} ({ret_count/total*100:.1f}%)")
    print(f"• General MF Feedback (Excluded): {general_mf:,} / {total:,} ({general_mf/total*100:.1f}%)")
    print(f"• Rejected Off-Topic Trading   : {rejected_trading:,} (F&O, intraday, demat, stock orders)")
    print(f"• Rejected No MF Anchor        : {rejected_no_anchor:,} (generic app bugs, non-MF complaints)")
    print("\n--- Breakdown by App ---")
    for app, stats in sorted(app_breakdown.items(), key=lambda x: x[1]["retention"], reverse=True):
        print(f"{app:25s} | Total: {stats['total']:4d} | On-Topic: {stats['on_topic']:4d} | Retention: {stats['retention']:4d} | Rejected: {stats['rejected']:4d}")


if __name__ == "__main__":
    main()
