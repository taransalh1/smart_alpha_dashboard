import io
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, UTC, timedelta, timezone

from core.utils import fmt_usd, fmt_pct, st_theme_toggle, safe_float
from core import data_sources as ds
from core import scoring as sc

# -------------------------
# PAGE CONFIG
# -------------------------
st.set_page_config(page_title="Smart Alpha Dashboard", layout="wide")
st.title("🧠 Smart Alpha Dashboard (Binance Alpha)")
st.caption("Combines Binance Alpha-only tokens with fundamentals, unlock schedules, TVL/dev activity, and market momentum.")

# -------------------------
# SIDEBAR CONTROLS
# -------------------------
theme = st_theme_toggle()
with st.sidebar:
    st.header("Controls")
    auto = st.checkbox("Auto-refresh", True)
    refresh_sec = st.slider("Refresh every (seconds)", 30, 300, 90, 10)
    min_qvol = st.number_input("Min 24h Quote Volume (USDT)", value=5_000_000.0, step=500_000.0, format="%.0f")
    topn = st.slider("Show Top N", 10, 100, 30, 5)

if auto:
    st.query_params["ts"] = str(datetime.now(UTC).timestamp())

# -------------------------
# FETCH ALPHA TOKENS
# -------------------------
with st.spinner("Fetching Binance Alpha list..."):
    try:
        alpha_map = ds.map_alpha_to_binance()
    except Exception as e:
        st.error(f"Failed to load Alpha list: {e}")
        st.stop()

if alpha_map.empty:
    st.error("No Binance Alpha tokens matched USDT spot pairs right now.")
    st.stop()

# -------------------------
# FETCH 24H STATS
# -------------------------
try:
    stats = ds.get_ticker_24h_all()
except Exception as e:
    st.error(f"Failed to fetch 24h ticker data: {e}")
    st.stop()

# -------------------------
# ASSEMBLE METRICS
# -------------------------
rows = []
for _, r in alpha_map.iterrows():
    sym = r["spot_symbol"]
    base = r["symbol"]
    strow = stats[stats["symbol"] == sym]
    if strow.empty:
        continue
    qvol = float(strow["quoteVolume"].iloc[0])
    if qvol < min_qvol:
        continue
    price = float(strow["lastPrice"].iloc[0])

    # --- klines ---
    try:
        kl1h = ds.get_klines(sym, "1h", 60)
        kl15 = ds.get_klines(sym, "15m", 48)
    except Exception:
        kl1h, kl15 = None, None

    def pct_from(kl, n):
        if not kl or len(kl) < 2:
            return None
        sub = kl[-n:] if len(kl) >= n else kl
        a = float(sub[0][4])
        b = float(sub[-1][4])
        return (b - a) / a * 100.0 if a > 0 else None

    chg_15m = pct_from(kl15, 2) if kl15 else None
    chg_1h = pct_from(kl1h, 2) if kl1h else None
    chg_4h = pct_from(kl1h, 5) if kl1h else None
    chg_24h = pct_from(kl1h, 25) if kl1h else None
    vol_last_1h = float(kl1h[-1][5]) if kl1h else None
    vol_prev_6h = (
        sum(float(x[5]) for x in (kl1h[-7:-1] if kl1h and len(kl1h) >= 7 else [])) / 6 if kl1h else None
    )
    vol_accel = (vol_last_1h + 1) / (vol_prev_6h + 1) if (vol_last_1h and vol_prev_6h) else None

    # --- CoinGecko Fundamentals ---
    cg_id = ds.cg_find_id_by_symbol_platform(base, None)
    mcap = fdv = circ_ratio = None
    gh_commits = gh_contribs = None
    if cg_id:
        try:
            md = ds.cg_coin_market_data(cg_id)
            mkt = md.get("market_data", {})
            mcap = safe_float(mkt.get("market_cap", {}).get("usd"), None)
            fdv = safe_float(mkt.get("fully_diluted_valuation", {}).get("usd"), None)
            circ = safe_float(mkt.get("circulating_supply"), None)
            total = safe_float(mkt.get("total_supply"), None)
            circ_ratio = (circ / total) if (circ and total and total > 0) else None

            # GitHub activity
            links = md.get("links", {})
            gh = (links.get("repos_url") or {}).get("github") or []
            if gh:
                gh_stats = ds.github_repo_stats(gh[0])
                gh_commits = gh_stats.get("github_commits_approx")
                gh_contribs = gh_stats.get("github_contributors")
        except Exception:
            pass

    # --- Token unlocks ---
    next_unlock_days = next_unlock_pct = next_unlock_usd = None
    try:
        un = ds.unlocks_lookup(base)
        pu = ds.parse_next_unlock(un or {})
        if pu.get("next_date"):
            dt = pd.to_datetime(pu["next_date"], utc=True)
            days = (dt - pd.Timestamp.now(tz=UTC)).total_seconds() / 86400.0
            next_unlock_days = days
        next_unlock_pct = pu.get("next_pct")
        next_unlock_usd = pu.get("next_usd")
    except Exception:
        pass

    # --- Scores ---
    mom = sc.momentum_score(chg_15m, chg_1h, chg_4h, chg_24h, vol_accel)
    fund = sc.fundamental_score(mcap, fdv, circ_ratio)
    unl = sc.unlock_risk_score(next_unlock_days, next_unlock_pct)
    use = sc.usage_dev_score(None, None, gh_commits, gh_contribs)
    smart = sc.smart_alpha_score(dict(momentum=mom, fundamentals=fund, unlock=unl, usage=use))

    rows.append(
        dict(
            symbol=sym,
            base=base,
            price_usd=price,
            quoteVolume_24h=qvol,
            chg_15m_pct=chg_15m,
            chg_1h_pct=chg_1h,
            chg_4h_pct=chg_4h,
            chg_24h_pct=chg_24h,
            vol_accel_1h_vs_6h=vol_accel,
            market_cap_usd=mcap,
            fdv_usd=fdv,
            circ_ratio=circ_ratio,
            next_unlock_days=next_unlock_days,
            next_unlock_pct=next_unlock_pct,
            next_unlock_usd=next_unlock_usd,
            github_commits_30d=gh_commits,
            github_contributors=gh_contribs,
            alpha_score=smart,
            alphaId=r.get("alphaId"),
            chainId=r.get("chainId"),
            contractAddress=r.get("contractAddress"),
        )
    )

# -------------------------
# BUILD DATAFRAME
# -------------------------
df = pd.DataFrame(rows)
if df.empty:
    st.warning("No Alpha tokens met your filters right now.")
    st.stop()

df = df.sort_values("alpha_score", ascending=False)

# -------------------------
# DISPLAY TABLE & CHARTS
# -------------------------
show_cols = [
    "symbol","price_usd","quoteVolume_24h",
    "chg_15m_pct","chg_1h_pct","chg_4h_pct","chg_24h_pct",
    "vol_accel_1h_vs_6h",
    "market_cap_usd","fdv_usd","circ_ratio",
    "next_unlock_days","next_unlock_pct","next_unlock_usd",
    "github_commits_30d","github_contributors",
    "alpha_score","alphaId","chainId","contractAddress"
]

st.subheader("Top Smart Alpha Picks")
st.dataframe(df[show_cols].head(topn), use_container_width=True, hide_index=True)

# Heatmap bar
st.markdown("### Smart Alpha Score Heatmap")
heat = px.bar(df.head(topn), x="symbol", y="alpha_score", color="alpha_score", color_continuous_scale="Viridis")
st.plotly_chart(heat, use_container_width=True)

# Scatter plot
st.markdown("### Market Cap vs 24h Volume")
scat = px.scatter(
    df.head(topn),
    x="market_cap_usd",
    y="quoteVolume_24h",
    size="alpha_score",
    hover_name="symbol",
    labels={"market_cap_usd": "Market Cap (USD)", "quoteVolume_24h": "24h Quote Volume (USD)"}
)
st.plotly_chart(scat, use_container_width=True)

# Mini price charts
st.markdown("### Mini Price Charts (15m close)")
cols = st.columns(3)
for i, sym in enumerate(df["symbol"].head(6).tolist()):
    with cols[i % 3]:
        try:
            kl = ds.get_klines(sym, "15m", 96)
            t = [pd.to_datetime(x[0], unit="ms") for x in kl]
            c = [float(x[4]) for x in kl]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=t, y=c, mode="lines", name=sym))
            fig.update_layout(
                title=sym,
                xaxis_title="Time",
                yaxis_title="Price (USDT)",
                height=300,
                margin=dict(l=40, r=20, t=40, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.write(f"{sym}: chart unavailable")

# -------------------------
# EXPORTS
# -------------------------
st.markdown("### Export")
csv = df.to_csv(index=False).encode("utf-8")
st.download_button("Download CSV", data=csv, file_name="smart_alpha_scan.csv", mime="text/csv")

try:
    import openpyxl
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="SmartAlpha")
    st.download_button(
        "Download Excel",
        data=out.getvalue(),
        file_name="smart_alpha_scan.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
except Exception:
    st.caption("Install openpyxl for Excel export.")
