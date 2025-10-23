"""
Smart Alpha Dashboard — Data Sources
Hybrid fetcher for Binance Alpha tokens and CoinGecko market data.
"""

import requests
import pandas as pd
import streamlit as st
import traceback
import time


# --------------------------------------------------------------------
# 1️⃣  Binance → CoinGecko hybrid ticker fetcher
# --------------------------------------------------------------------
def get_ticker_24h_all():
    """
    Try Binance first (for Alpha pairs), then fall back to CoinGecko.
    Returns a pandas DataFrame with normalized columns:
        symbol, lastPrice, quoteVolume, source
    """
    # --- Binance mirrors (global) ---
    mirrors = [
        "https://api-gcp.binance.com/api/v3/ticker/24hr",
        "https://data.binance.com/api/v3/ticker/24hr",
        "https://api1.binance.com/api/v3/ticker/24hr",
        "https://api2.binance.com/api/v3/ticker/24hr",
        "https://api3.binance.com/api/v3/ticker/24hr",
    ]

    for url in mirrors:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data)
                df["source"] = "binance"
                st.info(f"✅ Loaded {len(df)} tickers from {url}")
                return df
        except Exception as e:
            st.warning(f"Mirror failed: {url} → {e}")

    # --- Fallback: CoinGecko global market data ---
    st.warning("⚠️ Binance unreachable — using CoinGecko data instead.")
    try:
        markets = []
        for page in range(1, 5):  # up to 1000 coins
            cg_url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "volume_desc",
                "per_page": 250,
                "page": page,
                "sparkline": False,
            }
            r = requests.get(cg_url, params=params, timeout=20)
            r.raise_for_status()
            chunk = r.json()
            if not chunk:
                break
            markets.extend(chunk)
            time.sleep(1)

        df = pd.DataFrame(markets)
        df.rename(
            columns={
                "symbol": "symbol",
                "current_price": "lastPrice",
                "total_volume": "quoteVolume",
            },
            inplace=True,
        )
        df["source"] = "coingecko"
        st.success(f"✅ Loaded {len(df)} tickers from CoinGecko")
        return df
    except Exception as e:
        st.error("❌ Failed fetching both Binance & CoinGecko data")
        st.code(traceback.format_exc())
        return pd.DataFrame()


# --------------------------------------------------------------------
# 2️⃣  Alpha mapping (mock or real)
# --------------------------------------------------------------------
def map_alpha_to_binance():
    """
    Fetch Binance Alpha list. Replace this stub with real Alpha endpoint
    if you have an API key. Returns DataFrame with columns:
        symbol, spot_symbol, alphaId, chainId, contractAddress
    """
    try:
        url = "https://data.binance.com/bapi/asset/v2/public/asset-service/product/get-alpha-list"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        df = pd.DataFrame(data)
        # Normalize key columns
        if "symbol" in df.columns:
            df.rename(columns={"symbol": "base"}, inplace=True)
        df["spot_symbol"] = df["base"].astype(str) + "USDT"
        st.info(f"✅ Loaded {len(df)} Alpha tokens from Binance Alpha endpoint")
        return df
    except Exception as e:
        st.warning(f"⚠️ Could not load Alpha list, using fallback: {e}")
        # fallback static sample
        return pd.DataFrame(
            [
                {"symbol": "SOL", "spot_symbol": "SOLUSDT"},
                {"symbol": "JUP", "spot_symbol": "JUPUSDT"},
                {"symbol": "PYTH", "spot_symbol": "PYTHUSDT"},
            ]
        )


# --------------------------------------------------------------------
# 3️⃣  CoinGecko fundamentals / market data (reused by scoring)
# --------------------------------------------------------------------
def cg_find_id_by_symbol_platform(symbol: str, platform=None):
    """Find CoinGecko ID from symbol (best-effort)."""
    try:
        url = "https://api.coingecko.com/api/v3/coins/list"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = pd.DataFrame(r.json())
        hit = data[data["symbol"].str.lower() == symbol.lower()]
        if not hit.empty:
            return hit.iloc[0]["id"]
    except Exception:
        pass
    return None


def cg_coin_market_data(cg_id: str):
    """Fetch full coin data from CoinGecko."""
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}"
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


# --------------------------------------------------------------------
# 4️⃣  Token unlocks lookup (optional external API)
# --------------------------------------------------------------------
def unlocks_lookup(symbol: str):
    """Fetch unlock schedule from TokenUnlocks API."""
    try:
        url = f"https://token.unlocks.app/api/token/{symbol.lower()}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def parse_next_unlock(data):
    """Parse next unlock event."""
    try:
        if not data:
            return {}
        events = data.get("events") or []
        if not events:
            return {}
        nxt = sorted(events, key=lambda x: x.get("date"))[0]
        return {
            "next_date": nxt.get("date"),
            "next_pct": nxt.get("percent"),
            "next_usd": nxt.get("usd"),
        }
    except Exception:
        return {}


# --------------------------------------------------------------------
# 5️⃣  GitHub repo stats (for developer activity)
# --------------------------------------------------------------------
def github_repo_stats(url):
    """Fetch public GitHub commit stats (approx)."""
    try:
        parts = url.rstrip("/").split("/")
        user, repo = parts[-2], parts[-1]
        api_url = f"https://api.github.com/repos/{user}/{repo}/stats/commit_activity"
        r = requests.get(api_url, timeout=10)
        if r.status_code == 202:
            # stats generating; skip
            return {}
        weeks = r.json()
        commits_30d = sum(w.get("total", 0) for w in weeks[-4:])
        contribs = len(
            set(c["author"]["login"] for w in weeks[-4:] for c in w.get("days", []) if c)
        )
        return {"github_commits_approx": commits_30d, "github_contributors": contribs}
    except Exception:
        return {}
