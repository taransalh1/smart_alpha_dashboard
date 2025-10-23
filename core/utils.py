import os
import time
from functools import lru_cache
from typing import Any, Dict, Optional

from dotenv import load_dotenv
import streamlit as st
import requests

# Load .env locally; on Streamlit Cloud use st.secrets
load_dotenv()

def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    # Prefer Streamlit secrets if available
    try:
        if "secrets" in dir(st) and key in st.secrets:
            return st.secrets.get(key, default)
    except Exception:
        pass
    return os.getenv(key, default)

class HttpClient:
    def __init__(self, user_agent: str = "smart-alpha/1.0"):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def jget(self, url: str, params: Dict[str, Any] = None, retries: int = 3, timeout: int = 20, headers: Dict[str, str] = None):
        last_err = None
        for i in range(retries):
            try:
                h = dict(headers or {})
                r = self.session.get(url, params=params, timeout=timeout, headers=h)
                if r.status_code in (429, 418, 520, 525):
                    time.sleep(1 + i)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                time.sleep(0.5 * (i + 1))
        raise last_err or RuntimeError("HTTP GET failed")

http = HttpClient()

def fmt_usd(x):
    try:
        x = float(x)
    except Exception:
        return "—"
    if x >= 1e9: return f"${x/1e9:.2f}B"
    if x >= 1e6: return f"${x/1e6:.2f}M"
    if x >= 1e3: return f"${x/1e3:.2f}K"
    return f"${x:.2f}"

def fmt_pct(x):
    try:
        return f"{float(x):.2f}%"
    except Exception:
        return "—"

def safe_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default

def st_theme_mode():
    mode = st.session_state.get("theme_mode", "Dark")
    return mode

def st_theme_toggle():
    choice = st.sidebar.radio("Theme", ["Dark","Light"], index=0 if st.session_state.get("theme_mode","Dark")=="Dark" else 1)
    st.session_state["theme_mode"] = choice
    return choice
