"""
Index Breadth Dashboard - Python Script
========================================
Fetches live data from Yahoo Finance and replicates the HTML dashboard.
Outputs: console summary + Excel file

Install deps:
    pip install yfinance pandas openpyxl requests

Usage:
    python breadth_dashboard.py
"""

import yfinance as yf
import pandas as pd
import json
import os
import time
import requests
from io import StringIO
from datetime import datetime, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────
BASE_URL = "https://raw.githubusercontent.com/VJTriumph/index-breadth-dashboard/main/data/"

CSV_FILES = [
    {"file": "NIFTY 100.csv",          "name": "Nifty 100",          "indexKey": "NIFTY 100"},
    {"file": "NIFTY MIDCAP 150.csv",   "name": "Nifty Midcap 150",   "indexKey": "NIFTY MIDCAP 150"},
    {"file": "nifty microcap 250.csv", "name": "Nifty Microcap 250", "indexKey": "NIFTY MICROCAP 250"},
    {"file": "nifty smallcap 250.csv", "name": "Nifty Smallcap 250", "indexKey": "NIFTY SMALLCAP 250"},
]

HISTORY_FILE = "breadth_history.json"
BATCH_SIZE   = 20
SLEEP        = 0.4


# ── CSV PARSING ───────────────────────────────────────────────────────────────
def fetch_csv_symbols(file_name, index_key):
    url = BASE_URL + requests.utils.quote(file_name)
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    text = resp.text.strip()
    df = pd.read_csv(StringIO(text), header=0)
    symbols = []
    suffix = " " + index_key
    if df.shape[1] >= 2 and df.shape[0] > 5:
        for val in df.iloc[:, 1].dropna():
            val = str(val).strip().strip('"').upper()
            if val and val not in ("STOCKS", ""):
                symbols.append(val)
    else:
        for col in df.columns[1:]:
            val = str(col).strip().strip('"').upper()
            if val.upper().endswith(index_key):
                val = val[: -len(suffix)].strip()
            else:
                val = val.split()[0].strip()
            if val and val not in ("STOCKS", "INDEX", ""):
                symbols.append(val)
    seen = set()
    unique = []
    for s in symbols:
        if s not in seen and len(s) > 1:
            seen.add(s)
            unique.append(s)
    return unique


# ── YAHOO FINANCE FETCH ───────────────────────────────────────────────────────
def fetch_quotes(symbols):
    results = {}
    ns_syms = [s + ".NS" for s in symbols]
    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=370)
    total = len(ns_syms)
    done  = 0
    for i in range(0, total, BATCH_SIZE):
        batch_ns  = ns_syms[i: i + BATCH_SIZE]
        batch_raw = symbols[i: i + BATCH_SIZE]
        try:
            raw = yf.download(
                batch_ns,
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                interval="1d",
                auto_adjust=True,
                group_by="ticker",
                progress=False,
                threads=True,
            )
        except Exception as e:
            for sym in batch_raw:
                results[sym] = {"symbol": sym, "error": str(e)}
            done += len(batch_raw)
            time.sleep(SLEEP)
            continue
        for j, sym in enumerate(batch_raw):
            ns = batch_ns[j]
            try:
                if len(batch_ns) > 1:
                    closes = raw["Close"][ns].dropna()
                else:
                    closes = raw["Close"].dropna()
                if len(closes) < 5:
                    raise ValueError("Insufficient data")
                price   = float(closes.iloc[-1])
                prev    = float(closes.iloc[-2])
                chg_pct = round((price - prev) / prev * 100, 2)
                high52  = round(float(closes.max()), 2)
                low52   = round(float(closes.min()), 2)
                def sma(n):
                    return round(float(closes.iloc[-n:].mean()), 2) if len(closes) >= n else None
                s20, s50, s200 = sma(20), sma(50), sma(200)
                results[sym] = {
                    "symbol":      sym,
                    "price":       round(price, 2),
                    "changePct":   chg_pct,
                    "sma20":       s20,
                    "sma50":       s50,
                    "sma200":      s200,
                    "aboveSma20":  (price > s20)  if s20  is not None else None,
                    "aboveSma50":  (price > s50)  if s50  is not None else None,
                    "aboveSma200": (price > s200) if s200 is not None else None,
                    "high52":      high52,
                    "low52":       low52,
                    "nearHigh":    price / high52 >= 0.95,
                    "nearLow":     price <= low52 * 1.05,
                    "error":       None,
                }
            except Exception as e:
                results[sym] = {"symbol": sym, "error": str(e)}
        done += len(batch_raw)
        print(f"    [{done}/{total}] fetched")
        time.sleep(SLEEP)
    return results


# ── BREADTH CALCULATION ───────────────────────────────────────────────────────
def calc_breadth(stocks):
    valid  = [s for s in stocks.values() if not s.get("error")]
    errors = [s for s in stocks.values() if s.get("error")]
    n = len(valid)
    if not n:
        return None
    a20  = sum(1 for s in valid if s.get("aboveSma20")  is True)
    a50  = sum(1 for s in valid if s.get("aboveSma50")  is True)
    a200 = sum(1 for s in valid if s.get("aboveSma200") is True)
    return {
        "total": len(stocks), "valid": n, "errors": errors,
        "above20": a20,  "above20Pct":  round(a20  / n * 100, 1),
        "above50": a50,  "above50Pct":  round(a50  / n * 100, 1),
        "above200": a200,"above200Pct": round(a200 / n * 100, 1),
        "nearHigh": [s for s in valid if s.get("nearHigh")],
        "nearLow":  [s for s in valid if s.get("nearLow")],
    }


def color_label(pct):
    return "BULLISH" if pct >= 60 else "NEUTRAL" if pct >= 40 else "BEARISH"


# ── HISTORY ───────────────────────────────────────────────────────────────────
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return {}


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def record_history(history, name, b):
    entry = {"ts": datetime.now().isoformat(), "a20": b["above20Pct"], "a50": b["above50Pct"], "a200": b["above200Pct"]}
    history.setdefault(name, []).append(entry)
    cutoff = datetime.now() - timedelta(days=90)
    history[name] = [e for e in history[name] if datetime.fromisoformat(e["ts"]) >= cutoff]


def get_period_history(history, name, period):
    days = {"1D": 1, "1W": 7, "1M": 30, "3M": 90}.get(period, 30)
    cutoff = datetime.now() - timedelta(days=days)
    return [e for e in history.get(name, []) if datetime.fromisoformat(e["ts"]) >= cutoff]


# ── CONSOLE DISPLAY ───────────────────────────────────────────────────────────
def print_dashboard(name, b, history):
    sep = "─" * 55
    print(f"\n  {sep}")
    print(f"  {name}   ({b['valid']}/{b['total']} stocks | {len(b['errors'])} errors)")
    print(f"  {sep}")
    print(f"  Above 20 SMA  : {b['above20Pct']:5.1f}%  ({b['above20']}/{b['valid']})  [{color_label(b['above20Pct'])}]")
    print(f"  Above 50 SMA  : {b['above50Pct']:5.1f}%  ({b['above50']}/{b['valid']})  [{color_label(b['above50Pct'])}]")
    print(f"  Above 200 SMA : {b['above200Pct']:5.1f}%  ({b['above200']}/{b['valid']})  [{color_label(b['above200Pct'])}]")
    print(f"  Near 52W High : {len(b['nearHigh'])} stocks")
    print(f"  Near 52W Low  : {len(b['nearLow'])} stocks")
    if b["errors"]:
        print(f"  Errors: {[e['symbol'] for e in b['errors'][:10]]}")
    print(f"\n  Breadth History (Above 20 SMA %):")
    for period in ["1D", "1W", "1M", "3M"]:
        ph = get_period_history(history, name, period)
        if ph:
            cur = ph[-1]["a20"]
            prv = ph[-2]["a20"] if len(ph) > 1 else None
            chg = f"  delta{cur - prv:+.1f}%" if prv is not None else ""
            print(f"    {period:>3}: {cur:.1f}%{chg}")
        else:
            print(f"    {period:>3}: -")


# ── EXCEL EXPORT ──────────────────────────────────────────────────────────────
def export_excel(all_data):
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    fname    = f"Index_Breadth_{date_str}.xlsx"
    with pd.ExcelWriter(fname, engine="openpyxl") as writer:
        summary_rows = []
        for name, stocks in all_data.items():
            b = calc_breadth(stocks)
            if not b:
                continue
            summary_rows.append({
                "Index": name, "Total": b["total"], "Valid": b["valid"],
                "Errors": len(b["errors"]),
                "Above 20 SMA %": b["above20Pct"], "Above 50 SMA %": b["above50Pct"],
                "Above 200 SMA %": b["above200Pct"],
                "Near 52W High": len(b["nearHigh"]), "Near 52W Low": len(b["nearLow"]),
                "Signal 20": color_label(b["above20Pct"]),
                "Signal 50": color_label(b["above50Pct"]),
                "Signal 200": color_label(b["above200Pct"]),
                "Updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)
        for name, stocks in all_data.items():
            rows = []
            for s in stocks.values():
                def yn(val):
                    if val is True: return "YES"
                    if val is False: return "NO"
                    return "N/A"
                rows.append({
                    "Symbol": s["symbol"], "Price (Rs)": s.get("price"),
                    "Change %": s.get("changePct"),
                    "SMA 20": s.get("sma20"), "SMA 50": s.get("sma50"), "SMA 200": s.get("sma200"),
                    "Above SMA 20": yn(s.get("aboveSma20")),
                    "Above SMA 50": yn(s.get("aboveSma50")),
                    "Above SMA 200": yn(s.get("aboveSma200")),
                    "52W High": s.get("high52"), "52W Low": s.get("low52"),
                    "Near 52W High": "YES" if s.get("nearHigh") else "NO",
                    "Near 52W Low":  "YES" if s.get("nearLow")  else "NO",
                    "Error": s.get("error") or "",
                })
            pd.DataFrame(rows).to_excel(writer, sheet_name=name[:31], index=False)
    print(f"\n  Excel saved: {fname}")
    return fname


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Index Breadth Dashboard - Python")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)
    history  = load_history()
    all_data = {}
    for cfg in CSV_FILES:
        print(f"\nLoading: {cfg['name']} ...")
        try:
            symbols = fetch_csv_symbols(cfg["file"], cfg["indexKey"])
            print(f"  Symbols: {len(symbols)}")
            if not symbols:
                raise ValueError("No symbols found")
            stocks = fetch_quotes(symbols)
            b      = calc_breadth(stocks)
            if b is None:
                print(f"  No valid data for {cfg['name']}")
                continue
            all_data[cfg["name"]] = stocks
            record_history(history, cfg["name"], b)
            print_dashboard(cfg["name"], b, history)
        except Exception as e:
            print(f"  Failed {cfg['name']}: {e}")
    save_history(history)
    print(f"\n  History saved: {HISTORY_FILE}")
    if all_data:
        export_excel(all_data)
    print("\n" + "=" * 55)
    print("  Done!")
    print("=" * 55)


if __name__ == "__main__":
    main()
