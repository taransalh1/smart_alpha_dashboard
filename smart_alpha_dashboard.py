import warnings
warnings.filterwarnings("ignore")

import streamlit as st
from datetime import datetime, UTC
import traceback
import pandas as pd

# ✅ Page setup
st.set_page_config(page_title="Smart Alpha Dashboard", layout="wide")
st.title("🧠 Smart Alpha Dashboard (Diagnostic Mode)")
st.caption("Binance Alpha coins + fundamentals + unlocks + dev activity")

# ✅ Verify Streamlit is actually running
st.write("🚀 App booted at:", datetime.now(UTC))

# ✅ Try imports safely
try:
    from core import data_sources as ds, scoring, utils
except Exception as e:
    st.error("❌ Import failure in core modules")
    st.code(traceback.format_exc())
    st.stop()

# ✅ Optional timestamp for auto-refresh
try:
    st.query_params["ts"] = str(datetime.now(UTC).timestamp())
except Exception:
    pass

# Sidebar / Theme selector (just to test)
st.sidebar.title("Settings")
st.sidebar.radio("Theme", ["Dark", "Light"], index=0)

# ✅ Try to fetch live data safely
try:
    with st.spinner("Fetching Binance Alpha token data..."):
        alpha_map = ds.map_alpha_to_binance()
        st.write("✅ Alpha map loaded:", len(alpha_map), "tokens")

    with st.spinner("Fetching 24h ticker data..."):
        stats = ds.get_ticker_24h_all()
        st.write("✅ Binance ticker data:", len(stats), "rows")

    # Demo dataframe (so you see something even if APIs fail)
    demo = pd.DataFrame({
        "Token": ["PYTH", "JUP", "BONK"],
        "Price": [0.45, 0.85, 0.000013],
        "Alpha Score": [82, 67, 74],
        "Next Unlock (days)": [12, 5, 20],
    })
    st.subheader("Demo Data")
    st.dataframe(demo, use_container_width=True)

except Exception as e:
    st.error("❌ Runtime error while fetching data")
    st.code(traceback.format_exc())
    st.stop()

st.success("✅ Dashboard loaded successfully (diagnostic mode)")
