import streamlit as st
import pandas as pd
import psycopg2
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import os
import yfinance as yf
from fyers_apiv3 import fyersModel
import datetime
import pytz

# ==========================================
# 1. PAGE CONFIGURATION & CONNECTION POOL
# ==========================================
st.set_page_config(page_title="The Oracle: Global Intelligence", page_icon="⚖️", layout="wide")

# 🚀 THE GLOBAL CONNECTION POOL (Saves the database from crashing)
conn = st.connection("neon", type="sql", url=st.secrets["DATABASE_URL"])

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. DATA LOADERS (100% Vectorized Pool)
# ==========================================
@st.cache_data(ttl=900)
def load_market_breadth():
    try:
        return conn.query("SELECT * FROM gold_market_breadth")
    except Exception: 
        return pd.DataFrame()

@st.cache_data(ttl=900)
def load_ledger_scoreboard():
    try:
        return conn.query("SELECT COUNT(*) as total_signals, SUM(CASE WHEN verdict = 'WIN' THEN 1 ELSE 0 END) as total_wins, ROUND(AVG(pnl_percentage), 2) as average_return FROM gold_signal_ledger WHERE verdict != 'PENDING';")
    except Exception as e:
        st.error(f"Ledger Scoreboard SQL Error: {e}") 
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_active_portfolio(timeframe):
    try:
        # 🚀 ARCHITECTURAL UPGRADE: Direct 15m Candle Price Extraction
        query = f"""
            WITH aggregated_ledger AS (
                SELECT 
                    ticker, target_timeframe, MIN(signal_date) as first_entry_date,
                    COUNT(signal_id) as total_signals, AVG(entry_price) as avg_entry_price,
                    SUM(COALESCE(allocated_capital, 0)) as total_invested
                FROM gold_signal_ledger
                WHERE verdict = 'PENDING' AND target_timeframe = '{timeframe}'
                GROUP BY ticker, target_timeframe
            ),
            latest_15m_price AS (
                SELECT ticker, close as latest_close
                FROM (
                    SELECT ticker, close, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY datetime DESC) as rn
                    FROM silver_technical_indicators
                ) sub
                WHERE rn = 1
            )
            SELECT 
                g.ticker AS "Ticker",
                CASE 
                    WHEN g.target_timeframe = '1d' THEN 'Macro (1D)'
                    WHEN g.target_timeframe = '15m' THEN 'Intraday (15m)'
                    ELSE g.target_timeframe 
                END AS "Category",
                g.total_signals AS "Signal Count",
                ROUND(g.total_invested::numeric, 2) AS "Invested Amount",
                TO_CHAR(g.first_entry_date, 'Mon DD, YYYY - HH12:MI AM') AS "Entry Time",
                ROUND(g.avg_entry_price::numeric, 2) AS "Avg Entry Price",
                ROUND(s.latest_close::numeric, 2) AS "Current Price",
                ROUND( (((s.latest_close - g.avg_entry_price) / g.avg_entry_price) * 100)::numeric, 2 ) AS "Unrealized_PNL"
            FROM aggregated_ledger g
            JOIN latest_15m_price s ON g.ticker = s.ticker
            ORDER BY ((s.latest_close - g.avg_entry_price) / g.avg_entry_price) DESC;
        """
        df = conn.query(query)
        if not df.empty:
            df = df.rename(columns={"Unrealized_PNL": "Unrealized PNL (%)"})
        return df
    except Exception as e:
        st.error(f"Portfolio Load Error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_daily_executions(timeframe):
    try:
        query = f"""
            WITH today_activity AS (
                SELECT DISTINCT ON (g.ticker)
                    g.ticker AS "Ticker",
                    COALESCE((SELECT signal_type FROM gold_signal_ledger WHERE ticker = g.ticker AND signal_type !~* 'SELL' AND signal_date <= g.signal_date ORDER BY signal_date DESC LIMIT 1), g.signal_type) AS "Action",
                    COALESCE(CASE WHEN g.signal_type !~* 'SELL' THEN ROUND(g.entry_price::numeric, 2) ELSE NULL END, (SELECT ROUND(entry_price::numeric, 2) FROM gold_signal_ledger WHERE ticker = g.ticker AND signal_type !~* 'SELL' AND signal_date <= g.signal_date ORDER BY signal_date DESC LIMIT 1)) AS "Execution Price",
                    COALESCE(CASE WHEN g.signal_type ~* 'SELL' THEN ROUND(g.entry_price::numeric, 2) ELSE NULL END, (SELECT ROUND(entry_price::numeric, 2) FROM gold_signal_ledger WHERE ticker = g.ticker AND signal_type ~* 'SELL' AND signal_date >= g.signal_date ORDER BY signal_date ASC LIMIT 1)) AS "Exit Price",
                    TO_CHAR(COALESCE(CASE WHEN g.signal_type !~* 'SELL' THEN g.signal_date ELSE NULL END, (SELECT signal_date FROM gold_signal_ledger WHERE ticker = g.ticker AND signal_type !~* 'SELL' AND signal_date <= g.signal_date ORDER BY signal_date DESC LIMIT 1), g.signal_date), 'HH12:MI AM') AS "Execution Time",
                    COALESCE(TO_CHAR(CASE WHEN g.signal_type ~* 'SELL' THEN g.signal_date ELSE NULL END, 'HH12:MI AM'), (SELECT TO_CHAR(signal_date, 'HH12:MI AM') FROM gold_signal_ledger WHERE ticker = g.ticker AND signal_type ~* 'SELL' AND signal_date >= g.signal_date ORDER BY signal_date ASC LIMIT 1), 'Active') AS "Exit Time",
                    g.verdict AS "Status", g.pnl_percentage
                FROM gold_signal_ledger g
                WHERE g.target_timeframe = '{timeframe}' 
                  AND DATE(g.signal_date) = DATE(NOW() AT TIME ZONE 'Asia/Kolkata')
                ORDER BY g.ticker, g.signal_date DESC
            )
            SELECT "Ticker", "Action", "Execution Price", "Exit Price", "Execution Time", "Exit Time", "Status", 
            COALESCE(NULLIF(ROUND(pnl_percentage::numeric, 2), 0.00), ROUND((("Exit Price" - "Execution Price") / "Execution Price" * 100)::numeric, 2), 0.00) AS "PNL_Pct"
            FROM today_activity;
        """
        df = conn.query(query)
        if not df.empty:
            df = df.rename(columns={"PNL_Pct": "PNL (%)"})
        return df
    except Exception as e:
        st.error(f"Executions Load Error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_period_performance(timeframe, days):
    try:
        strict_filter = "AND signal_type ~* 'INTRADAY'" if timeframe == '15m' else ""
        query = f"""
            WITH paired_trades AS (
                SELECT 
                    DATE(b.signal_date) as trade_date,
                    COALESCE(
                        NULLIF(b.pnl_percentage, 0),
                        ROUND(((b.settlement_price - b.entry_price) / b.entry_price * 100)::numeric, 2),
                        (SELECT ROUND(((s.entry_price - b.entry_price) / b.entry_price * 100)::numeric, 2) 
                         FROM gold_signal_ledger s 
                         WHERE s.ticker = b.ticker AND s.target_timeframe = b.target_timeframe 
                           AND s.signal_type ~* 'SELL' AND s.signal_date >= b.signal_date 
                         ORDER BY s.signal_date ASC LIMIT 1),
                        0.00
                    ) as true_pnl
                FROM gold_signal_ledger b
                WHERE b.target_timeframe = '{timeframe}' 
                  AND b.signal_date >= NOW() - INTERVAL '{days} days' 
                  AND b.verdict != 'PENDING' AND b.signal_type !~* 'SELL' {strict_filter}
            )
            SELECT trade_date as "Date", COALESCE(ROUND(SUM(true_pnl)::numeric, 2), 0.00) as "Daily_PNL"
            FROM paired_trades GROUP BY trade_date ORDER BY trade_date ASC;
        """
        df = conn.query(query)
        if not df.empty:
            df = df.rename(columns={"Daily_PNL": "Daily PNL (%)"})
        return df
    except Exception as e:
        st.error(f"Performance Graph Error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def fetch_macro_trade_lifecycle(timeframe, days):
    try:
        query = f"""
            SELECT 
                ticker AS "Ticker", TO_CHAR(signal_date, 'Mon DD - HH12:MI AM') AS "Buy Time", 
                ROUND(entry_price::numeric, 2) AS "Buy Price",
                COALESCE(TO_CHAR(settlement_date, 'Mon DD - HH12:MI AM'), CASE WHEN verdict != 'PENDING' THEN 'Closed' ELSE 'Active' END) AS "Sold Time",
                ROUND(settlement_price::numeric, 2) AS "Sold Price",
                COALESCE(ROUND(pnl_percentage::numeric, 2), 0.00) AS "Net Return", verdict AS "Status"
            FROM gold_signal_ledger
            WHERE target_timeframe = '{timeframe}' AND signal_date >= NOW() - INTERVAL '{days} days' AND signal_type !~* 'SELL' 
            ORDER BY signal_date DESC;
        """
        return conn.query(query)
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=900) 
def load_gold_data():
    try:
        df = conn.query("SELECT ticker, latest_close, stochrsi_15m, trend_15m, smart_money_daily FROM gold_screener_latest;")
        time_df = conn.query("SELECT MAX(datetime) as true_market_time FROM silver_technical_indicators;")
        
        if df.empty: return None, None
        
        latest_date = time_df['true_market_time'].iloc[0]
        if pd.notna(latest_date):
            ts = pd.to_datetime(latest_date)
            ts_ist = ts.tz_localize('Asia/Kolkata') if ts.tz is None else ts.tz_convert('Asia/Kolkata')
            return df, ts_ist
        return df, None
    except Exception: return None, None

@st.cache_data(ttl=900)
def load_silver_history(ticker, timeframe):
    try:
        if timeframe == '1d':
            query = f"SELECT DISTINCT ON (b.datetime::date) b.datetime, b.open, b.high, b.low, b.close, s.macd_black, s.macd_red, s.rsi_2, s.stochrsi_k, s.stochrsi_d, s.rsi_14, s.nvi_black, s.nvi_red FROM bronze_raw_ohlcv b LEFT JOIN silver_1d_macro s ON b.ticker = s.ticker AND b.datetime::date = s.datetime::date WHERE b.ticker = '{ticker}' AND b.timeframe = '1d' ORDER BY b.datetime::date DESC, b.datetime DESC LIMIT 300;"
        else:
            query = f"SELECT DISTINCT ON (b.datetime) b.datetime, b.open, b.high, b.low, b.close, s.macd_black, s.macd_red, s.rsi_2, s.stochrsi_k, s.stochrsi_d, s.rsi_14, NULL as nvi_black, NULL as nvi_red FROM bronze_raw_ohlcv b LEFT JOIN silver_technical_indicators s ON b.ticker = s.ticker AND b.datetime::timestamp = s.datetime::timestamp AND s.timeframe = '15m' WHERE b.ticker = '{ticker}' AND b.timeframe = '15m' ORDER BY b.datetime DESC LIMIT 300;"
        
        df = conn.query(query)
        if df.empty: return df
        df['datetime'] = pd.to_datetime(df['datetime'])
        if df['datetime'].dt.tz is not None: df['datetime'] = df['datetime'].dt.tz_localize(None) 
        return df.sort_values(by="datetime", ascending=True)
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=60) 
def load_etf_sniper_radar():
    try:
        query = """
            SELECT DISTINCT ON (ticker) 
                ticker AS "ETF Ticker", TO_CHAR(signal_date, 'Mon DD, YYYY - HH12:MI AM') AS "Time Locked", 
                signal_date, signal_type AS "Signal Type", entry_price AS "Entry Price", 
                target_timeframe AS "Timeframe", verdict AS "Status" 
            FROM gold_signal_ledger 
            WHERE ticker IN ('SILVERBEES.NS', 'GOLDBEES.NS', 'NIFTYBEES.NS', 'BANKBEES.NS', 'ITBEES.NS', 'LIQUIDBEES.NS')
              AND signal_date >= NOW() - INTERVAL '30 days' ORDER BY ticker, signal_date DESC;
        """
        df = conn.query(query)
        if not df.empty:
            df = df.sort_values(by="signal_date", ascending=False).drop(columns=["signal_date"])
        return df
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=60)
def load_live_intraday_signals():
    try:
        query = """
            WITH latest_1d AS (
                SELECT ticker, nvi_black, nvi_red, rsi_14, macd_black, macd_red, rsi_2 
                FROM (SELECT *, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY datetime DESC) as rn 
                      FROM silver_1d_macro WHERE datetime >= CURRENT_DATE - INTERVAL '5 days') sub 
                WHERE rn = 1
            ),
            latest_15m AS (
                SELECT ticker, close, rsi_2, rsi_14, stochrsi_k, stochrsi_d, macd_black, macd_red, vwap 
                FROM (SELECT *, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY datetime DESC) as rn 
                      FROM silver_technical_indicators WHERE datetime >= CURRENT_DATE - INTERVAL '2 days') sub 
                WHERE rn = 1
            ),
            scored_stocks AS (
                SELECT 
                    m.ticker, m.close, 
                    (CASE WHEN d.nvi_black > d.nvi_red THEN 10 ELSE 0 END + 
                     CASE WHEN m.macd_black > m.macd_red THEN 20 ELSE 0 END + 
                     CASE WHEN m.rsi_14 > 45 THEN 20 ELSE 0 END + 
                     CASE WHEN m.rsi_2 < 5 AND m.stochrsi_k < 10 THEN 20 ELSE 0 END + 
                     CASE WHEN m.close > m.vwap THEN 30 ELSE 0 END) AS buy_intraday_score 
                FROM latest_15m m JOIN latest_1d d ON m.ticker = d.ticker
            )
            SELECT s.ticker AS "Stock", ROUND(s.close::numeric, 2) AS "Current Price", s.buy_intraday_score AS "Raw Intraday Score", 
            CASE 
                WHEN l.ticker IS NOT NULL THEN '🟢 BOUGHT (Active)' 
                WHEN s.buy_intraday_score >= 80 THEN '⚡ LOCK (Pending Macro Check)' 
                WHEN s.buy_intraday_score >= 70 THEN '🔥 HEATING UP' 
                ELSE '⏳ WAITING' 
            END AS "Signal Status"
            FROM scored_stocks s LEFT JOIN gold_signal_ledger l ON s.ticker = l.ticker AND l.verdict = 'PENDING' AND l.target_timeframe = '15m' 
            WHERE s.buy_intraday_score >= 50 ORDER BY s.buy_intraday_score DESC LIMIT 15;
        """
        return conn.query(query)
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=300)
def load_global_macro_pulse():
    tickers = {"NIFTY 50": "^NSEI", "S&P 500": "^GSPC", "USD / INR": "INR=X", "Crude Oil": "CL=F", "Bitcoin": "BTC-USD"}
    results = {}
    try:
        for name, symbol in tickers.items():
            t = yf.Ticker(symbol)
            hist = t.history(period="5d")
            if len(hist) >= 2:
                pct_change = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
                results[name] = {"value": hist['Close'].iloc[-1], "delta": pct_change}
            elif len(hist) == 1:
                 results[name] = {"value": hist['Close'].iloc[-1], "delta": 0.0}
        return results
    except Exception: return {}


# ==========================================
# 3. TOP LEVEL: BREADTH RADAR
# ==========================================
st.markdown("### 📡 Institutional Market Breadth")
breadth_df = load_market_breadth()
try:
    if not breadth_df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric(label="🐂 Elite Bullish %", value=f"{breadth_df['elite_bullish_percentage'].iloc[0]}%", delta="Strict Confluence")
        col2.metric(label="🐻 Terminal Bearish %", value=f"{breadth_df['terminal_bearish_percentage'].iloc[0]}%", delta="-Avoid", delta_color="inverse")
        col3.metric(label="🎯 Active Targets", value=f"{breadth_df['elite_bulls'].iloc[0]} Stocks", delta="Ready for Screener")
        st.divider() 
except Exception as e:
    st.warning(f"Market Breadth Radar offline: {e}")

# ==========================================
# 4. SIDEBAR
# ==========================================
data_result = load_gold_data()
st.sidebar.divider()
st.sidebar.subheader("🔀 Data Source Router")
try:
    # ⚠️ For the Sidebar DML (Updates), we must use a direct psycopg2 cursor, not the Streamlit read-only pool
    pg_conn = psycopg2.connect(host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb", user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"])
    cursor = pg_conn.cursor()
    cursor.execute("SELECT key_value FROM system_config WHERE key_name = 'ACTIVE_DATA_SOURCE';")
    res = cursor.fetchone()
    current_source = res[0] if res else "YAHOO"

    cursor.execute("SELECT last_updated FROM system_config WHERE key_name = 'FYERS_ACCESS_TOKEN';")
    token_res = cursor.fetchone()
    ist = pytz.timezone('Asia/Kolkata')
    today_ist = datetime.datetime.now(ist).date()
    is_token_fresh = token_res and token_res[0] and (token_res[0].replace(tzinfo=pytz.utc) if token_res[0].tzinfo is None else token_res[0]).astimezone(ist).date() == today_ist

    if current_source == "FYERS" and not is_token_fresh:
        current_source = "YAHOO"
        cursor.execute("UPDATE system_config SET key_value = 'YAHOO', last_updated = NOW() WHERE key_name = 'ACTIVE_DATA_SOURCE';")
        pg_conn.commit()
        st.sidebar.warning("⚠️ Fyers Token expired. UI Auto-Reverted to YAHOO.")

    new_source = st.sidebar.radio("Active Pipeline Source:", ["YAHOO (Default / Free)", "FYERS (Requires Daily Token)"], index=0 if current_source == "YAHOO" else 1)
    if ("YAHOO" if "YAHOO" in new_source else "FYERS") != current_source:
        cursor.execute("INSERT INTO system_config (key_name, key_value, last_updated) VALUES ('ACTIVE_DATA_SOURCE', %s, NOW()) ON CONFLICT (key_name) DO UPDATE SET key_value = EXCLUDED.key_value, last_updated = NOW();", ("YAHOO" if "YAHOO" in new_source else "FYERS",))
        pg_conn.commit()
    pg_conn.close()
except Exception: pass

st.sidebar.divider()
st.sidebar.subheader("🔑 Fyers API Forge")
with st.sidebar.expander("Authenticate Broker"):
    fyers_client_id = st.text_input("App ID (client_id)").strip()
    fyers_secret = st.text_input("Secret Key", type="password").strip()
    if fyers_client_id and fyers_secret:
        session = fyersModel.SessionModel(client_id=fyers_client_id, secret_key=fyers_secret, redirect_uri="https://127.0.0.1", response_type="code", grant_type="authorization_code")
        st.markdown(f"**1. [🔗 CLICK HERE TO LOGIN]({session.generate_authcode()})**")
        auth_code = st.text_input("2. Paste Auth Code Here:").strip()
        if st.button("3. Forge Master Token"):
            session.set_token(auth_code)
            response = session.generate_token()
            if "access_token" in response:
                try:
                    forge_conn = psycopg2.connect(host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb", user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"])
                    forge_conn.cursor().execute("INSERT INTO system_config (key_name, key_value, last_updated) VALUES ('FYERS_ACCESS_TOKEN', %s, NOW()) ON CONFLICT (key_name) DO UPDATE SET key_value = EXCLUDED.key_value, last_updated = NOW();", (response["access_token"],))
                    forge_conn.cursor().execute("INSERT INTO system_config (key_name, key_value, last_updated) VALUES ('ACTIVE_DATA_SOURCE', 'FYERS', NOW()) ON CONFLICT (key_name) DO UPDATE SET key_value = EXCLUDED.key_value, last_updated = NOW();")
                    forge_conn.commit(); forge_conn.close(); st.success("✅ Handshake Successful!"); st.rerun()
                except Exception as e: st.error(f"DB Error: {e}")

st.sidebar.divider()
df = data_result[0] if data_result[0] is not None else pd.DataFrame()
filename = data_result[1]

st.sidebar.title("🌍 Global Sentinel")
if st.sidebar.button("🔄 Clear Oracle Cache"): st.cache_data.clear(); st.rerun()

nifty_proxy = df[df['ticker'] == 'RELIANCE.NS'].iloc[0] if not df.empty and 'RELIANCE.NS' in df['ticker'].values else None
if nifty_proxy is not None: st.sidebar.metric("Nifty Health Proxy", "✅ STABLE" if nifty_proxy['smart_money_daily'] == 'ACCUMULATION' else "⚠️ WEAK")

st.sidebar.divider()
st.sidebar.subheader("🌐 Global Macro Radar")
macro_data = load_global_macro_pulse()
if macro_data:
    for asset, data in macro_data.items():
        st.sidebar.metric(label=asset, value=f"{data['value']:,.2f}", delta=f"{data['delta']:.2f}%", delta_color="inverse" if asset in ["USD / INR", "Crude Oil"] else "normal")

# ==========================================
# 5. MAIN UI (Tabs)
# ==========================================
st.title("⚖️ The Market Oracle")
# --- 🚀 FLOATING TIME HUD ---
if data_result[1] is not None:
    ts_ist = data_result[1]
    last_refresh_str = ts_ist.strftime('%d %b %Y, %I:%M %p')
    
    minutes = ts_ist.minute
    next_min = ((minutes // 15) + 1) * 15
    
    if next_min >= 60:
        valid_till_ts = ts_ist.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
    else:
        valid_till_ts = ts_ist.replace(minute=next_min, second=0, microsecond=0)
        
    if valid_till_ts.hour > 15 or (valid_till_ts.hour == 15 and valid_till_ts.minute >= 30):
        valid_till_str = "Next Trading Day 09:15 AM"
    else:
        valid_till_str = valid_till_ts.strftime('%d %b %Y, %I:%M %p')
else:
    last_refresh_str = "Awaiting Data"
    valid_till_str = "Awaiting Data"

st.markdown(f"""
    <div style="position: absolute; top: -45px; right: 0px; text-align: right; font-size: 13px; color: #a0a0a0; background-color: #161b22; padding: 8px 15px; border-radius: 8px; border: 1px solid #30363d; z-index: 100; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
        <span style="color:#E0E0E0;">🔄 <b>Last Refresh:</b></span> {last_refresh_str}<br>
        <span style="color:#26A69A;">⏳ <b>Valid Till:</b></span> {valid_till_str}
    </div>
""", unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 The Screener", "📈 The X-Ray Sandbox", "⚡ Intraday Ledger", "🏛️ Macro Ledger", "🎯 ETF Sniper Radar"])

# ------------------------------------------
# TAB 1: THE SCREENER
# ------------------------------------------
with tab1:
    st.subheader("🏆 The Oracle's True Win Rate")
    try:
        ledger_df = load_ledger_scoreboard()
        if ledger_df is not None and not ledger_df.empty and ledger_df['total_signals'].iloc[0] > 0:
            st.metric(label=f"System Accuracy ({ledger_df['total_signals'].iloc[0]} Settled Trades)", value=f"{(ledger_df['total_wins'].iloc[0] / ledger_df['total_signals'].iloc[0]) * 100:.1f}%", delta=f"Avg Return: {ledger_df['average_return'].iloc[0]}%")
        else: st.info("📊 Forward-Testing Engine Active. Awaiting first settlements...")
    except Exception as e: 
        st.warning(f"Ledger Database Offline. Error: {e}")
    
    st.divider()
    if df.empty:
        st.warning("⚠️ Screener vault (`gold_screener_latest`) is empty or initializing. Check your DB ingestion pipelines.")
    else:
        signal_type = st.radio("⚔️ **SIGNAL SELECTION:**", ["BUY (The Rebound)", "SELL (The Collapse)"], horizontal=True)
        is_buy = "BUY" in signal_type
        st.subheader("🔥 THE ELITE BULLS" if is_buy else "💀 THE FALLEN")
        top_10 = df[df['trend_15m'] == ('BULLISH' if is_buy else 'BEARISH')].sort_values(by='stochrsi_15m', ascending=is_buy).head(10)
        if not top_10.empty:
            cols = st.columns(5)
            for idx, (i, row) in enumerate(top_10.iterrows()):
                cols[idx % 5].metric(label=row['ticker'], value=f"₹{row['latest_close']}", delta="REBOUND" if is_buy else "COLLAPSE", delta_color="normal" if is_buy else "inverse")
            st.dataframe(top_10[['ticker', 'latest_close', 'stochrsi_15m', 'smart_money_daily', 'trend_15m']], use_container_width=True)
        else: st.error("### 🚫 NO TRADE ZONE")
        st.divider()
        search_query = st.text_input("🔍 Search Stock Symbol", "").upper()
        st.dataframe(df[df['ticker'].str.contains(search_query, na=False)] if search_query else df[['ticker', 'latest_close', 'stochrsi_15m', 'smart_money_daily', 'trend_15m']], use_container_width=True, height=400)

# ------------------------------------------
# TAB 2: THE X-RAY Sandbox
# ------------------------------------------
with tab2:
    st.subheader("🔬 Institutional Indicator X-Ray")
    ctrl_col1, ctrl_col2 = st.columns([2, 1])
    with ctrl_col1: target_ticker = st.selectbox("Select Asset to Analyze:", df['ticker'].sort_values().unique() if not df.empty else [])
    with ctrl_col2: target_timeframe = {"15m (Intraday)": "15m", "1h (Swing)": "1h", "1d (Macro)": "1d"}[st.radio("Lens (Timeframe):", ["15m (Intraday)", "1h (Swing)", "1d (Macro)"], horizontal=True)]
    
    if target_ticker:
        chart_df = load_silver_history(target_ticker, target_timeframe)
        if not chart_df.empty:
            chart_df['rsi_2_over'] = chart_df['rsi_2'].clip(lower=75)
            chart_df['rsi_2_under'] = chart_df['rsi_2'].clip(upper=20)
            chart_df['display_time'] = chart_df['datetime'].dt.strftime('%b %d, %Y' if target_timeframe == '1d' else '%b %d, %H:%M')

            fig = make_subplots(rows=6, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.25, 0.15, 0.15, 0.15, 0.15, 0.15], subplot_titles=(f"{target_ticker} - Close Price", "MACD", "RSI (2)", "Stochastic RSI", "RSI (14)", "NVI"))
            fig.add_trace(go.Candlestick(x=chart_df['display_time'], open=chart_df['open'], high=chart_df['high'], low=chart_df['low'], close=chart_df['close'], name='Price', increasing_line_color='#26A69A', decreasing_line_color='#EF5350'), row=1, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['macd_black'], name='MACD Line', line=dict(color='white', width=1.5)), row=2, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['macd_red'], name='Signal Line', line=dict(color='red', width=1.5)), row=2, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['rsi_2'], name='RSI(2)', line=dict(color='#FFA500', width=1.5)), row=3, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['stochrsi_k'], name='%K Line (Blue)', line=dict(color='#0055FF', width=1.5)), row=4, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['stochrsi_d'], name='%D Line (Orange)', line=dict(color='#FF9900', width=1.2, dash='dot')), row=4, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['rsi_14'], name='RSI(14)', line=dict(color='#E0E0E0', width=1.5)), row=5, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['nvi_black'], name='NVI Raw', line=dict(color='white', width=1.5)), row=6, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['nvi_red'], name='NVI EMA(255)', line=dict(color='#FF3333', width=1.5)), row=6, col=1)

            fig.update_layout(height=1200, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, margin=dict(l=0, r=90, t=30, b=0), dragmode='pan', xaxis_rangeslider_visible=False)
            fig.update_xaxes(type='category', nticks=12, tickangle=-45, categoryorder='array', categoryarray=chart_df['display_time'])
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom':False, 'displayModeBar': False})
        else: st.warning("Historical data is still warming up for this asset.")

# ------------------------------------------
# TAB 3: INTRADAY LEDGER (15m)
# ------------------------------------------
with tab3:
    st.subheader("⚡ Intraday Sniper Operations")
    
    df_intra_today = load_daily_executions('15m')
    
    if not df_intra_today.empty:
        df_intra_today = df_intra_today[df_intra_today['Action'].str.contains('INTRADAY|HARVEST|SQUAREOFF', case=False, na=False)]
        df_intra_today = df_intra_today.dropna(subset=['Execution Price'])

    intra_pnl_today = 0.00
    profit_taken_1qty = 0.00
    
    if not df_intra_today.empty:
        settled_df = df_intra_today.dropna(subset=['Exit Price']).copy()
        
        if not settled_df.empty:
            settled_df['True PNL'] = ((settled_df['Exit Price'].astype(float) - settled_df['Execution Price'].astype(float)) / settled_df['Execution Price'].astype(float)) * 100
            intra_pnl_today = settled_df['True PNL'].sum()
            profit_taken_1qty = (settled_df['Exit Price'].astype(float) - settled_df['Execution Price'].astype(float)).sum()

    df_intra_portfolio = load_active_portfolio('15m')
    intra_avg_pnl = df_intra_portfolio["Unrealized PNL (%)"].mean() if not df_intra_portfolio.empty else 0.00

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Today's Executions", len(df_intra_today))
    c2.metric("Today's Settled PNL", f"{intra_pnl_today:.2f}%", delta=f"{intra_pnl_today:.2f}%")
    c3.metric("Open Intraday Positions", len(df_intra_portfolio))
    c4.metric("Avg Unrealized PNL", f"{intra_avg_pnl:.2f}%", delta="Profitable" if intra_avg_pnl > 0 else "Drawdown", delta_color="normal" if intra_avg_pnl > 0 else "inverse")
    c5.metric("💸 Profit Taken (1 Qty)", f"₹{profit_taken_1qty:.2f}", help="Total pure points captured today, assuming exactly 1 share bought/sold per trade.")
    st.divider()
    
    st.markdown("### 📡 Live Signal Radar")
    df_live_signals = load_live_intraday_signals()
    if not df_live_signals.empty:
        st.dataframe(df_live_signals.style.map(lambda val: 'background-color: rgba(9, 171, 59, 0.2); color: #09ab3b; font-weight: bold;' if 'BOUGHT' in str(val).upper() else 'background-color: rgba(255, 75, 75, 0.2); color: #ff4b4b; font-weight: bold;' if 'TRIGGERED' in str(val).upper() else 'color: #FFA500; font-weight: bold;' if 'HEATING' in str(val).upper() else 'color: gray;', subset=['Signal Status']), use_container_width=True, hide_index=True)
    else: st.info("Radar is quiet.")
    st.divider()

    st.markdown("### 🟢 Active Open Intraday")
    if not df_intra_portfolio.empty: 
        st.dataframe(
            df_intra_portfolio.style.map(lambda val: f"color: {'#26A69A' if val > 0 else '#EF5350' if val < 0 else 'gray'}; font-weight: bold;", subset=["Unrealized PNL (%)"]), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Invested Amount": st.column_config.NumberColumn("Invested Amount", format="₹%.2f"),
                "Avg Entry Price": st.column_config.NumberColumn("Avg Entry Price", format="₹%.2f"),
                "Current Price": st.column_config.NumberColumn("Current Price", format="₹%.2f")
            }
        )
    else: st.info("No active open intraday positions.")
    st.divider()

    st.markdown("### 📋 Today's Order Book")
    if not df_intra_today.empty: 
        st.dataframe(df_intra_today[["Ticker", "Action", "Execution Price", "Exit Price", "Execution Time", "Exit Time", "Status", "PNL (%)"]], use_container_width=True, hide_index=True)
    else: 
        st.info("No intraday actions executed yet today.")
    st.divider()

    st.markdown("### 📈 Weekly Performance Curve")
    df_intra_weekly = load_period_performance('15m', 7)
    if not df_intra_weekly.empty:
        df_intra_weekly["Cumulative Growth (%)"] = df_intra_weekly["Daily PNL (%)"].cumsum()
        st.plotly_chart(px.line(df_intra_weekly, x="Date", y="Cumulative Growth (%)", title="Intraday Cumulative Variance", markers=True), use_container_width=True)
    else: st.warning("Insufficient baseline data.")

# ------------------------------------------
# TAB 4: MACRO Ledger (1D)
# ------------------------------------------
with tab4:
    st.subheader("🏛️ Macro Portfolio Command Center")
    
    try:
        # For simple SELECT queries, we use the pool
        seed_df = conn.query("SELECT key_value FROM system_config WHERE key_name = 'STARTING_MACRO_CAPITAL'")
        seed_capital = float(seed_df.iloc[0]['key_value']) if not seed_df.empty else 100000.0
        
        realized_df = conn.query("SELECT SUM(COALESCE(net_realized_pnl, 0)) as pnl FROM gold_signal_ledger WHERE target_timeframe = '1d' AND verdict = 'CLOSED'")
        realized_pnl = float(realized_df.iloc[0]['pnl'] or 0.0)
        
        invested_df = conn.query("SELECT SUM(COALESCE(allocated_capital, 0)) as inv FROM gold_signal_ledger WHERE target_timeframe = '1d' AND verdict = 'PENDING'")
        invested_capital = float(invested_df.iloc[0]['inv'] or 0.0)
        
        unrealized_df = conn.query("""
            SELECT SUM((s.latest_close - g.entry_price) * g.quantity) as upnl
            FROM gold_signal_ledger g
            JOIN gold_screener_latest s ON g.ticker = s.ticker
            WHERE g.target_timeframe = '1d' AND g.verdict = 'PENDING'
        """)
        unrealized_pnl = float(unrealized_df.iloc[0]['upnl'] or 0.0)
        
        current_equity = seed_capital + realized_pnl + unrealized_pnl
        available_cash = (seed_capital + realized_pnl) - invested_capital
        total_growth_pct = ((current_equity - seed_capital) / seed_capital) * 100
        
        st.markdown("<style>.big-font {font-size:30px !important; font-weight: bold; color: #E0E0E0;}</style>", unsafe_allow_html=True)
        
        dash_c1, dash_c2, dash_c3, dash_c4, dash_c5 = st.columns(5)
        dash_c1.metric(label="💰 Total Macro Equity", value=f"₹{current_equity:,.2f}", delta=f"{total_growth_pct:.2f}% Net Return")
        dash_c2.metric(label="💵 Available Cash", value=f"₹{available_cash:,.2f}")
        dash_c3.metric(label="🔒 Invested Capital", value=f"₹{invested_capital:,.2f}")
        dash_c4.metric(label="📈 Live Unrealized PNL", value=f"₹{unrealized_pnl:,.2f}", delta="Fluctuating", delta_color="off")
        dash_c5.metric(label="💸 Net Realized Profit", value=f"₹{realized_pnl:,.2f}", help="Total harvested profit with 0.25% brokerage, taxes, and slippage already deducted.")
        st.divider()

        with st.expander("🏦 Manage Portfolio Capital"):
            col_a, col_b = st.columns([3, 1])
            with col_a:
                new_capital = st.number_input("Update Total Seed Capital (₹)", min_value=10000, value=int(seed_capital), step=10000)
            with col_b:
                st.write("") 
                st.write("") 
                if st.button("Inject Capital"):
                    try:
                        # DML MUST use psycopg2 directly
                        conn_update = psycopg2.connect(host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb", user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"])
                        cursor_update = conn_update.cursor()
                        cursor_update.execute("UPDATE system_config SET key_value = %s, last_updated = NOW() WHERE key_name = 'STARTING_MACRO_CAPITAL'", (str(new_capital),))
                        conn_update.commit()
                        conn_update.close()
                        st.success(f"✅ Capital successfully updated to ₹{new_capital:,.2f}")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to inject capital: {e}")

    except Exception as e:
        st.warning(f"Failed to load Portfolio Metrics: {e}")
        
    df_macro_portfolio = load_active_portfolio('1d')
    if not df_macro_portfolio.empty:
        st.dataframe(
            df_macro_portfolio.style.map(lambda val: f"color: {'#26A69A' if val > 0 else '#EF5350' if val < 0 else 'gray'}; font-weight: bold;", subset=["Unrealized PNL (%)"]), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Invested Amount": st.column_config.NumberColumn("Invested Amount", format="₹%.2f"),
                "Avg Entry Price": st.column_config.NumberColumn("Avg Entry Price", format="₹%.2f"),
                "Current Price": st.column_config.NumberColumn("Current Price", format="₹%.2f")
            }
        )
    else: st.info("No active open macro positions.")
    st.divider()
    
    st.subheader("📅 Historical Macro Performance")
    days_lookback = 7 if "7" in st.radio("Select Lookback Period:", ["Last 7 Days", "Last 30 Days"], horizontal=True) else 30
    df_macro_history = fetch_macro_trade_lifecycle('1d', days_lookback)
    
    if not df_macro_history.empty: st.dataframe(df_macro_history, use_container_width=True, hide_index=True)
    else: st.info(f"No systemic macro shifts or settled trades detected.")
    st.divider()
    
    df_macro_curve = load_period_performance('1d', days_lookback)
    if not df_macro_curve.empty:
        df_macro_curve["Structural Growth (%)"] = df_macro_curve["Daily PNL (%)"].cumsum()
        st.plotly_chart(px.area(df_macro_curve, x="Date", y="Structural Growth (%)", title="Macro Framework Long-Term Equity Curve"), use_container_width=True)
    else:
        st.info("📈 Equity Curve Standby: No settled 1D macro trades closed within this lookback window.")

# ------------------------------------------
# TAB 5: ETF SNIPER RADAR
# ------------------------------------------
with tab5:
    st.subheader("🎯 Institutional ETF Sniper Radar")
    etf_df = load_etf_sniper_radar()
    if not etf_df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total ETF Locks", len(etf_df))
        c2.metric("Intraday Snipes", len(etf_df[etf_df['Signal Type'].str.contains('INTRADAY', na=False)]))
        c3.metric("Macro Bull Locks", len(etf_df[etf_df['Signal Type'].str.contains('LONG_TERM', na=False)]))
        st.divider()
        st.dataframe(etf_df.style.map(lambda val: 'background-color: rgba(255, 215, 0, 0.2); color: #ffd700; font-weight: bold;' if 'SELL_HARVEST' in str(val).upper() else 'background-color: rgba(255, 100, 100, 0.2); color: #ff0000; font-weight: bold;' if 'SELL_EVAC' in str(val).upper() else 'background-color: rgba(255, 75, 75, 0.2); color: #ff4b4b; font-weight: bold;' if 'INTRADAY' in str(val).upper() else 'background-color: rgba(9, 171, 59, 0.2); color: #09ab3b; font-weight: bold;' if 'LONG_TERM' in str(val).upper() else '', subset=['Signal Type']), use_container_width=True, hide_index=True)
        if st.button("🔄 Force Radar Sweep"): st.cache_data.clear(); st.rerun()
    else: st.info("🛡️ ETF Radar Clear.")
