import streamlit as st
import pandas as pd
import yfinance as yf
import glob
import os
from datetime import datetime

# 1. Page Configuration
st.set_page_config(page_title="The Oracle: Global Intelligence", page_icon="⚖️", layout="wide")

# Custom Styling
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# 2. Global Index Fetcher (Live API Data)
@st.cache_data(ttl=300) # Refresh global data every 5 minutes
def get_global_indices():
    indices = {
        "^DJI": "Dow Jones (US)",
        "^IXIC": "Nasdaq (US)",
        "^GSPC": "S&P 500 (US)",
        "^FTSE": "FTSE 100 (UK)",
        "^N225": "Nikkei 225 (JP)",
        "BTC-USD": "Bitcoin"
    }
    data = []
    for ticker, name in indices.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="2d")
            if len(hist) >= 2:
                current_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                change = ((current_price - prev_price) / prev_price) * 100
                data.append({"Name": name, "Price": current_price, "Change": change})
        except:
            continue
    return data

# 3. Local Data Loading (Nifty 500 Vault)
@st.cache_data
def load_data():
    list_of_files = glob.glob('Nifty500_Scan_*.csv')
    if not list_of_files: return None
    latest_file = max(list_of_files, key=os.path.getctime)
    return pd.read_csv(latest_file), latest_file

# Execute Loads
data_result = load_data()
global_data = get_global_indices()

if data_result is None:
    st.error("The Council is silent. CSV missing.")
else:
    df, filename = data_result

    # --- SIDEBAR: GLOBAL PULSE & SENTINEL ---
    st.sidebar.title("🌍 Global Sentinel")
    
    # 1. Nifty Internal Health (Your existing code)
    nifty_proxy = df[df['Ticker'] == 'RELIANCE.NS'].iloc[0] if 'RELIANCE.NS' in df['Ticker'].values else None
    if nifty_proxy is not None:
        market_bullish = nifty_proxy['1D_NVI_Black'] > nifty_proxy['1D_NVI_Red']
        st.sidebar.metric("Nifty Health Proxy", "✅ STABLE" if market_bullish else "⚠️ WEAK")
    else:
        market_bullish = True

    st.sidebar.divider()
    
    # 2. Live Global Indices Display
    st.sidebar.subheader("International Markets")
    for index in global_data:
        st.sidebar.metric(
            label=index['Name'], 
            value=f"{index['Price']:,.2f}", 
            delta=f"{index['Change']:.2f}%"
        )

    # --- MAIN UI ---
    st.title("⚖️ The Market Oracle")
    
    signal_type = st.radio("⚔️ **SIGNAL SELECTION:**", ["BUY (The Rebound)", "SELL (The Collapse)"], horizontal=True)

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
        st.subheader("🔥 THE ELITE BULLS")
        top_10 = df[bullish_mask].sort_values(by='1D_Stoch_K_Black', ascending=True).head(10)
        color, verdict = "green", "REBOUND"
    else:
        st.subheader("💀 THE FALLEN")
        top_10 = df[bearish_mask].sort_values(by='1D_Stoch_K_Black', ascending=False).head(10)
        color, verdict = "red", "COLLAPSE"

    # --- SIGNAL DISPLAY ---
    if not top_10.empty:
        cols = st.columns(5)
        for idx, (i, row) in enumerate(top_10.iterrows()):
            with cols[idx % 5]:
                st.metric(label=row['Ticker'], value=f"₹{row['1D_Price']}", delta=verdict, delta_color="normal" if color=="green" else "inverse")
        st.divider()
        st.dataframe(top_10[['Ticker', '1D_Price', '1D_Stoch_K_Black', '1D_NVI_Black', '15m_MACD_Black']], use_container_width=True)
    else:
        st.info("The Mathematician finds no factual setups right now.")

    with st.expander("📝 The Chart Reader's Final Warning"):
        if "BUY" in signal_type:
            st.write("Smart money is absorbing pressure. Precision meets opportunity.")
        else:
            st.write("Distribution is over. Institutional support has vanished.")

    # --- THE FULL DATA VAULT ---
    st.divider()
    st.header("📁 The Full Data Vault")
    search_query = st.text_input("🔍 Search Stock Symbol (e.g., TATA, HDFC)", "").upper()
    vault_df = df[df['Ticker'].str.contains(search_query)] if search_query else df
    st.dataframe(vault_df, use_container_width=True, height=400)

    st.caption(f"Last Vault Update: {filename}")
