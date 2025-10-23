import streamlit as st, traceback

st.set_page_config(page_title="Debug Loader", layout="wide")
st.title("🧠 Smart Alpha Dashboard — Debug Mode")

st.markdown("If you see this, Streamlit is running fine ✅")

# ---- Check imports ----
st.subheader("Checking imports...")

try:
    from core import utils, data_sources as ds, scoring as sc
    st.success("✅ Imported core modules successfully")
except Exception as e:
    st.error("❌ Import failed in /core package")
    st.code(traceback.format_exc())
    st.stop()

# ---- Check Binance connectivity ----
try:
    st.write("Fetching Alpha mapping...")
    alpha_map = ds.map_alpha_to_binance()
    st.write(f"Alpha list size: {len(alpha_map)}")
except Exception as e:
    st.error("❌ Failed ds.map_alpha_to_binance()")
    st.code(traceback.format_exc())
    st.stop()

# ---- Check Ticker fetch ----
try:
    st.write("Fetching 24h ticker data...")
    stats = ds.get_ticker_24h_all()
    st.write(f"Stats size: {len(stats)}")
except Exception as e:
    st.error("❌ Failed ds.get_ticker_24h_all()")
    st.code(traceback.format_exc())
    st.stop()

st.success("✅ All data functions imported and executed successfully")

st.markdown("---")
st.info("If you reached here, your backend works. Now you can restore full dashboard.")
