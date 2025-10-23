from typing import Dict, Any, List, Optional
from datetime import datetime
import time
import re

import requests
import pandas as pd
import traceback
import streamlit as st

from .utils import http, get_secret, safe_float

BINANCE_PRIMARY = "https://api1.binance.com"
BINANCE_BACKUP = "https://api2.binance.com"
BINANCE_DATA = "https://data-api.binance.vision"  # read-only public mirror
ALPHA_LIST = "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"
COINGECKO = "https://pro-api.coingecko.com/api/v3"
DEFILLAMA = "https://api.llama.fi"
TOKENUNLOCKS = "https://api.token.unlocks.app"  # community api; may vary

# ---------------- Binance ----------------
def get_exchange_info() -> Dict[str, Any]:
    """Get Binance spot exchange info with fallback mirrors."""
    for base in [BINANCE_PRIMARY, BINANCE_BACKUP, BINANCE_DATA]:
        try:
            return http.jget(f"{base}/api/v3/exchangeInfo")
        except Exception:
            continue
    raise RuntimeError("All Binance mirrors failed for /exchangeInfo")


def get_usdt_spot_symbols() -> List[str]:
    ex = get_exchange_info()
    return [s["symbol"] for s in ex.get("symbols", []) if s.get("status")=="TRADING" and s.get("quoteAsset")=="USDT"]

def get_ticker_24h_all():
    """Fetch 24h ticker data from Binance with error safety."""
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            st.warning("⚠️ Binance returned unexpected format.")
            return pd.DataFrame()
        df = pd.DataFrame(data)
        if df.empty:
            st.warning("⚠️ Binance returned empty ticker data.")
        return df
    except Exception as e:
        st.error(f"❌ Binance API error: {e}")
        st.code(traceback.format_exc())
        return pd.DataFrame()

def get_klines(symbol: str, interval: str = "15m", limit: int = 96):
    return http.jget(f"{BINANCE}/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": limit})

# ---------------- Binance Alpha ----------------

def get_alpha_token_list() -> pd.DataFrame:
    data = http.jget(ALPHA_LIST)
    tokens = data.get("data") if isinstance(data, dict) else data
    tokens = tokens or []
    rows = []
    for t in tokens:
        rows.append({
            "alphaId": t.get("alphaId") or t.get("id"),
            "symbol": (t.get("symbol") or "").upper(),
            "name": t.get("name"),
            "chainId": t.get("chainId"),
            "contractAddress": t.get("contractAddress"),
            "projectId": t.get("projectId"),
            "logo": t.get("logo") or t.get("logoUrl"),
        })
    return pd.DataFrame(rows)

def map_alpha_to_binance() -> pd.DataFrame:
    alpha = get_alpha_token_list()
    syms = set(get_usdt_spot_symbols())
    rows = []
    for _, r in alpha.iterrows():
        base = r["symbol"]
        if not base: continue
        spot = f"{base}USDT"
        if spot in syms:
            out = r.to_dict()
            out["spot_symbol"] = spot
            rows.append(out)
    return pd.DataFrame(rows)

# ---------------- CoinGecko ----------------

def cg_headers():
    key = get_secret("COINGECKO_API_KEY", None)
    return {"x-cg-pro-api-key": key} if key else {}

def cg_coin_list_with_platforms() -> List[Dict[str, Any]]:
    return http.jget(f"{COINGECKO}/coins/list", params={"include_platform":"true"}, headers=cg_headers())

def cg_find_id_by_symbol_platform(symbol_upper: str, platform: Optional[str] = None) -> Optional[str]:
    sym = symbol_upper.lower()
    key = get_secret("COINGECKO_API_KEY", None)
    headers = {"x-cg-pro-api-key": key} if key else {}
    # Try lightweight search first
    try:
        res = http.jget(f"{COINGECKO}/search", params={"query": sym}, headers=headers)
        coins = res.get("coins", [])
        for c in coins:
            if c.get("symbol", "").lower() == sym:
                return c.get("id")
        if coins:
            return coins[0].get("id")
    except Exception:
        pass

    # fallback (only if necessary)
    try:
        res = http.jget(f"{COINGECKO}/coins/list", params={"include_platform": "true"}, headers=headers)
        for c in res:
            if c.get("symbol", "").lower() == sym:
                return c.get("id")
    except Exception:
        pass
    return None


def cg_coin_market_data(coin_id: str) -> Dict[str, Any]:
    params = dict(localization="false", tickers="false", market_data="true", community_data="true", developer_data="true", sparkline="false")
    return http.jget(f"{COINGECKO}/coins/{coin_id}", params=params, headers=cg_headers())

# ---------------- TokenUnlocks ----------------

def unlocks_lookup(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Community API varies; we implement a best-effort:
    - Try search by symbol
    - Return next unlock event (date, percent, amount) if present
    """
    key = get_secret("TOKENUNLOCKS_API_KEY", None)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        res = http.jget(f"{TOKENUNLOCKS}/v1/token/{symbol.upper()}", headers=headers)
        return res
    except Exception:
        # fallback basic search endpoint if available
        try:
            res = http.jget(f"{TOKENUNLOCKS}/v1/search", params={"q": symbol.upper()}, headers=headers)
            return res
        except Exception:
            return None

def parse_next_unlock(unlocks: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a dict: {"next_date": iso, "next_pct": float, "next_usd": float}
    Handle flexible payloads.
    """
    out = {"next_date": None, "next_pct": None, "next_usd": None}
    if not isinstance(unlocks, dict):
        return out
    # naive parsing
    evs = unlocks.get("upcoming") or unlocks.get("events") or []
    if isinstance(evs, dict): evs = [evs]
    if evs:
        e = evs[0]
        out["next_date"] = e.get("date") or e.get("time") or e.get("unlockDate")
        out["next_pct"] = safe_float(e.get("percent") or e.get("pct") or e.get("percentage"), None)
        out["next_usd"] = safe_float(e.get("usdValue") or e.get("valueUsd") or e.get("usd"), None)
    return out

# ---------------- DefiLlama ----------------

def llama_search(protocol: str) -> Optional[Dict[str, Any]]:
    try:
        return http.jget(f"{DEFILLAMA}/search", params={"q": protocol})
    except Exception:
        return None

def llama_protocol_tvl(slug: str) -> Optional[Dict[str, Any]]:
    try:
        return http.jget(f"{DEFILLAMA}/protocol/{slug}")
    except Exception:
        return None

# ---------------- GitHub ----------------

def github_repo_stats(repo_url: str) -> Dict[str, Any]:
    """
    Minimal stats: commit count last 30d & contributors.
    If token's CoinGecko links include github, we try HEAD requests.
    """
    import re
    import requests
    token = get_secret("GITHUB_TOKEN", None)
    headers = {"Authorization": f"token {token}"} if token else {}
    m = re.match(r"https?://github.com/([^/]+)/([^/]+)", repo_url or "")
    if not m:
        return {}
    owner, repo = m.group(1), m.group(2).rstrip("/")
    try:
        commits = http.jget(f"https://api.github.com/repos/{owner}/{repo}/commits", params={"per_page": 100}, headers=headers)
        commit_count = len(commits) if isinstance(commits, list) else 0
    except Exception:
        commit_count = None
    try:
        contribs = http.jget(f"https://api.github.com/repos/{owner}/{repo}/contributors", params={"per_page": 100}, headers=headers)
        contrib_count = len(contribs) if isinstance(contribs, list) else 0
    except Exception:
        contrib_count = None
    return {"github_commits_approx": commit_count, "github_contributors": contrib_count}
