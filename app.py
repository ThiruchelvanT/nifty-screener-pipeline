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
@st.cache_data(ttl=900)
def load_silver_history(ticker, timeframe):
    """Pulls time-series data directly from the Silver Layer for charting"""
    try:
        conn = psycopg2.connect(
            host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb",    
            user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"]
        )
        
        # --- THE TIMESTAMP DRIFT FIX ---
        # If looking at macro 1D, deduplicate by the pure calendar date (ignoring hours/mins).
        # Otherwise, deduplicate by the exact precise datetime.
        if timeframe == '1d':
            distinct_col = "datetime::date"
        else:
            distinct_col = "datetime"

        # The ORDER BY must perfectly match the DISTINCT ON clause for Postgres to execute it.
        query = f"""
        SELECT DISTINCT ON ({distinct_col}) 
               datetime, open, high, low, close, macd_black, macd_red, 
               rsi_2, stochrsi_k, rsi_14, 
               nvi_black, nvi_red
        FROM silver_technical_indicators
        WHERE ticker = '{ticker}' AND LOWER(timeframe) = '{timeframe}'
        ORDER BY {distinct_col} DESC, datetime DESC
        LIMIT 150;
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            return df
            
        # Sort chronologically (oldest to newest) so Plotly draws the lines perfectly forward
        return df.sort_values(by="datetime", ascending=True)
        
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
# ------------------------------------------
# TAB 2: THE X-RAY SANDBOX (Silver Layer)
# ------------------------------------------
with tab2:
    st.subheader("🔬 Institutional Indicator X-Ray")
    st.markdown("Dive into the raw mathematical momentum and accumulation of a specific asset across multiple timeframes.")
    
    # ⚠️ Create columns for a clean top-bar layout
    ctrl_col1, ctrl_col2 = st.columns([2, 1])
    
    with ctrl_col1:
        target_ticker = st.selectbox("Select Asset to Analyze:", df['ticker'].sort_values().unique())
        
    with ctrl_col2:
        # The Timeframe Switcher
        selected_tf_label = st.radio(
            "Lens (Timeframe):", 
            ["15m (Intraday)", "1h (Swing)", "1d (Macro)"], 
            horizontal=True
        )
    
    # Map the UI label to the exact string our database expects
    tf_map = {
        "15m (Intraday)": "15m",
        "1h (Swing)": "1h",
        "1d (Macro)": "1d"
    }
    target_timeframe = tf_map[selected_tf_label]
    
    if target_ticker:
        # Pass BOTH parameters to our updated data loader
        chart_df = load_silver_history(target_ticker, target_timeframe)
        
        if not chart_df.empty:
            # --- ON-THE-FLY MATH ---
            # 1. MACD Histogram
            chart_df['macd_hist'] = chart_df['macd_black'] - chart_df['macd_red']
            hist_colors = ['#26A69A' if val >= 0 else '#EF5350' for val in chart_df['macd_hist']]
            
            # 2. RSI(2) Shading Math
            chart_df['rsi_2_over'] = chart_df['rsi_2'].clip(lower=75)
            chart_df['rsi_2_under'] = chart_df['rsi_2'].clip(upper=20)

            # Create a 6-row Plotly chart
            fig = make_subplots(
                rows=6, cols=1, shared_xaxes=True, 
                vertical_spacing=0.03, # Tighter spacing to fit everything
                row_heights=[0.25, 0.15, 0.15, 0.15, 0.15, 0.15],
                subplot_titles=(
                    f"{target_ticker} - Close Price", 
                    "MACD (12, 26, 9)", 
                    "RSI (2) - Extreme Mean Reversion", 
                    "Stochastic RSI", 
                    "RSI (14) - Structural Trend", 
                    "NVI - Institutional Flow"
                )
            )

            # ==========================================
            # ROW 1: PRICE
            # ==========================================
            # ==========================================
            # ROW 1: PRICE (Japanese Candlesticks)
            # ==========================================
            fig.add_trace(go.Candlestick(
                x=chart_df['datetime'],
                open=chart_df['open'],
                high=chart_df['high'],
                low=chart_df['low'],
                close=chart_df['close'],
                name='Price',
                increasing_line_color='#26A69A', # TradingView Green
                decreasing_line_color='#EF5350'  # TradingView Red
            ), row=1, col=1)
            
            # Plotly automatically adds a range slider with candlesticks which breaks our subplots. 
            # We must explicitly turn it off. Add this INSIDE your fig.update_layout() block at the bottom:
            # xaxis_rangeslider_visible=False,
            # ==========================================
            # ROW 2: MACD
            # ==========================================
            fig.add_trace(go.Bar(x=chart_df['datetime'], y=chart_df['macd_hist'], name='Histogram', marker_color=hist_colors), row=2, col=1)
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['macd_black'], name='MACD Line', line=dict(color='white')), row=2, col=1)
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['macd_red'], name='Signal Line', line=dict(color='red')), row=2, col=1)
            
            # ==========================================
            # ROW 3: RSI (2)
            # ==========================================
            # Invisible boundaries and shading
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=[75]*len(chart_df), mode='lines', line=dict(color='rgba(255,255,255,0)', width=0), hoverinfo='skip'), row=3, col=1)
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['rsi_2_over'], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(255,255,255,0.3)', hoverinfo='skip'), row=3, col=1)
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=[20]*len(chart_df), mode='lines', line=dict(color='rgba(255,255,255,0)', width=0), hoverinfo='skip'), row=3, col=1)
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['rsi_2_under'], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(255,255,255,0.3)', hoverinfo='skip'), row=3, col=1)
            # The RSI 2 Line
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['rsi_2'], name='RSI(2)', line=dict(color='#FFA500', width=1.5)), row=3, col=1)

            # ==========================================
            # ROW 4: STOCHASTIC RSI
            # ==========================================
            fig.add_hrect(y0=20, y1=80, fillcolor="rgba(255, 100, 100, 0.1)", layer="below", line_width=0, row=4, col=1)
            fig.add_hline(y=80, line_width=1, line_color="gray", row=4, col=1)
            fig.add_hline(y=20, line_width=1, line_color="gray", row=4, col=1)
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['stochrsi_k'], name='StochRSI', line=dict(color='#0055FF', width=1.5)), row=4, col=1)

            # ==========================================
            # ROW 5: RSI (14)
            # ==========================================
            fig.add_hline(y=70, line_dash="dot", line_color="red", row=5, col=1)
            fig.add_hline(y=30, line_dash="dot", line_color="green", row=5, col=1)
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['rsi_14'], name='RSI(14)', line=dict(color='#E0E0E0', width=1.5)), row=5, col=1)

            # ==========================================
            # ROW 6: NVI
            # ==========================================
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['nvi_black'], name='NVI Raw', line=dict(color='white', width=1.5)), row=6, col=1)
            fig.add_trace(go.Scatter(x=chart_df['datetime'], y=chart_df['nvi_red'], name='NVI EMA(255)', line=dict(color='#FF3333', width=1.5)), row=6, col=1)

            # --- TRADINGVIEW STYLE VALUE BUBBLES ---
            last_date = chart_df['datetime'].iloc[-1]
            
            # StochRSI Bubble (Row 4)
            last_stoch = chart_df['stochrsi_k'].iloc[-1]
            if pd.notna(last_stoch):
                fig.add_annotation(
                    x=last_date, y=last_stoch, text=f"<b>{last_stoch:.2f}</b>",
                    showarrow=False, xanchor='left', xshift=10,
                    bgcolor="#0055FF", font=dict(color="white", size=11),
                    borderpad=3, bordercolor="white", borderwidth=1, row=4, col=1
                )

            # NVI Bubbles (Row 6)
            last_nvi_black = chart_df['nvi_black'].iloc[-1]
            last_nvi_red = chart_df['nvi_red'].iloc[-1]
            if pd.notna(last_nvi_black):
                fig.add_annotation(
                    x=last_date, y=last_nvi_black, text=f"<b>{last_nvi_black:.2f}</b>",
                    showarrow=False, xanchor='left', xshift=10,
                    bgcolor="white", font=dict(color="black", size=11),
                    borderpad=3, bordercolor="black", borderwidth=1, row=6, col=1
                )
            if pd.notna(last_nvi_red):
                fig.add_annotation(
                    x=last_date, y=last_nvi_red, text=f"<b>{last_nvi_red:.2f}</b>",
                    showarrow=False, xanchor='left', xshift=10,
                    bgcolor="#FF3333", font=dict(color="white", size=11),
                    borderpad=3, bordercolor="white", borderwidth=1, row=6, col=1
                )

            # --- STRICT LAYOUT LOCKS ---
            fig.update_layout(
                height=1200, # ⚠️ Increased height to comfortably fit 6 rows
                template="plotly_dark",
                paper_bgcolor='rgba(0,0,0,0)', 
                plot_bgcolor='rgba(0,0,0,0)',
                showlegend=False,
                margin=dict(l=0, r=60, t=30, b=0),
                dragmode='pan',
                xaxis=dict(
                    rangeselector=dict(
                        buttons=list([
                            dict(count=7, label="1W", step="day", stepmode="backward"),
                            dict(count=1, label="1M", step="month", stepmode="backward"),
                            dict(count=1, label="1Y", step="year", stepmode="backward"),
                            dict(count=2, label="2Y", step="year", stepmode="backward"),
                            dict(step="all", label="All")
                        ]),
                        bgcolor="#161b22", activecolor="#30363d", font=dict(color="white")
                    ),
                    type="date"
                )
            )
            fig.update_yaxes(fixedrange=True)
            # --- THE TIME-FOLDING FIX (RANGEBREAKS) ---
            # Dynamically hide non-trading hours so the lines don't stretch unnaturally across time gaps
            if target_timeframe == '1d':
                # For Macro Daily charts, we only need to hide the weekends
                fig.update_xaxes(
                    rangebreaks=[
                        dict(bounds=["sat", "mon"]) # Hides Saturday to Monday morning
                    ]
                )
            else:
                # For Intraday charts (15m, 1h), we hide weekends AND the overnight gaps
                # The NSE closes at 15:30 (15.5) and opens at 09:15 (9.25)
                fig.update_xaxes(
                    rangebreaks=[
                        dict(bounds=["sat", "mon"]),
                        dict(bounds=[15.5, 9.25], pattern="hour") 
                    ]
                )

            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': False, 'displayModeBar': False})
        else:
            st.warning("Historical data is still warming up for this asset.")
            
