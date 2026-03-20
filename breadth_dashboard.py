"""
Index Breadth Dashboard - Python Script
========================================
Fetches live data from Yahoo Finance and writes data/breadth.json
and data/breadth_crosscheck.csv for the HTML dashboard to consume.

Install: pip install yfinance pandas requests
Usage:   python breadth_dashboard.py
"""
import yfinance as yf
import pandas as pd
import json, os, time, csv, requests
from io import StringIO
from datetime import datetime, timedelta, timezone

# -- CONFIG --
BASE_URL  = "https://raw.githubusercontent.com/VJTriumph/index-breadth-dashboard/main/data/"
CSV_FILES = [
            {"file": "NIFTY 100.csv",          "name": "Nifty 100",        "indexKey": "NIFTY 100"},
            {"file": "NIFTY MIDCAP 150.csv",   "name": "Nifty Midcap 150", "indexKey": "NIFTY MIDCAP 150"},
            {"file": "nifty microcap 250.csv", "name": "Nifty Microcap 250","indexKey": "NIFTY MICROCAP 250"},
            {"file": "nifty smallcap 250.csv", "name": "Nifty Smallcap 250","indexKey": "NIFTY SMALLCAP 250"},
]
OUTPUT_JSON     = os.path.join("data", "breadth.json")
OUTPUT_CSV      = os.path.join("data", "breadth_crosscheck.csv")
HISTORY_FILE    = "breadth_history.json"
SLEEP           = 0.3

# IST = UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

# Historical periods: label -> trading days back
PERIODS = {"1D": 1, "1W": 5, "1M": 21, "3M": 63}

# 52-week high/low proximity threshold: 7%
NEAR_HIGH_THRESHOLD = 0.93   # price / high52 >= 0.93  (within 7% of high)
NEAR_LOW_THRESHOLD  = 1.07   # price <= low52 * 1.07   (within 7% of low)

# -- CSV PARSING --
def fetch_csv_symbols(file_name, index_key):
            url = BASE_URL + requests.utils.quote(file_name)
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            symbols = []
            for line in resp.text.strip().split("\n")[1:]:
                            cols = line.split(",")
                            if len(cols) >= 2:
                                                sym = cols[1].strip().strip('"').upper()
                                                if sym and sym not in ("STOCKS", "INDEX", ""):
                                                                        symbols.append(sym)
                                                            seen, unique = set(), []
                                        for s in symbols:
                                                        if s not in seen and len(s) > 1:
                                                                            seen.add(s); unique.append(s)
                                                                    return unique

# -- YAHOO FINANCE FETCH --
def fetch_one(symbol):
            ns  = symbol + ".NS"
            end = datetime.today()
            start = end - timedelta(days=375)
            try:
                            tk = yf.Ticker(ns)
                            df = tk.history(
                                start=start.strftime("%Y-%m-%d"),
                                end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
                                interval="1d",
                                auto_adjust=True
                            )
                            if df is None or df.empty or len(df) < 5:
                                                return {"symbol": symbol, "error": "Insufficient data"}
                                            closes = df["Close"].dropna()
                            if len(closes) < 5:
                                                return {"symbol": symbol, "error": "Insufficient closes"}

                            today_close = float(closes.iloc[-1])
                            prev_close  = float(closes.iloc[-2]) if len(closes) >= 2 else today_close

                try:
                                    fi   = tk.fast_info
                                    live = fi.get("last_price") or fi.get("regularMarketPrice")
                                    price = round(float(live), 2) if live and float(live) > 0 else round(today_close, 2)
except Exception:
            price = round(today_close, 2)

        chgPct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0.0
        high52 = round(float(closes.max()), 2)
        low52  = round(float(closes.min()), 2)

        def sma_at(offset, n):
                            end_idx = len(closes) - offset
                            if end_idx < n: return None
                                                return round(float(closes.iloc[end_idx - n:end_idx].mean()), 2)

        def price_at(offset):
                            idx = len(closes) - 1 - offset
            if idx < 0: return None
                                return float(closes.iloc[idx])

        s20, s50, s200 = sma_at(0, 20), sma_at(0, 50), sma_at(0, 200)

        hist_above = {}
        for period_label, days_back in PERIODS.items():
                            p_price = price_at(days_back)
            p_s20   = sma_at(days_back, 20)
            p_s50   = sma_at(days_back, 50)
            p_s200  = sma_at(days_back, 200)
            hist_above[period_label] = {
                                    "price":      round(p_price, 2) if p_price is not None else None,
                                    "aboveSma20": (p_price > p_s20)  if (p_price and p_s20)  else None,
                                    "aboveSma50": (p_price > p_s50)  if (p_price and p_s50)  else None,
                                    "aboveSma200":(p_price > p_s200) if (p_price and p_s200) else None,
            }

        # 7% proximity thresholds
        near_high = (price / high52 >= NEAR_HIGH_THRESHOLD) if high52 else False
        near_low  = (price <= low52 * NEAR_LOW_THRESHOLD)   if low52  else False

        return {
                            "symbol":     symbol,
                            "price":      price,
                            "changePct":  chgPct,
                            "sma20":      s20,
                            "sma50":      s50,
                            "sma200":     s200,
                            "aboveSma20": (price > s20)  if s20  is not None else None,
                            "aboveSma50": (price > s50)  if s50  is not None else None,
                            "aboveSma200":(price > s200) if s200 is not None else None,
                            "high52":     high52,
                            "low52":      low52,
                            "nearHigh":   near_high,
                            "nearLow":    near_low,
                            "hist":       hist_above,
                            "error":      None,
        }
except Exception as e:
        return {"symbol": symbol, "error": str(e)[:120]}

def fetch_all(symbols):
            results = {}
            for i, sym in enumerate(symbols):
                            results[sym] = fetch_one(sym)
        if (i + 1) % 10 == 0:
                            print(f"  [{i+1}/{len(symbols)}] done")
        time.sleep(SLEEP)
    return results

# -- BREADTH --
def calc_breadth(stocks):
            valid  = [s for s in stocks.values() if not s.get("error")]
    errors = [s["symbol"] for s in stocks.values() if s.get("error")]
    n = len(valid)
    if not n: return None

                    a20  = sum(1 for s in valid if s.get("aboveSma20")  is True)
    a50  = sum(1 for s in valid if s.get("aboveSma50")  is True)
    a200 = sum(1 for s in valid if s.get("aboveSma200") is True)

    hist_breadth = {}
    for period_label in PERIODS:
                    h20  = sum(1 for s in valid if s.get("hist", {}).get(period_label, {}).get("aboveSma20")  is True)
        h50  = sum(1 for s in valid if s.get("hist", {}).get(period_label, {}).get("aboveSma50")  is True)
        h200 = sum(1 for s in valid if s.get("hist", {}).get(period_label, {}).get("aboveSma200") is True)
        hist_breadth[period_label] = {
                            "above20":    h20,
                            "above20Pct": round(h20/n*100, 1),
                            "above50":    h50,
                            "above50Pct": round(h50/n*100, 1),
                            "above200":   h200,
                            "above200Pct":round(h200/n*100, 1),
        }

    return {
                    "total":      len(stocks),
                    "valid":      n,
                    "errors":     errors,
                    "above20":    a20,
                    "above20Pct": round(a20/n*100, 1),
                    "above50":    a50,
                    "above50Pct": round(a50/n*100, 1),
                    "above200":   a200,
                    "above200Pct":round(a200/n*100, 1),
                    "nearHigh":   [s["symbol"] for s in valid if s.get("nearHigh")],
                    "nearLow":    [s["symbol"] for s in valid if s.get("nearLow")],
                    "histBreadth":hist_breadth,
    }

def color_label(p):
            return "BULLISH" if p >= 60 else "NEUTRAL" if p >= 40 else "BEARISH"

# -- HISTORY --
def load_history():
            if os.path.exists(HISTORY_FILE):
                            with open(HISTORY_FILE) as f:
                                                return json.load(f)
                                        return {}

def save_history(h):
            with open(HISTORY_FILE, "w") as f:
                            json.dump(h, f, indent=2)

def record_history(h, name, b):
            now_ist = datetime.now(IST)
    entry = {
                    "ts":  now_ist.strftime("%Y-%m-%dT%H:%M:%S+05:30"),
                    "a20": b["above20Pct"],
                    "a50": b["above50Pct"],
                    "a200":b["above200Pct"]
    }
    h.setdefault(name, []).append(entry)
    cutoff = datetime.now(IST) - timedelta(days=90)
    h[name] = [
                    e for e in h[name]
                    if datetime.fromisoformat(e["ts"]) >= cutoff
    ]

# -- CSV CROSS-CHECK EXPORT --
def write_crosscheck_csv(all_data, all_breadth):
            """Write a CSV file with all stock data for manual cross-checking."""
    os.makedirs("data", exist_ok=True)
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")

    header = [
                    "FetchedAt", "Index", "Symbol", "Price", "ChangePct",
                    "SMA20", "SMA50", "SMA200",
                    "AboveSMA20", "AboveSMA50", "AboveSMA200",
                    "High52W", "Low52W",
                    "NearHigh_7pct", "NearLow_7pct",
                    "PriceToHigh52_pct", "PriceToLow52_pct",
                    "Hist_1D_SMA20", "Hist_1D_SMA50", "Hist_1D_SMA200",
                    "Hist_1W_SMA20", "Hist_1W_SMA50", "Hist_1W_SMA200",
                    "Hist_1M_SMA20", "Hist_1M_SMA50", "Hist_1M_SMA200",
                    "Hist_3M_SMA20", "Hist_3M_SMA50", "Hist_3M_SMA200",
                    "Error"
    ]

    rows = []
    for name, stocks in all_data.items():
                    for sym, s in stocks.items():
                                        def yn(v):
                                                                if v is True:  return "YES"
                                                                                        if v is False: return "NO"
                                                                                                                return "N/A"
                                                            def pct_to_high(s):
                                                                                    if s.get("price") and s.get("high52") and s["high52"] > 0:
                                                                                                                return round((s["price"] / s["high52"] - 1) * 100, 2)
                                                                                                            return ""
            def pct_to_low(s):
                                    if s.get("price") and s.get("low52") and s["low52"] > 0:
                                                                return round((s["price"] / s["low52"] - 1) * 100, 2)
                return ""
            def h(period, key):
                                    return yn(s.get("hist", {}).get(period, {}).get(key))

            rows.append([
                                    now_ist, name, s.get("symbol",""), s.get("price",""), s.get("changePct",""),
                                    s.get("sma20",""), s.get("sma50",""), s.get("sma200",""),
                                    yn(s.get("aboveSma20")), yn(s.get("aboveSma50")), yn(s.get("aboveSma200")),
                                    s.get("high52",""), s.get("low52",""),
                                    "YES" if s.get("nearHigh") else "NO",
                                    "YES" if s.get("nearLow")  else "NO",
                                    pct_to_high(s), pct_to_low(s),
                                    h("1D","aboveSma20"), h("1D","aboveSma50"), h("1D","aboveSma200"),
                                    h("1W","aboveSma20"), h("1W","aboveSma50"), h("1W","aboveSma200"),
                                    h("1M","aboveSma20"), h("1M","aboveSma50"), h("1M","aboveSma200"),
                                    h("3M","aboveSma20"), h("3M","aboveSma50"), h("3M","aboveSma200"),
                                    s.get("error","")
            ])

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    size = os.path.getsize(OUTPUT_CSV)
    print(f"\n  CSV cross-check saved -> {OUTPUT_CSV} ({size//1024} KB, {len(rows)} rows)")

    # Also print index-level summary
    print("\n  === INDEX BREADTH SUMMARY ===")
    for name, b in all_breadth.items():
                    print(f"\n  {name}:")
        print(f"    Total={b['total']} Valid={b['valid']} Errors={len(b['errors'])}")
        print(f"    Above20SMA={b['above20Pct']}% [{color_label(b['above20Pct'])}]  "
                            f"Above50SMA={b['above50Pct']}%  Above200SMA={b['above200Pct']}%")
        print(f"    NearHigh(7%)={len(b['nearHigh'])}  NearLow(7%)={len(b['nearLow'])}")
        hb = b.get("histBreadth", {})
        for pl in ["1D","1W","1M","3M"]:
                            if pl in hb:
                                                    print(f"    {pl}: 20SMA={hb[pl]['above20Pct']}% | "
                                                                                f"50SMA={hb[pl]['above50Pct']}% | "
                                                                                f"200SMA={hb[pl]['above200Pct']}%")

# -- JSON OUTPUT --
def write_breadth_json(all_data, all_breadth, history):
            now_ist = datetime.now(IST)
    payload = {
                    "updatedAt": now_ist.strftime("%Y-%m-%d %H:%M IST"),
                    "indices": {}
    }
    for name, stocks in all_data.items():
                    b = all_breadth.get(name)
        if not b: continue
                        payload["indices"][name] = {
                                            "breadth":  b,
                                            "history":  history.get(name, []),
                                            "stocks":   list(stocks.values()),
                        }
    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
                    json.dump(payload, f)
    size = os.path.getsize(OUTPUT_JSON)
    print(f"\n  JSON saved -> {OUTPUT_JSON} ({size//1024} KB, {len(payload['indices'])} indices)")

# -- MAIN --
def main():
            print("=" * 55)
    print("  Index Breadth Dashboard")
    now_ist = datetime.now(IST)
    print(f"  {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"  52W Threshold: {int((1-NEAR_HIGH_THRESHOLD)*100)}% near High, "
                    f"{int((NEAR_LOW_THRESHOLD-1)*100)}% near Low")
    print("=" * 55)

    history   = load_history()
    all_data  = {}
    all_breadth = {}

    for cfg in CSV_FILES:
                    print(f"\n-- {cfg['name']} --")
        try:
                            symbols = fetch_csv_symbols(cfg["file"], cfg["indexKey"])
            print(f"  Symbols loaded: {len(symbols)}")
            if not symbols:
                                    print("  WARN: no symbols found, skipping")
                continue
            stocks = fetch_all(symbols)
            b = calc_breadth(stocks)
            if b is None:
                                    print(f"  WARN: no valid data for {cfg['name']}")
                continue
            all_data[cfg["name"]]    = stocks
            all_breadth[cfg["name"]] = b
            record_history(history, cfg["name"], b)
            print(f"  Valid: {b['valid']}/{b['total']} | "
                                    f"20SMA={b['above20Pct']}% [{color_label(b['above20Pct'])}] | "
                                    f"50SMA={b['above50Pct']}% | 200SMA={b['above200Pct']}%")
            if b["errors"]:
                                    print(f"  Errors ({len(b['errors'])}): {b['errors'][:5]}")
except Exception as e:
            print(f"  ERROR: {cfg['name']} -> {e}")

    save_history(history)
    print(f"\n  History saved: {HISTORY_FILE}")

    if all_data:
                    write_breadth_json(all_data, all_breadth, history)
        write_crosscheck_csv(all_data, all_breadth)
else:
        print("\n  ERROR: No data fetched for any index -- breadth.json NOT written")
        raise SystemExit(1)

    print("\n" + "=" * 55 + "\n  Done!" + "\n" + "=" * 55)

if __name__ == "__main__":
            main()
