import streamlit as st
import pandas as pd
import yfinance as yf
import psycopg2
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
# 2. DATA LOADERS
# ==========================================
@st.cache_data(ttl=300) 
def get_global_indices():
    indices = {
        "^DJI": "Dow Jones (US)", "^IXIC": "Nasdaq (US)", "^GSPC": "S&P 500 (US)",
        "^N225": "Nikkei 225 (JP)", "BTC-USD": "Bitcoin"
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

@st.cache_data(ttl=900) 
def load_gold_data():
    try:
        conn = psycopg2.connect(
            host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb",    
            user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"]
        )
        query = """
        SELECT ticker, latest_close, stochrsi_15m, trend_15m, smart_money_daily, last_updated
        FROM gold_screener_latest;
        """
        df = pd.read_sql_query(query, conn)
        conn.close() 
        if df.empty: return None, None
        
        latest_date = df['last_updated'].max()
        if not isinstance(latest_date, str): latest_date = latest_date.strftime('%Y-%m-%d %H:%M')
        return df, f"Cloud Vault - {latest_date}"
    except Exception as e:
        st.error(f"Failed to breach the Gold Vault: {e}")
        return None, None

@st.cache_data(ttl=900)
def load_silver_history(ticker):
    """Pulls time-series data directly from the Silver Layer for charting"""
    try:
        conn = psycopg2.connect(
            host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb",    
            user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"]
        )
        # Pull the last 150 daily candles for the requested ticker
        query = f"""
        SELECT datetime, close, macd_black, macd_red, rsi_14, nvi_black, nvi_red
        FROM silver_technical_indicators
        WHERE ticker = '{ticker}' AND timeframe = '1d'
        ORDER BY datetime DESC
        LIMIT 150;
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        # Reverse the dataframe so oldest dates are first (for proper charting)
        return df.sort_values(by="datetime")
    except Exception as e:
        st.error(f"Failed to breach the Silver Vault: {e}")
        return pd.DataFrame()

# ==========================================
# 3. SIDEBAR (Global Pulse)
# ==========================================
data_result = load_gold_data()
global_data = get_global_indices()

if data_result[0] is None:
    st.stop() 

df, filename = data_result

st.sidebar.title("🌍 Global Sentinel")
if st.sidebar.button("🔄 Clear Oracle Cache"):
    st.cache_data.clear()
    st.rerun()

nifty_proxy = df[df['ticker'] == 'RELIANCE.NS'].iloc[0] if 'RELIANCE.NS' in df['ticker'].values else None
if nifty_proxy is not None:
    market_bullish = (nifty_proxy['smart_money_daily'] == 'ACCUMULATION')
    st.sidebar.metric("Nifty Health Proxy", "✅ STABLE" if market_bullish else "⚠️ WEAK")

st.sidebar.divider()
st.sidebar.subheader("International Markets")
for index in global_data:
    st.sidebar.metric(label=index['Name'], value=f"{index['Price']:,.2f}", delta=f"{index['Change']:.2f}%")

# ==========================================
# 4. MAIN UI (Tabs)
# ==========================================
st.title("⚖️ The Market Oracle")

# Create the Navigation Tabs
tab1, tab2 = st.tabs(["📊 The Screener", "📈 The X-Ray Sandbox"])

# ------------------------------------------
# TAB 1: THE SCREENER (Gold Layer)
# ------------------------------------------
with tab1:
    st.subheader("🌊 Market Breadth (Overall Sentiment)")
    total = len(df)
    if total > 0:
        macd_bulls = (len(df[df['trend_15m'] == 'BULLISH']) / total) * 100
        nvi_accum = (len(df[df['smart_money_daily'] == 'ACCUMULATION']) / total) * 100
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Short-Term Momentum (15m MACD)**: {macd_bulls:.1f}% Bullish")
            st.progress(macd_bulls / 100)
        with col2:
            st.markdown(f"**Institutional Flow (Daily NVI)**: {nvi_accum:.1f}% Accumulation")
            st.progress(nvi_accum / 100)
            
    st.divider()
    signal_type = st.radio("⚔️ **SIGNAL SELECTION:**", ["BUY (The Rebound)", "SELL (The Collapse)"], horizontal=True)

    bullish_mask = ((df['stochrsi_15m'] < 40) & (df['trend_15m'] == 'BULLISH') & (df['smart_money_daily'] == 'ACCUMULATION'))
    bearish_mask = ((df['stochrsi_15m'] > 75) & (df['trend_15m'] == 'BEARISH') & (df['smart_money_daily'] == 'DISTRIBUTION'))

    if "BUY" in signal_type:
        st.subheader("🔥 THE ELITE BULLS")
        top_10 = df[bullish_mask].sort_values(by='stochrsi_15m', ascending=True).head(10)
        color, verdict = "green", "REBOUND"
    else:
        st.subheader("💀 THE FALLEN")
        top_10 = df[bearish_mask].sort_values(by='stochrsi_15m', ascending=False).head(10)
        color, verdict = "red", "COLLAPSE"

    if not top_10.empty:
        cols = st.columns(5)
        for idx, (i, row) in enumerate(top_10.iterrows()):
            with cols[idx % 5]:
                st.metric(label=row['ticker'], value=f"₹{row['latest_close']}", delta=verdict, delta_color="normal" if color=="green" else "inverse")
        st.dataframe(top_10[['ticker', 'latest_close', 'stochrsi_15m', 'smart_money_daily', 'trend_15m']], use_container_width=True)
    else:
        st.error("### 🚫 THE COUNCIL REMAINS SILENT: NO TRADE ZONE")

    # --- THE FULL DATA VAULT ---
    st.divider()
    st.subheader("📁 The Full Data Vault")
    st.markdown("Manually search the master ledger for specific stock alignments.")
    
    # Search Bar
    search_query = st.text_input("🔍 Search Stock Symbol (e.g., RELIANCE, HDFC)", "").upper()
    
    # Filter the dataframe based on search
    vault_df = df[df['ticker'].str.contains(search_query, na=False)] if search_query else df
    
    # Display the full, scrollable dataframe
    st.dataframe(
        vault_df[['ticker', 'latest_close', 'stochrsi_15m', 'smart_money_daily', 'trend_15m']], 
        use_container_width=True, 
        height=400
    )

    st.divider()
    st.caption(f"Last Vault Update: {filename}")

# ------------------------------------------
# TAB 2: THE X-RAY SANDBOX (Silver Layer)
# ------------------------------------------
with tab2:
    st.subheader("🔬 Institutional Indicator X-Ray")
    st.markdown("Dive into the raw mathematical momentum and accumulation of a specific asset.")
    
    # Dropdown to select a ticker from the available Gold data
    target_ticker = st.selectbox("Select Asset to Analyze:", df['ticker'].sort_values().unique())
    
    if target_ticker:
        chart_df = load_silver_history(target_ticker)
        
        if not chart_df.empty:
            # Create a 4-row Plotly chart (Price, MACD, RSI, NVI)
            fig = make_subplots(
                rows=4, cols=1, shared_xaxes=True, 
                vertical_spacing=0.05,
                row_heights=[0.4, 0.2, 0.2, 0.2],
                subplot_titles=(f"{target_ticker} - Close Price", "MACD (12, 26, 9)", "RSI (14)", "NVI (Institutional Flow)")
            )

            # Row 1: Price
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['close'], name='Close Price', line=dict(color='white')), row=1, col=1)
            
            # Row 2: MACD
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['macd_black'], name='MACD Line', line=dict(color='#00F5FF')), row=2, col=1)
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['macd_red'], name='Signal Line', line=dict(color='#FF3030')), row=2, col=1)
            
            # Row 3: RSI
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['rsi_14'], name='RSI(14)', line=dict(color='#FFA500')), row=3, col=1)
            # Add overbought/oversold boundaries
            fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
            fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

            # Row 4: NVI
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['nvi_black'], name='NVI Raw', line=dict(color='gray')), row=4, col=1)
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['nvi_red'], name='NVI EMA(255)', line=dict(color='red')), row=4, col=1)

            # Layout tuning for dark mode dashboard
            # Layout tuning for dark mode dashboard
            fig.update_layout(
                height=800, 
                template="plotly_dark",
                paper_bgcolor='rgba(0,0,0,0)', 
                plot_bgcolor='rgba(0,0,0,0)',
                showlegend=False,
                margin=dict(l=0, r=0, t=30, b=0),
                dragmode='pan', # Sets the default mouse interaction to dragging/panning (left/right)
                
                # Configure the X-Axis with your requested time filters
                xaxis=dict(
                    rangeselector=dict(
                        buttons=list([
                            dict(count=7, label="Daily (1W)", step="day", stepmode="backward"),
                            dict(count=1, label="Weekly (1M)", step="month", stepmode="backward"),
                            dict(count=1, label="Monthly (1Y)", step="year", stepmode="backward"),
                            dict(count=2, label="Yearly (2Y)", step="year", stepmode="backward"),
                            dict(step="all", label="All Data")
                        ]),
                        bgcolor="#161b22",       # Matches your Streamlit metric background
                        activecolor="#30363d",   # Highlights the clicked button
                        font=dict(color="white") # Ensures text is readable
                    ),
                    type="date"
                )
            )

            # Render the chart with scrollZoom explicitly disabled
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': False, 'displayModeBar': False})
            
        else:
            st.warning("Historical data is still warming up for this asset.")
