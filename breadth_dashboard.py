"""
Index Breadth Dashboard - Python Script
========================================
Fetches live data from Yahoo Finance and writes data/breadth.json
for the HTML dashboard to consume (no CORS issues, no rate limits).

Install deps: pip install yfinance pandas requests
Usage:        python breadth_dashboard.py
"""

import yfinance as yf
import pandas as pd
import json
import os
import time
import requests
from io import StringIO
from datetime import datetime, timedelta

# ── CONFIG ───────────────────────────────────────────────────────────────────
BASE_URL   = "https://raw.githubusercontent.com/VJTriumph/index-breadth-dashboard/main/data/"
CSV_FILES  = [
    {"file": "NIFTY 100.csv",         "name": "Nifty 100",        "indexKey": "NIFTY 100"},
    {"file": "NIFTY MIDCAP 150.csv",  "name": "Nifty Midcap 150", "indexKey": "NIFTY MIDCAP 150"},
    {"file": "nifty microcap 250.csv","name": "Nifty Microcap 250","indexKey": "NIFTY MICROCAP 250"},
    {"file": "nifty smallcap 250.csv","name": "Nifty Smallcap 250","indexKey": "NIFTY SMALLCAP 250"},
]
OUTPUT_JSON   = os.path.join("data", "breadth.json")
HISTORY_FILE  = "breadth_history.json"
BATCH_SIZE    = 20
SLEEP         = 0.5

# ── CSV PARSING ──────────────────────────────────────────────────────────────
def fetch_csv_symbols(file_name, index_key):
    url  = BASE_URL + requests.utils.quote(file_name)
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    lines = resp.text.strip().split("\n")
    symbols = []
    for line in lines[1:]:          # skip header
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

# ── YAHOO FINANCE FETCH ──────────────────────────────────────────────────────
def fetch_quotes(symbols):
    results  = {}
    ns_syms  = [s + ".NS" for s in symbols]
    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=370)
    total = len(ns_syms); done = 0

    for i in range(0, total, BATCH_SIZE):
        batch_ns  = ns_syms[i: i + BATCH_SIZE]
        batch_raw = symbols[i: i + BATCH_SIZE]
        try:
            raw = yf.download(
                batch_ns,
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                interval="1d", auto_adjust=True,
                group_by="ticker", progress=False, threads=True,
            )
        except Exception as e:
            for sym in batch_raw:
                results[sym] = {"symbol": sym, "error": str(e)}
            done += len(batch_raw); time.sleep(SLEEP); continue

        for j, sym in enumerate(batch_raw):
            ns = batch_ns[j]
            try:
                closes = (raw["Close"][ns] if len(batch_ns) > 1 else raw["Close"]).dropna()
                if len(closes) < 5:
                    raise ValueError("Insufficient data")
                price    = float(closes.iloc[-1])
                prev     = float(closes.iloc[-2])
                chg_pct  = round((price - prev) / prev * 100, 2)
                high52   = round(float(closes.max()), 2)
                low52    = round(float(closes.min()), 2)
                def sma(n): return round(float(closes.iloc[-n:].mean()), 2) if len(closes) >= n else None
                s20, s50, s200 = sma(20), sma(50), sma(200)
                results[sym] = {
                    "symbol": sym,
                    "price":  round(price, 2),
                    "changePct": chg_pct,
                    "sma20": s20, "sma50": s50, "sma200": s200,
                    "aboveSma20":  (price > s20)  if s20  else None,
                    "aboveSma50":  (price > s50)  if s50  else None,
                    "aboveSma200": (price > s200) if s200 else None,
                    "high52": high52, "low52": low52,
                    "nearHigh": price / high52 >= 0.95,
                    "nearLow":  price <= low52 * 1.05,
                    "error": None,
                }
            except Exception as e:
                results[sym] = {"symbol": sym, "error": str(e)}
        done += len(batch_raw)
        print(f"  [{done}/{total}] fetched")
        time.sleep(SLEEP)
    return results

# ── BREADTH CALCULATION ──────────────────────────────────────────────────────
def calc_breadth(stocks):
    valid  = [s for s in stocks.values() if not s.get("error")]
    errors = [s for s in stocks.values() if s.get("error")]
    n = len(valid)
    if not n: return None
    a20  = sum(1 for s in valid if s.get("aboveSma20")  is True)
    a50  = sum(1 for s in valid if s.get("aboveSma50")  is True)
    a200 = sum(1 for s in valid if s.get("aboveSma200") is True)
    return {
        "total": len(stocks), "valid": n, "errors": [e["symbol"] for e in errors],
        "above20": a20, "above20Pct": round(a20/n*100, 1),
        "above50": a50, "above50Pct": round(a50/n*100, 1),
        "above200":a200,"above200Pct":round(a200/n*100, 1),
        "nearHigh": [s["symbol"] for s in valid if s.get("nearHigh")],
        "nearLow":  [s["symbol"] for s in valid if s.get("nearLow")],
    }

def color_label(pct):
    return "BULLISH" if pct >= 60 else "NEUTRAL" if pct >= 40 else "BEARISH"

# ── HISTORY ──────────────────────────────────────────────────────────────────
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def record_history(history, name, b):
    entry = {"ts": datetime.now().isoformat(),
             "a20": b["above20Pct"], "a50": b["above50Pct"], "a200": b["above200Pct"]}
    history.setdefault(name, []).append(entry)
    cutoff = datetime.now() - timedelta(days=90)
    history[name] = [e for e in history[name]
                     if datetime.fromisoformat(e["ts"]) >= cutoff]

# ── JSON OUTPUT ───────────────────────────────────────────────────────────────
def write_breadth_json(all_data, all_breadth, history):
    """Write data/breadth.json consumed by index.html"""
    payload = {
        "updatedAt": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "indices": {}
    }
    for name, stocks in all_data.items():
        b = all_breadth.get(name)
        if not b:
            continue
        payload["indices"][name] = {
            "breadth":  b,
            "history":  history.get(name, []),
            "stocks":   list(stocks.values()),
        }
    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n  JSON saved: {OUTPUT_JSON}  ({os.path.getsize(OUTPUT_JSON)//1024} KB)")

# ── CONSOLE DISPLAY ──────────────────────────────────────────────────────────
def print_dashboard(name, b):
    sep = "─" * 55
    print(f"\n  {sep}")
    print(f"  {name}  ({b['valid']}/{b['total']} stocks | {len(b['errors'])} errors)")
    print(f"  {sep}")
    print(f"  Above 20 SMA  : {b['above20Pct']:5.1f}%  [{color_label(b['above20Pct'])}]")
    print(f"  Above 50 SMA  : {b['above50Pct']:5.1f}%  [{color_label(b['above50Pct'])}]")
    print(f"  Above 200 SMA : {b['above200Pct']:5.1f}%  [{color_label(b['above200Pct'])}]")
    print(f"  Near 52W High : {len(b['nearHigh'])} stocks")
    print(f"  Near 52W Low  : {len(b['nearLow'])} stocks")
    if b["errors"]:
        print(f"  Errors        : {b['errors'][:10]}")

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Index Breadth Dashboard - Python")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    history    = load_history()
    all_data   = {}
    all_breadth= {}

    for cfg in CSV_FILES:
        print(f"\nLoading: {cfg['name']} ...")
        try:
            symbols = fetch_csv_symbols(cfg["file"], cfg["indexKey"])
            print(f"  Symbols: {len(symbols)}")
            if not symbols:
                raise ValueError("No symbols found")
            stocks = fetch_quotes(symbols)
            b = calc_breadth(stocks)
            if b is None:
                print(f"  No valid data for {cfg['name']}")
                continue
            all_data[cfg["name"]]    = stocks
            all_breadth[cfg["name"]] = b
            record_history(history, cfg["name"], b)
            print_dashboard(cfg["name"], b)
        except Exception as e:
            print(f"  Failed {cfg['name']}: {e}")

    save_history(history)
    print(f"\n  History saved: {HISTORY_FILE}")

    if all_data:
        write_breadth_json(all_data, all_breadth, history)

    print("\n" + "=" * 55)
    print("  Done!")
    print("=" * 55)

if __name__ == "__main__":
    main()
