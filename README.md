# NSE Index Analysis Dashboard

Real-time dashboard for NSE India indices built with Streamlit, pandas and Plotly.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Features

- Live data from the NSE `allIndices` API (cookie handshake + retries, 30s cache)
- Auto-refresh (15–300 s) and manual refresh
- Tabs: Overview (KPIs, heatmap), Performance (1D/1W/1M/1Y, 52-week position),
  Top Movers, Valuation (P/E, P/B, dividend yield), Breadth, Data
- Sidebar filters: search, category, gainers/losers, % change range
- CSV download of filtered and full data

## Notes

- NSE rejects requests without browser-like headers and cookies; the app handles this,
  but NSE may still throttle or block cloud-hosted IPs. Running locally works best.
- Outside market hours (9:15–15:30 IST, Mon–Fri) the data shows the last close.
- Data is for information only, not investment advice.
