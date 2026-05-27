import streamlit as st
import pandas as pd
import yfinance as yf
import psycopg2

# ==========================================
# 1. PAGE CONFIGURATION & STYLING
# ==========================================
st.set_page_config(page_title="The Oracle: Global Intelligence", page_icon="⚖️", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. GLOBAL SENTINEL (Market Health)
# ==========================================
@st.cache_data(ttl=300) 
def get_global_indices():
    indices = {
        "^DJI": "Dow Jones (US)", "^IXIC": "Nasdaq (US)", "^GSPC": "S&P 500 (US)",
        "^FTSE": "FTSE 100 (UK)", "^N225": "Nikkei 225 (JP)", "BTC-USD": "Bitcoin"
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

# ==========================================
# 3. SECURE VAULT CONNECTION (The Gold Layer)
# ==========================================
@st.cache_data(ttl=900) # Caches for 15 minutes to match our GitHub CRON
def load_data():
    try:
        conn = psycopg2.connect(
            host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb",    
            user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"]
        )
        
        # Querying the NEW Materialized View
        query = """
        SELECT 
            ticker,
            latest_close,
            stochrsi_15m,
            trend_15m,
            smart_money_daily,
            last_updated
        FROM gold_screener_latest;
        """
        df = pd.read_sql_query(query, conn)
        conn.close() 
        
        if df.empty: return None, None
        
        latest_date = df['last_updated'].max()
        if not isinstance(latest_date, str): 
            latest_date = latest_date.strftime('%Y-%m-%d %H:%M')
            
        return df, f"Cloud Vault - {latest_date}"
    except Exception as e:
        st.error(f"Failed to breach the Cloud Vault: {e}")
        return None, None

# ==========================================
# 4. EXECUTE LOADS & VALIDATE
# ==========================================
data_result = load_data()
global_data = get_global_indices()

if data_result[0] is None:
    st.error("🚨 **CRITICAL ALERT:** The Oracle has lost connection to the Neon Cloud Vault.")
    st.info("Check Streamlit Secrets or the raw error message above for details.")
    st.stop() 
else:
    df, filename = data_result

    # --- SIDEBAR: GLOBAL PULSE & SENTINEL ---
    st.sidebar.title("🌍 Global Sentinel")

    if st.sidebar.button("🔄 Clear Oracle Cache"):
        st.cache_data.clear()
        st.rerun()
    
    # Check Nifty proxy health using the new smart_money_daily column
    nifty_proxy = df[df['ticker'] == 'RELIANCE.NS'].iloc[0] if 'RELIANCE.NS' in df['ticker'].values else None
    if nifty_proxy is not None:
        market_bullish = (nifty_proxy['smart_money_daily'] == 'ACCUMULATION')
        st.sidebar.metric("Nifty Health Proxy", "✅ STABLE" if market_bullish else "⚠️ WEAK")
    else:
        market_bullish = True

    st.sidebar.divider()
    
    st.sidebar.subheader("International Markets")
    for index in global_data:
        st.sidebar.metric(label=index['Name'], value=f"{index['Price']:,.2f}", delta=f"{index['Change']:.2f}%")

    # ==========================================
    # 5. MAIN UI & QUANTITATIVE ENGINE
    # ==========================================
    st.title("⚖️ The Market Oracle")

    # Calculate Percentages
    total = len(df)
    if total > 0:
        macd_bulls = (len(df[df['trend_15m'] == 'BULLISH']) / total) * 100
        macd_bears = (len(df[df['trend_15m'] == 'BEARISH']) / total) * 100
        nvi_accum = (len(df[df['smart_money_daily'] == 'ACCUMULATION']) / total) * 100
        nvi_dist = (len(df[df['smart_money_daily'] == 'DISTRIBUTION']) / total) * 100
        
        # Display Progress Bars
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"**Short-Term Momentum (15m MACD)**: {macd_bulls:.1f}% Bullish")
            st.progress(macd_bulls / 100)
            
        with col2:
            st.markdown(f"**Institutional Flow (Daily NVI)**: {nvi_accum:.1f}% Accumulation")
            st.progress(nvi_accum / 100)
            
    st.divider()
    
    signal_type = st.radio("⚔️ **SIGNAL SELECTION:**", ["BUY (The Rebound)", "SELL (The Collapse)"], horizontal=True)

    # --- MATH ENGINE (Updated to match Gold Layer logic) ---
    bullish_mask = (
        (df['stochrsi_15m'] < 40) & 
        (df['trend_15m'] == 'BULLISH') &
        (df['smart_money_daily'] == 'ACCUMULATION')
    )
    
    bearish_mask = (
        (df['stochrsi_15m'] > 75) & 
        (df['trend_15m'] == 'BEARISH') &
        (df['smart_money_daily'] == 'DISTRIBUTION')
    )

    if "BUY" in signal_type:
        st.subheader("🔥 THE ELITE BULLS")
        top_10 = df[bullish_mask].sort_values(by='stochrsi_15m', ascending=True).head(10)
        color, verdict = "green", "REBOUND"
    else:
        st.subheader("💀 THE FALLEN")
        top_10 = df[bearish_mask].sort_values(by='stochrsi_15m', ascending=False).head(10)
        color, verdict = "red", "COLLAPSE"

    # --- SIGNAL DISPLAY ---
    if not top_10.empty:
        cols = st.columns(5)
        for idx, (i, row) in enumerate(top_10.iterrows()):
            with cols[idx % 5]:
                st.metric(label=row['ticker'], value=f"₹{row['latest_close']}", delta=verdict, delta_color="normal" if color=="green" else "inverse")
        st.divider()
        
        # Display the formatted dataframe
        st.dataframe(
            top_10[['ticker', 'latest_close', 'stochrsi_15m', 'smart_money_daily', 'trend_15m']], 
            use_container_width=True
        )
    else:
        st.error("### 🚫 THE COUNCIL REMAINS SILENT: NO TRADE ZONE")
        st.markdown("""
        **The Elite Assessment:**
        * 📐 **The Mathematician:** "Current price action lacks the volatility cluster required for a high-probability entry."
        * 📉 **The Chart Reader:** "Institutional accumulation is paused. We are currently in a 'no-man's land' of retail indecision."
        * ♟️ **The Grandmaster:** "Patience is a currency. We do not chase price. Remain defensive until the NVI proxy shifts decisively."
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
    vault_df = df[df['ticker'].str.contains(search_query)] if search_query else df
    st.dataframe(vault_df, use_container_width=True, height=400)

    st.caption(f"Last Vault Update: {filename}")
