# 📊 Index Breadth Dashboard

A comprehensive **market breadth dashboard** for tracking 4 major indices — built as a single HTML file with no backend required.

## 🌐 Live Demo

👉 **[Open Dashboard](https://vjtriumph.github.io/index-breadth-dashboard/)**

## ✨ Features

### 4 Index Tabs
- **Nifty 50** — 50 large-cap stocks
- **Nifty Bank** — 12 banking stocks  
- **Nifty IT** — 10 IT sector stocks
- **Nifty Midcap 150** — 50 midcap stocks

### Breadth Metrics (per index)
- **% Stocks Above 20 SMA** — Short-term trend
- **% Stocks Above 50 SMA** — Medium-term trend
- **% Stocks Above 200 SMA** — Long-term trend
- Color-coded: Bullish (>60%) | Neutral (40-60%) | Bearish (<40%)

### 52-Week Analysis
- **Near 52-Week High** — Stocks within 5% of their yearly high
- **Near 52-Week Low** — Stocks within 5% of their yearly low

### Breadth History Charts (per SMA type)
- **1D** — 30 intraday data points
- **1W** — Daily data for past week
- **1M** — Daily data for past month
- **3M** — 3-day interval data for past quarter

### Stock Details Table
- Per-stock price, % change
- SMA status badges (green = above, red = below)
- 52W High/Low proximity tags

## How to Use

1. Open the dashboard (GitHub Pages or local file)
2. Click any index tab (Nifty 50, Bank, IT, Midcap)
3. View breadth cards at the top for quick overview
4. Scroll to history charts and click 1D/1W/1M/3M to switch timeframe
5. Check stock tags for names near 52-week extremes
6. Stock table at the bottom shows individual SMA status

## Customization

To add your own stocks, edit the INDICES array in index.html:

    const INDICES = [
      { id: 'myindex', name: 'My Index', stocks: ['SYMBOL1', 'SYMBOL2', ...] },
    ];

Note: Currently uses simulated/mock data. To connect real data, replace the generateMockData() function with your data provider API.

## Tech Stack

- Pure HTML + CSS + JavaScript (no framework)
- Chart.js for breadth history line charts
- Dark theme UI, fully responsive

---
Made for traders tracking Indian equity market breadth.
