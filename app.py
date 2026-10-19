"""
Real-time NSE Index Analysis Dashboard
Run:  streamlit run app.py
"""

import time
from contextlib import contextmanager
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:  # optional dependency
    st_autorefresh = None

# --------------------------------------------------------------------------
# Page config
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="NSE Index Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

NSE_HOME = "https://www.nseindia.com"
NSE_ALL_INDICES = "https://www.nseindia.com/api/allIndices"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/live-market-indices",
}

NUMERIC_COLS = [
    "last", "variation", "percentChange", "open", "high", "low",
    "previousClose", "yearHigh", "yearLow", "pe", "pb", "dy",
    "advances", "declines", "unchanged",
    "perChange365d", "perChange30d",
    "previousDay", "oneWeekAgo", "oneMonthAgo", "oneYearAgo",
]

RENAME = {
    "index": "Index",
    "last": "Last",
    "variation": "Change",
    "percentChange": "% Change",
    "open": "Open",
    "high": "High",
    "low": "Low",
    "previousClose": "Prev Close",
    "yearHigh": "52W High",
    "yearLow": "52W Low",
    "pe": "P/E",
    "pb": "P/B",
    "dy": "Div Yield %",
    "advances": "Advances",
    "declines": "Declines",
    "unchanged": "Unchanged",
    "perChange365d": "1Y %",
    "perChange30d": "1M %",
}


# --------------------------------------------------------------------------
# Data layer
# --------------------------------------------------------------------------
def _new_session() -> requests.Session:
    """NSE blocks bare API calls: hit the home page first to obtain cookies."""
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get(NSE_HOME, timeout=10)
    return s


@st.cache_data(ttl=300, show_spinner=False)
def fetch_indices(bucket: int = 0) -> tuple[pd.DataFrame, str]:
    """Fetch all NSE indices. `bucket` is a time slice (now // interval), so the cache
    expires once per refresh interval."""
    last_err = None
    for attempt in range(3):
        try:
            session = _new_session()
            r = session.get(NSE_ALL_INDICES, timeout=15)
            r.raise_for_status()
            payload = r.json()
            df = pd.DataFrame(payload["data"])
            for c in NUMERIC_COLS:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            # Derived metrics
            df["rangePos"] = (
                (df["last"] - df["low"]) / (df["high"] - df["low"]).replace(0, np.nan)
            ) * 100
            df["from52wHigh"] = (df["last"] / df["yearHigh"] - 1) * 100
            df["from52wLow"] = (df["last"] / df["yearLow"] - 1) * 100
            if "oneWeekAgo" in df.columns:
                df["perChange7d"] = (df["last"] / df["oneWeekAgo"] - 1) * 100
            ts = payload.get("timestamp") or datetime.now().strftime("%d-%b-%Y %H:%M:%S")
            return df, ts
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Could not fetch data from NSE: {last_err}")


def categorize(name: str) -> str:
    n = name.upper()
    if n.startswith("NIFTY") and any(k in n for k in ["BANK", "FIN", "IT", "PHARMA", "AUTO",
            "FMCG", "METAL", "REALTY", "ENERGY", "MEDIA", "PSU", "INFRA", "OIL",
            "HEALTH", "CONSUMER", "COMMODITIES", "SERVICES", "MNC", "CPSE", "CHEMICALS"]):
        return "Sectoral / Thematic"
    if any(k in n for k in ["50", "100", "200", "500", "NEXT", "MIDCAP", "SMALLCAP",
            "MICROCAP", "LARGEMIDCAP", "TOTAL MARKET"]):
        return "Broad Market"
    if any(k in n for k in ["ALPHA", "QUALITY", "VALUE", "MOMENTUM", "LOW VOL",
            "DIVIDEND", "EQUAL", "FACTOR", "GROWTH", "TARGET", "BETA"]):
        return "Strategy"
    if "VIX" in n:
        return "Volatility"
    return "Other"


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------
st.sidebar.title("⚙️ Controls")

auto = st.sidebar.toggle("Auto-refresh", value=True)
interval = st.sidebar.slider("Refresh interval (sec)", 1, 300, 60, step=1, disabled=not auto)
if auto and st_autorefresh is not None:
    st_autorefresh(interval=interval * 1000, key="nse_autorefresh")
elif auto:
    st.sidebar.warning("Install `streamlit-autorefresh` for auto-refresh.")

if st.sidebar.button("🔄 Refresh now", use_container_width=True):
    fetch_indices.clear()
    st.rerun()

# --------------------------------------------------------------------------
# Load data
# --------------------------------------------------------------------------
st.title("📈 NSE Index Analysis Dashboard")

try:
    with st.spinner("Fetching live NSE data…"):
        raw, as_of = fetch_indices(int(time.time() // (interval if auto else 30)))
except Exception as e:  # noqa: BLE001
    st.error(str(e))
    st.info("NSE sometimes throttles requests or blocks cloud IPs. "
            "Try again in a moment, or run the app locally.")
    st.stop()

raw = raw.copy()
raw["Category"] = raw["index"].apply(categorize)

# Filters
st.sidebar.subheader("Filters")
search = st.sidebar.text_input("🔍 Search index", placeholder="e.g. BANK, IT, MIDCAP")
cats = sorted(raw["Category"].unique())
sel_cats = st.sidebar.multiselect("Category", cats, default=cats)
direction = st.sidebar.radio("Direction", ["All", "Gainers", "Losers"], horizontal=True)
pct_min, pct_max = float(raw["percentChange"].min()), float(raw["percentChange"].max())
if pct_min < pct_max:
    pct_range = st.sidebar.slider("% Change range", pct_min, pct_max, (pct_min, pct_max), step=0.05)
else:
    pct_range = (pct_min, pct_max)

df = raw[raw["Category"].isin(sel_cats)]
if search:
    df = df[df["index"].str.contains(search, case=False, na=False)]
if direction == "Gainers":
    df = df[df["percentChange"] > 0]
elif direction == "Losers":
    df = df[df["percentChange"] < 0]
df = df[df["percentChange"].between(*pct_range)]

st.caption(f"Data as of **{as_of}** (IST) · {len(df)} of {len(raw)} indices shown · "
           f"fetched {datetime.now().strftime('%H:%M:%S')}")

if df.empty:
    st.warning("No indices match the current filters.")
    st.stop()

# --------------------------------------------------------------------------
# Tabs
# --------------------------------------------------------------------------
tab_over, tab_perf, tab_move, tab_val, tab_breadth, tab_data = st.tabs(
    ["🏠 Overview", "📊 Performance", "🚀 Top Movers", "💰 Valuation", "🌐 Breadth", "📄 Data"]
)


@contextmanager
def safe(tab):
    """Render a tab; show the real error inside it instead of crashing the whole app."""
    with tab:
        try:
            yield
        except Exception as e:  # noqa: BLE001
            st.error("This tab hit an error. Details below.")
            st.exception(e)

# ---- Overview -------------------------------------------------------------
with safe(tab_over):
    key_names = ["NIFTY 50", "NIFTY BANK", "NIFTY NEXT 50", "NIFTY MIDCAP 100",
                 "NIFTY IT", "INDIA VIX"]
    key = raw[raw["index"].isin(key_names)].set_index("index").reindex(
        [k for k in key_names if k in set(raw["index"])]
    )
    cols = st.columns(max(len(key), 1))
    for col, (name, row) in zip(cols, key.iterrows()):
        col.metric(name, f"{row['last']:,.2f}", f"{row['variation']:+,.2f} ({row['percentChange']:+.2f}%)")

    st.markdown("---")
    c1, c2 = st.columns([3, 2])

    with c1:
        st.subheader("Market heatmap")
        heat = df.dropna(subset=["last", "percentChange"]).copy()
        heat["size"] = heat["last"].abs()
        heat = heat[heat["size"] > 0]
        fig = px.treemap(
            heat, path=["Category", "index"], values="size",
            color="percentChange", color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
            range_color=(-max(abs(heat["percentChange"]).max(), 0.5),
                         max(abs(heat["percentChange"]).max(), 0.5)),
            hover_data={"percentChange": ":.2f", "last": ":,.2f", "size": False},
        )
        fig.update_traces(textinfo="label+text", texttemplate="%{label}<br>%{color:.2f}%")
        fig.update_layout(height=520, margin=dict(t=10, l=0, r=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Gainers vs Losers")
        counts = pd.DataFrame({
            "Status": ["Up", "Down", "Flat"],
            "Count": [(df["percentChange"] > 0).sum(),
                      (df["percentChange"] < 0).sum(),
                      (df["percentChange"] == 0).sum()],
        })
        fig = px.pie(counts, names="Status", values="Count", hole=0.55, color="Status",
                     color_discrete_map={"Up": "#16a34a", "Down": "#dc2626", "Flat": "#9ca3af"})
        fig.update_layout(height=250, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Average % change by category")
        cat_avg = df.groupby("Category", as_index=False)["percentChange"].mean()
        fig = px.bar(cat_avg, x="percentChange", y="Category", orientation="h",
                     color="percentChange", color_continuous_scale="RdYlGn",
                     color_continuous_midpoint=0)
        fig.update_layout(height=250, margin=dict(t=10, b=10), coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

# ---- Performance ----------------------------------------------------------
with safe(tab_perf):
    st.subheader("Performance across time horizons")
    horizons = {"Today": "percentChange", "1 Week": "perChange7d",
                "1 Month": "perChange30d", "1 Year": "perChange365d"}
    horizons = {k: v for k, v in horizons.items() if v in df.columns}
    metric_label = st.radio("Horizon", list(horizons), horizontal=True)
    metric = horizons[metric_label]

    top_n = st.slider("Number of indices", 5, min(60, len(df)), min(25, len(df)))
    ranked = df.dropna(subset=[metric]).sort_values(metric, ascending=False).head(top_n)
    fig = px.bar(ranked.sort_values(metric), x=metric, y="index", orientation="h",
                 color=metric, color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                 labels={metric: f"{metric_label} %", "index": ""})
    fig.update_layout(height=max(400, top_n * 22), coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Position within 52-week range")
    rng = df.dropna(subset=["yearHigh", "yearLow"]).copy()
    rng["pos52"] = (rng["last"] - rng["yearLow"]) / (rng["yearHigh"] - rng["yearLow"]) * 100
    fig = px.scatter(rng, x="pos52", y="perChange365d", color="Category", hover_name="index",
                     labels={"pos52": "% of 52W range (0 = low, 100 = high)",
                             "perChange365d": "1Y change %"})
    fig.add_vline(x=50, line_dash="dot", line_color="gray")
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    fig.update_layout(height=450)
    st.plotly_chart(fig, use_container_width=True)

# ---- Top Movers -----------------------------------------------------------
with safe(tab_move):
    n = st.slider("Show top N", 3, 20, 10, key="movers_n")
    g, l = st.columns(2)
    cols_show = ["index", "last", "variation", "percentChange"]
    with g:
        st.subheader("🟢 Top gainers")
        gain = df.nlargest(n, "percentChange")[cols_show].rename(columns=RENAME)
        st.dataframe(gain.style.format({"Last": "{:,.2f}", "Change": "{:+,.2f}", "% Change": "{:+.2f}%"})
                     .map(lambda v: "color: #16a34a", subset=["% Change"]),
                     hide_index=True, use_container_width=True)
    with l:
        st.subheader("🔴 Top losers")
        lose = df.nsmallest(n, "percentChange")[cols_show].rename(columns=RENAME)
        st.dataframe(lose.style.format({"Last": "{:,.2f}", "Change": "{:+,.2f}", "% Change": "{:+.2f}%"})
                     .map(lambda v: "color: #dc2626", subset=["% Change"]),
                     hide_index=True, use_container_width=True)

    st.subheader("Intraday range position")
    st.caption("Where each index is trading between today's low (0%) and high (100%).")
    pos = df.dropna(subset=["rangePos"]).nlargest(25, "percentChange")
    fig = go.Figure(go.Bar(x=pos["rangePos"], y=pos["index"], orientation="h",
                           marker_color="#2563eb"))
    fig.update_layout(height=600, xaxis_title="% of day's range", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, use_container_width=True)

# ---- Valuation ------------------------------------------------------------
with safe(tab_val):
    st.subheader("Valuation metrics")
    val = df.dropna(subset=["pe", "pb"])
    val = val[(val["pe"] > 0) & (val["pb"] > 0)]
    if val.empty:
        st.info("No valuation data for the current selection.")
    else:
        fig = px.scatter(val, x="pe", y="pb", size="dy" if val["dy"].notna().any() else None,
                         color="Category", hover_name="index",
                         labels={"pe": "P/E", "pb": "P/B", "dy": "Dividend yield %"})
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

        v1, v2 = st.columns(2)
        with v1:
            st.markdown("**Cheapest by P/E**")
            st.dataframe(val.nsmallest(10, "pe")[["index", "pe", "pb", "dy"]].rename(columns=RENAME),
                         hide_index=True, use_container_width=True)
        with v2:
            st.markdown("**Most expensive by P/E**")
            st.dataframe(val.nlargest(10, "pe")[["index", "pe", "pb", "dy"]].rename(columns=RENAME),
                         hide_index=True, use_container_width=True)

# ---- Breadth --------------------------------------------------------------
with safe(tab_breadth):
    st.subheader("Constituent breadth (advances vs declines)")
    br = df.dropna(subset=["advances", "declines"]).copy()
    br = br[(br["advances"] + br["declines"]) > 0]
    if br.empty:
        st.info("No breadth data for the current selection.")
    else:
        br["adRatio"] = br["advances"] / br["declines"].replace(0, np.nan)
        br["advPct"] = br["advances"] / (br["advances"] + br["declines"] + br["unchanged"].fillna(0)) * 100
        pick = st.multiselect("Indices", br["index"].tolist(),
                              default=[i for i in ["NIFTY 50", "NIFTY BANK", "NIFTY IT",
                                                   "NIFTY MIDCAP 100", "NIFTY NEXT 50"]
                                       if i in set(br["index"])] or br["index"].head(8).tolist())
        sub = br[br["index"].isin(pick)]
        fig = go.Figure()
        fig.add_bar(x=sub["index"], y=sub["advances"], name="Advances", marker_color="#16a34a")
        fig.add_bar(x=sub["index"], y=sub["declines"], name="Declines", marker_color="#dc2626")
        fig.add_bar(x=sub["index"], y=sub["unchanged"].fillna(0), name="Unchanged", marker_color="#9ca3af")
        fig.update_layout(barmode="group", height=450)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Strongest breadth (% of constituents advancing)**")
        st.dataframe(br.nlargest(10, "advPct")[["index", "advances", "declines", "advPct"]]
                     .rename(columns={**RENAME, "advPct": "% Advancing"})
                     .style.format({"% Advancing": "{:.0f}%"}),
                     hide_index=True, use_container_width=True)

# ---- Data -----------------------------------------------------------------
with safe(tab_data):
    st.subheader("Full data table")
    table_cols = [c for c in RENAME if c in df.columns] + ["Category"]
    table = df[table_cols].rename(columns=RENAME).sort_values("% Change", ascending=False)
    st.dataframe(table, hide_index=True, use_container_width=True, height=520)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Download filtered data (CSV)",
                       table.to_csv(index=False).encode("utf-8"),
                       file_name=f"nse_indices_filtered_{stamp}.csv", mime="text/csv",
                       use_container_width=True)
    d2.download_button("⬇️ Download all indices (CSV)",
                       raw.drop(columns=["Category"]).to_csv(index=False).encode("utf-8"),
                       file_name=f"nse_indices_all_{stamp}.csv", mime="text/csv",
                       use_container_width=True)

st.markdown("---")
st.caption("Source: NSE India public API. Data may be delayed and is for informational purposes only — "
           "not investment advice.")
