import streamlit as st
import pandas as pd
import glob
import os
from datetime import datetime

# 1. Page Configuration
st.set_page_config(page_title="The Oracle: Indian Market Decoder", page_icon="⚖️", layout="wide")

# Custom Styling
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# 2. The Persona
st.title("⚖️ The Market Oracle: Brutal Honesty Edition")
st.markdown("""
> **The Council:** *A Grandmaster of Trading, an Elite Systems Mathematician, and a Master Chart Reader.* > We decode the mathematically verified reality of the Indian Market. No sugarcoating.
""")

# 3. Data Loading
@st.cache_data
def load_data():
    list_of_files = glob.glob('Nifty500_Scan_*.csv')
    if not list_of_files: return None
    latest_file = max(list_of_files, key=os.path.getctime)
    return pd.read_csv(latest_file), latest_file

data_result = load_data()

if data_result is None:
    st.error("The Council is silent. No data found in the vault (CSV missing).")
else:
    df, filename = data_result

    # --- MARKET PULSE FILTER (Nifty 50 Context) ---
    # We find Nifty 50 or a major proxy like RELIANCE to gauge market health
    nifty_proxy = df[df['Ticker'] == 'RELIANCE.NS'].iloc[0] if 'RELIANCE.NS' in df['Ticker'].values else None
    
    st.sidebar.header("🌍 Global Market Pulse")
    if nifty_proxy is not None:
        # If Reliance (market leader) is below its NVI Red line, the whole market is risky
        market_bullish = nifty_proxy['1D_NVI_Black'] > nifty_proxy['1D_NVI_Red']
        status = "✅ STABLE" if market_bullish else "⚠️ WEAK"
        st.sidebar.metric("Nifty Health Proxy", status)
    else:
        market_bullish = True # Fallback

    # --- NAVIGATION ---
    st.divider()
    signal_type = st.radio("⚔️ **SELECT YOUR FATE (SIGNAL):**", ["BUY (The Bullish Rebound)", "SELL (The Bearish Collapse)"], horizontal=True)

    # --- MATH ENGINE (Fixing the 1D naming issue using string keys) ---
    bullish_mask = (
        (df['1D_Stoch_K_Black'] < 25) & 
        (df['15m_MACD_Black'] > df['15m_MACD_Red']) &
        (df['1D_NVI_Black'] > df['1D_NVI_Red'])
    )
    
    bearish_mask = (
        (df['1D_Stoch_K_Black'] > 75) & 
        (df['15m_MACD_Black'] < df['15m_MACD_Red']) &
        (df['1D_NVI_Black'] < df['1D_NVI_Red'])
    )

    if "BUY" in signal_type:
        st.subheader("🔥 THE ELITE BULLS: Top 10 Buy Signals")
        if not market_bullish:
            st.warning("🚨 **The Mathematician Warns:** Overall market pulse is WEAK. Even bullish setups have a higher probability of failure today.")
        
        top_10 = df[bullish_mask].sort_values(by='1D_Stoch_K_Black', ascending=True).head(10)
        color = "green"
        verdict = "REBOUND"
    else:
        st.subheader("💀 THE FALLEN: Top 10 Sell Signals")
        top_10 = df[bearish_mask].sort_values(by='1D_Stoch_K_Black', ascending=False).head(10)
        color = "red"
        verdict = "COLLAPSE"

    # --- DISPLAY (Using dict access to avoid SyntaxError) ---
    if not top_10.empty:
        cols = st.columns(5)
        for idx, (i, row) in enumerate(top_10.iterrows()):
            with cols[idx % 5]:
                # We use row['column_name'] to avoid the leading-number error
                st.metric(
                    label=row['Ticker'], 
                    value=f"₹{row['1D_Price']}", 
                    delta=verdict, 
                    delta_color="normal" if color=="green" else "inverse"
                )
        
        st.divider()
        st.write("### 📊 Raw Oracle Data")
        st.dataframe(top_10[['Ticker', '1D_Price', '1D_Stoch_K_Black', '1D_NVI_Black', '15m_MACD_Black']], use_container_width=True)
    else:
        st.info("The Mathematician finds no 100% factual setups matching this criteria right now.")

    # --- THE CHART READER'S INSIGHT ---
    with st.expander("📝 The Chart Reader's Final Warning"):
        if "BUY" in signal_type:
            st.write("Smart money is absorbing the selling pressure. The Stochastic RSI shows extreme exhaustion for sellers. This is where precision meets opportunity.")
        else:
            st.write("The distribution phase is over. Indicators show that institutional support has vanished. Retail is currently holding the bag.")

    st.caption(f"Last Vault Update: {filename}")
