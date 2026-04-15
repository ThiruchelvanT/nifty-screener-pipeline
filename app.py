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

    # --- MARKET PULSE FILTER ---
    nifty_proxy = df[df['Ticker'] == 'RELIANCE.NS'].iloc[0] if 'RELIANCE.NS' in df['Ticker'].values else None
    
    st.sidebar.header("🌍 Global Market Pulse")
    if nifty_proxy is not None:
        market_bullish = nifty_proxy['1D_NVI_Black'] > nifty_proxy['1D_NVI_Red']
        status = "✅ STABLE" if market_bullish else "⚠️ WEAK"
        st.sidebar.metric("Nifty Health Proxy", status)
    else:
        market_bullish = True

    # --- NAVIGATION ---
    st.divider()
    signal_type = st.radio("⚔️ **SELECT YOUR FATE (SIGNAL):**", ["BUY (The Bullish Rebound)", "SELL (The Bearish Collapse)"], horizontal=True)

    # --- MATH ENGINE ---
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
            st.warning("🚨 **The Mathematician Warns:** Overall market pulse is WEAK.")
        
        top_10 = df[bullish_mask].sort_values(by='1D_Stoch_K_Black', ascending=True).head(10)
        color, verdict = "green", "REBOUND"
    else:
        st.subheader("💀 THE FALLEN: Top 10 Sell Signals")
        top_10 = df[bearish_mask].sort_values(by='1D_Stoch_K_Black', ascending=False).head(10)
        color, verdict = "red", "COLLAPSE"

    # --- SIGNAL DISPLAY ---
    if not top_10.empty:
        cols = st.columns(5)
        for idx, (i, row) in enumerate(top_10.iterrows()):
            with cols[idx % 5]:
                st.metric(label=row['Ticker'], value=f"₹{row['1D_Price']}", delta=verdict, delta_color="normal" if color=="green" else "inverse")
        
        st.divider()
        st.write("### 📊 Oracle Specifics")
        st.dataframe(top_10[['Ticker', '1D_Price', '1D_Stoch_K_Black', '1D_NVI_Black', '15m_MACD_Black']], use_container_width=True)
    else:
        st.info("The Mathematician finds no 100% factual setups matching this criteria right now.")

    # --- CHART READER'S INSIGHT ---
    with st.expander("📝 The Chart Reader's Final Warning"):
        if "BUY" in signal_type:
            st.write("Smart money is absorbing pressure. Precision meets opportunity.")
        else:
            st.write("Distribution is over. Institutional support has vanished.")

    # --- NEW SECTION: THE FULL DATA VAULT ---
    st.divider()
    st.header("📁 The Full Data Vault")
    st.markdown("Access all mathematical data points for the Nifty 500 universe.")

    # Search and Filter Logic for the Full Table
    search_query = st.text_input("🔍 Search for a Stock (e.g., TATA, HDFC, SBIN)", "").upper()
    
    # Filter dataframe based on search
    vault_df = df[df['Ticker'].str.contains(search_query)] if search_query else df

    # Display the Full Table with professional formatting
    st.dataframe(
        vault_df, 
        use_container_width=True, 
        height=500,
        column_config={
            "1D_Price": st.column_config.NumberColumn("Current Price", format="₹%.2f"),
            "1D_Stoch_K_Black": st.column_config.ProgressColumn("Stoch RSI (1D)", min_value=0, max_value=100),
            "Ticker": "Symbol",
            "1D_NVI_Black": "NVI Actual",
            "1D_NVI_Red": "NVI Signal"
        }
    )

    st.caption(f"Last Vault Update: {filename} | Engine Active")
