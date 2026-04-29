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

# ... (Keep your global imports and page config)

# --- 3. CLOUD DATA LOADING (Supabase Vault) ---
@st.cache_data(ttl=3600) # Cache for 1 hour to save database compute
def load_data():
    try:
        # 1. Connect to the Cloud Database using Streamlit's native SQL connection
        conn = st.connection("supabase", type="sql")
        
        # 2. The 30 LPA Analytics Query
        # We dynamically select the LATEST available date in the database to handle weekends/holidays
        query = """
        SELECT 
            ticker AS "Ticker",
            price AS "1D_Price",
            stoch_k AS "1D_Stoch_K_Black",
            macd_black AS "15m_MACD_Black",
            macd_red AS "15m_MACD_Red",
            nvi_black AS "1D_NVI_Black",
            nvi_red AS "1D_NVI_Red",
            trade_date AS "Date"
        FROM nifty_daily_signals
        WHERE trade_date = (SELECT MAX(trade_date) FROM nifty_daily_signals);
        """
        
        # 3. Execute and load directly into a Pandas DataFrame
        df = conn.query(query)
        
        if df.empty:
            return None, None
            
        latest_date = df['Date'].iloc[0].strftime('%Y-%m-%d')
        filename_display = f"Cloud Vault - {latest_date}"
        
        return df, filename_display
        
    except Exception as e:
        st.error(f"Failed to breach the Cloud Vault: {e}")
        return None, None

# Execute Loads
data_result = load_data()
global_data = get_global_indices()


if data_result[0] is None:
    st.error("🚨 **CRITICAL ALERT:** The Oracle has lost connection to the Cloud Vault.")
    st.info("Please verify the Supabase Connection URI in your Streamlit Secrets.")
    st.stop() # <-- This commands Streamlit to halt execution immediately. No ugly red errors!

else:
    df, filename = data_result

    # --- SIDEBAR: GLOBAL PULSE & SENTINEL ---
    st.sidebar.title("🌍 Global Sentinel")

    if st.sidebar.button("🔄 Clear Oracle Cache"):
        st.cache_data.clear()
        st.rerun()
    
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
        (df['1D_Stoch_K_Black'] < 40) & 
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
        # --- THE COUNCIL'S VERDICT (REPLACED BLOCK) ---
        st.error("### 🚫 THE COUNCIL REMAINS SILENT: NO TRADE ZONE")
        st.markdown("""
        **The Elite Assessment:**
        * 📐 **The Mathematician:** "Current price action lacks the volatility cluster required for a high-probability entry. Stochastic metrics are severely distorted by the recent squeeze."
        * 📉 **The Chart Reader:** "Institutional accumulation is paused. We are currently in a 'no-man's land' of retail indecision. Forcing a setup here is gambling."
        * ♟️ **The Grandmaster:** "Patience is a currency. We do not chase price. Cash is an active position. Remain defensive until the NVI proxy shifts decisively."
        """)

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
