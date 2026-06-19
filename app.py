import streamlit as st
import pandas as pd
import psycopg2
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from sqlalchemy import create_engine
import os
import yfinance as yf
from fyers_apiv3 import fyersModel
import datetime
import pytz

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
@st.cache_data(ttl=900)
def load_market_breadth():
    try:
        temp_engine = create_engine(st.secrets["DATABASE_URL"])
        df = pd.read_sql("SELECT * FROM gold_market_breadth", temp_engine)
        temp_engine.dispose()
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=900)
def load_ledger_scoreboard():
    try:
        temp_engine = create_engine(st.secrets["DATABASE_URL"])
        query = """
            SELECT 
                COUNT(*) as total_signals,
                SUM(CASE WHEN verdict = 'WIN' THEN 1 ELSE 0 END) as total_wins,
                ROUND(AVG(pnl_percentage), 2) as average_return
            FROM gold_signal_ledger
            WHERE verdict != 'PENDING';
        """
        df = pd.read_sql(query, temp_engine)
        temp_engine.dispose()
        return df
    except Exception as e:
        return pd.DataFrame()

# 🛡️ THE FIX: Removed the double-shift from the Entry Time TO_CHAR formatting
@st.cache_data(ttl=60)
def load_active_portfolio(timeframe):
    try:
        conn = psycopg2.connect(
            host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb",    
            user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"]
        )
        
        query = f"""
            WITH latest_macro AS (
                SELECT ticker, close 
                FROM (
                    SELECT ticker, close, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY datetime DESC) as rn 
                    FROM silver_1d_macro
                ) sub WHERE rn = 1
            ),
            aggregated_ledger AS (
                SELECT 
                    ticker,
                    target_timeframe,
                    MIN(signal_date) as first_entry_date,
                    COUNT(signal_id) as total_signals,
                    AVG(entry_price) as avg_entry_price
                FROM gold_signal_ledger
                WHERE verdict = 'PENDING' AND target_timeframe = '{timeframe}'
                GROUP BY ticker, target_timeframe
            )
            SELECT 
                g.ticker AS "Ticker",
                CASE 
                    WHEN g.target_timeframe = '1d' THEN 'Macro (1D)'
                    WHEN g.target_timeframe = '15m' THEN 'Intraday (15m)'
                    ELSE g.target_timeframe 
                END AS "Category",
                g.total_signals AS "Signal Count",
                TO_CHAR(g.first_entry_date, 'Mon DD, YYYY - HH12:MI AM') AS "Entry Time",
                ROUND(g.avg_entry_price::numeric, 2) AS "Avg Entry Price",
                ROUND(s.close::numeric, 2) AS "Current Price",
                ROUND( (((s.close - g.avg_entry_price) / g.avg_entry_price) * 100)::numeric, 2 ) AS "Unrealized PNL (%)"
            FROM aggregated_ledger g
            JOIN latest_macro s ON g.ticker = s.ticker
            ORDER BY ((s.close - g.avg_entry_price) / g.avg_entry_price) DESC;
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

# 🛡️ THE FIX: Removed the double-shift from TO_CHAR and signal_date checking
@st.cache_data(ttl=60)
def load_daily_executions(timeframe):
    try:
        temp_engine = create_engine(st.secrets["DATABASE_URL"])
        query = f"""
            SELECT DISTINCT ON (ticker)
                ticker AS "Ticker",
                signal_type AS "Action",
                entry_price AS "Execution Price",
                TO_CHAR(signal_date, 'HH12:MI AM') AS "Execution Time",
                verdict AS "Status"
            FROM gold_signal_ledger
            WHERE target_timeframe = '{timeframe}'
              AND signal_date::date = (NOW() AT TIME ZONE 'Asia/Kolkata')::date
            ORDER BY ticker, signal_date DESC;
        """
        df = pd.read_sql(query, temp_engine)
        temp_engine.dispose()
        
        if not df.empty:
            df = df.sort_values(by="Execution Time", ascending=False)
            
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_daily_pnl(timeframe):
    try:
        temp_engine = create_engine(st.secrets["DATABASE_URL"])
        query = f"""
            WITH latest_prices AS (
                SELECT ticker, close 
                FROM (
                    SELECT ticker, close, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY datetime DESC) as rn 
                    FROM silver_1d_macro
                ) sub WHERE rn = 1
            )
            SELECT 
                COALESCE(ROUND(AVG(((s.close - g.entry_price) / g.entry_price) * 100)::numeric, 2), 0.00) as pnl_ratio
            FROM gold_signal_ledger g
            JOIN latest_prices s ON g.ticker = s.ticker
            WHERE g.target_timeframe = '{timeframe}' 
              AND g.signal_date::date = (NOW() AT TIME ZONE 'Asia/Kolkata')::date
              AND g.verdict = 'PENDING';
        """
        df = pd.read_sql(query, temp_engine)
        temp_engine.dispose()
        if not df.empty and pd.notna(df.iloc[0]['pnl_ratio']):
            return float(df.iloc[0]['pnl_ratio'])
        return 0.0
    except Exception:
        return 0.0

@st.cache_data(ttl=300)
def load_period_performance(timeframe, days):
    try:
        conn = psycopg2.connect(
            host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb",    
            user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"]
        )
        query = f"""
            SELECT 
                signal_date::date as "Date",
                SUM(COALESCE(pnl_percentage, 0)) as "Daily PNL (%)"
            FROM gold_signal_ledger
            WHERE target_timeframe = '{timeframe}'
              AND signal_date >= NOW() - INTERVAL '{days} days'
              AND verdict != 'PENDING'
            GROUP BY "Date"
            ORDER BY "Date" ASC;
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.sidebar.error(f"Curve DB Error: {e}")
        return pd.DataFrame()

# 🛡️ THE FIX: Removed timezone shifts from the Macro Lifecycle rendering
@st.cache_data(ttl=60)
def fetch_macro_trade_lifecycle(timeframe, days):
    try:
        conn = psycopg2.connect(
            host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb",    
            user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"]
        )
        query = f"""
            SELECT 
                b.ticker AS "Ticker",
                TO_CHAR(b.signal_date, 'Mon DD - HH12:MI AM') AS "Buy Time",
                ROUND(b.entry_price::numeric, 2) AS "Buy Price",
                COALESCE(
                    TO_CHAR(s.signal_date, 'Mon DD - HH12:MI AM'), 
                    CASE WHEN b.verdict != 'PENDING' THEN 'Closed' ELSE 'Active' END
                ) AS "Sold Time",
                COALESCE(
                    ROUND(s.entry_price::numeric, 2), 
                    CASE WHEN b.verdict != 'PENDING' THEN ROUND((b.entry_price * (1 + (b.pnl_percentage / 100)))::numeric, 2) ELSE NULL END
                ) AS "Sold Price",
                COALESCE(ROUND(b.pnl_percentage::numeric, 2), 0.00) AS "Net Return",
                b.verdict AS "Status"
            FROM gold_signal_ledger b
            LEFT JOIN LATERAL (
                SELECT signal_date, entry_price 
                FROM gold_signal_ledger 
                WHERE ticker = b.ticker 
                  AND target_timeframe = b.target_timeframe 
                  AND signal_type ~* 'SELL' 
                  AND signal_date > b.signal_date 
                ORDER BY signal_date ASC 
                LIMIT 1
            ) s ON true
            WHERE b.target_timeframe = '{timeframe}'
              AND b.signal_date >= NOW() - INTERVAL '{days} days'
              AND b.signal_type !~* 'SELL' 
            ORDER BY b.signal_date DESC;
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.sidebar.error(f"Ledger DB Error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_historical_pnl(timeframe, days):
    try:
        conn = psycopg2.connect(
            host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb",    
            user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"]
        )
        query = f"""
            SELECT 
                COALESCE(ROUND(SUM(pnl_percentage)::numeric, 2), 0.00) as total_pnl
            FROM gold_signal_ledger
            WHERE target_timeframe = '{timeframe}' 
              AND signal_date >= NOW() - INTERVAL '{days} days'
              AND verdict != 'PENDING';
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        if not df.empty and pd.notna(df.iloc[0]['total_pnl']):
            return float(df.iloc[0]['total_pnl'])
        return 0.0
    except Exception as e:
        st.sidebar.error(f"PNL DB Error: {e}")
        return 0.0

@st.cache_data(ttl=900) 
def load_gold_data():
    try:
        conn = psycopg2.connect(
            host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb",    
            user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"]
        )
        
        query_data = """
        SELECT ticker, latest_close, stochrsi_15m, trend_15m, smart_money_daily 
        FROM gold_screener_latest;
        """
        df = pd.read_sql_query(query_data, conn)
        
        query_time = "SELECT MAX(datetime) as true_market_time FROM silver_technical_indicators;"
        time_df = pd.read_sql_query(query_time, conn)
        
        conn.close() 
        if df.empty: return None, None
        
        latest_date = time_df['true_market_time'].iloc[0]
        
        if pd.notna(latest_date):
            ts = pd.to_datetime(latest_date)
            if ts.tz is None:
                ts = ts.tz_localize('UTC')
            ts_ist = ts.tz_convert('Asia/Kolkata')
            formatted_date = ts_ist.strftime('%b %d, %Y - %I:%M %p IST')
            display_text = f"Latest Market Data - {formatted_date}"
        else:
            display_text = "Market Data: Unknown"
            
        return df, display_text
        
    except Exception as e:
        st.error(f"Failed to breach the Gold Vault: {e}")
        return None, None

@st.cache_data(ttl=900)
def load_silver_history(ticker, timeframe):
    try:
        conn = psycopg2.connect(
            host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb",    
            user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"]
        )
        
        if timeframe == '1d':
            query = f"""
            SELECT DISTINCT ON (b.datetime::date) 
                   b.datetime, b.open, b.high, b.low, b.close, 
                   s.macd_black, s.macd_red, s.rsi_2, s.stochrsi_k, s.stochrsi_d, s.rsi_14, 
                   s.nvi_black, s.nvi_red
            FROM bronze_raw_ohlcv b
            LEFT JOIN silver_1d_macro s 
                   ON b.ticker = s.ticker 
                  AND b.datetime::date = s.datetime::date
            WHERE b.ticker = '{ticker}' AND b.timeframe = '1d'
            ORDER BY b.datetime::date DESC, b.datetime DESC
            LIMIT 300;
            """
        else:
            query = f"""
            SELECT DISTINCT ON (b.datetime) 
                   b.datetime, b.open, b.high, b.low, b.close, 
                   s.macd_black, s.macd_red, s.rsi_2, s.stochrsi_k, s.stochrsi_d, s.rsi_14, 
                   NULL as nvi_black, NULL as nvi_red
            FROM bronze_raw_ohlcv b
            LEFT JOIN silver_technical_indicators s 
                   ON b.ticker = s.ticker 
                  AND b.datetime::timestamp = s.datetime::timestamp 
                  AND s.timeframe = '15m'
            WHERE b.ticker = '{ticker}' AND b.timeframe = '15m'
            ORDER BY b.datetime DESC
            LIMIT 300;
            """

        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty: return df
            
        df['datetime'] = pd.to_datetime(df['datetime'])
        
        if df['datetime'].dt.tz is not None:
            df['datetime'] = df['datetime'].dt.tz_localize(None) 
        
        return df.sort_values(by="datetime", ascending=True)
    except Exception as e:
        st.error(f"Failed to breach the Dual Vaults: {e}")
        return pd.DataFrame()

# 🛡️ THE FIX: Removed the double-shift from the ETF Sniper Radar
@st.cache_data(ttl=60) 
def load_etf_sniper_radar():
    try:
        temp_engine = create_engine(st.secrets["DATABASE_URL"])
        query = """
            SELECT DISTINCT ON (ticker)
                ticker AS "ETF Ticker", 
                TO_CHAR(signal_date, 'Mon DD, YYYY - HH12:MI AM') AS "Time Locked",
                signal_date,
                signal_type AS "Signal Type", 
                entry_price AS "Entry Price", 
                target_timeframe AS "Timeframe",
                verdict AS "Status"
            FROM gold_signal_ledger 
            WHERE ticker IN ('SILVERBEES.NS', 'GOLDBEES.NS', 'NIFTYBEES.NS', 'BANKBEES.NS', 'ITBEES.NS', 'LIQUIDBEES.NS')
            ORDER BY ticker, signal_date DESC;
        """
        df = pd.read_sql(query, temp_engine)
        temp_engine.dispose()
        
        if not df.empty:
            df = df.sort_values(by="signal_date", ascending=False)
            df = df.drop(columns=["signal_date"])
            
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_live_intraday_signals():
    try:
        temp_engine = create_engine(st.secrets["DATABASE_URL"])
        query = """
            WITH latest_1d AS (
                SELECT ticker, nvi_black, nvi_red, rsi_14, macd_black, macd_red, rsi_2 
                FROM (
                    SELECT *, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY datetime DESC) as rn 
                    FROM silver_1d_macro
                ) sub WHERE rn = 1
            ),
            latest_15m AS (
                SELECT ticker, close, rsi_2, rsi_14, stochrsi_k, stochrsi_d, macd_black, macd_red 
                FROM (
                    SELECT *, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY datetime DESC) as rn 
                    FROM silver_technical_indicators
                ) sub WHERE rn = 1
            ),
            scored_stocks AS (
                SELECT 
                    m.ticker, 
                    m.close,
                    (CASE WHEN d.nvi_black > d.nvi_red THEN 20 ELSE 0 END +
                     CASE WHEN m.macd_black > m.macd_red THEN 25 ELSE 0 END +
                     CASE WHEN m.rsi_14 > 45 THEN 25 ELSE 0 END +
                     CASE WHEN m.rsi_2 < 5 AND m.stochrsi_k < 10 AND m.stochrsi_d < 10 THEN 30 ELSE 0 END) AS buy_intraday_score
                FROM latest_15m m
                JOIN latest_1d d ON m.ticker = d.ticker
            )
            SELECT 
                s.ticker AS "Stock",
                ROUND(s.close::numeric, 2) AS "Current Price",
                s.buy_intraday_score AS "Intraday Score",
                CASE 
                    WHEN l.ticker IS NOT NULL THEN '🟢 BOUGHT (Active)'
                    WHEN s.buy_intraday_score >= 85 THEN '⚡ BUY TRIGGERED (Locking)'
                    WHEN s.buy_intraday_score >= 70 THEN '🔥 HEATING UP'
                    ELSE '⏳ WAITING'
                END AS "Signal Status"
            FROM scored_stocks s
            LEFT JOIN gold_signal_ledger l 
                ON s.ticker = l.ticker 
                AND l.verdict = 'PENDING' 
                AND l.target_timeframe = '15m'
            WHERE s.buy_intraday_score >= 50
            ORDER BY s.buy_intraday_score DESC
            LIMIT 15;
        """
        df = pd.read_sql(query, temp_engine)
        temp_engine.dispose()
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_global_macro_pulse():
    """Fetches the ultimate 5-point global macro radar using Yahoo Finance."""
    tickers = {
        "NIFTY 50": "^NSEI",
        "S&P 500": "^GSPC",
        "USD / INR": "INR=X",
        "Crude Oil": "CL=F",
        "Bitcoin": "BTC-USD"
    }
    results = {}
    try:
        for name, symbol in tickers.items():
            t = yf.Ticker(symbol)
            hist = t.history(period="5d")
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                current = hist['Close'].iloc[-1]
                pct_change = ((current - prev_close) / prev_close) * 100
                results[name] = {"value": current, "delta": pct_change}
            elif len(hist) == 1:
                 results[name] = {"value": hist['Close'].iloc[-1], "delta": 0.0}
        return results
    except Exception:
        return {}


# ==========================================
# 3. TOP LEVEL: BREADTH RADAR
# ==========================================
st.markdown("### 📡 Institutional Market Breadth")
breadth_df = load_market_breadth()

try:
    if not breadth_df.empty:
        elite_pct = breadth_df['elite_bullish_percentage'].iloc[0]
        bear_pct = breadth_df['terminal_bearish_percentage'].iloc[0]
        elite_count = breadth_df['elite_bulls'].iloc[0]
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="🐂 Elite Bullish %", value=f"{elite_pct}%", delta="Strict Confluence")
        with col2:
            st.metric(label="🐻 Terminal Bearish %", value=f"{bear_pct}%", delta="-Avoid", delta_color="inverse")
        with col3:
            st.metric(label="🎯 Active Targets", value=f"{elite_count} Stocks", delta="Ready for Screener")
        st.divider() 
except Exception as e:
    st.warning(f"Market Breadth Radar offline: {e}")


# ==========================================
# 4. SIDEBAR (Global Pulse & API Forge & ROUTER)
# ==========================================
data_result = load_gold_data()

st.sidebar.divider()
st.sidebar.subheader("🔀 Data Source Router")
try:
    conn = psycopg2.connect(
        host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb",    
        user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"]
    )
    cursor = conn.cursor()
    cursor.execute("SELECT key_value FROM system_config WHERE key_name = 'ACTIVE_DATA_SOURCE';")
    res = cursor.fetchone()
    current_source = res[0] if res else "YAHOO"

    cursor.execute("SELECT last_updated FROM system_config WHERE key_name = 'FYERS_ACCESS_TOKEN';")
    token_res = cursor.fetchone()
    
    ist = pytz.timezone('Asia/Kolkata')
    today_ist = datetime.datetime.now(ist).date()
    
    is_token_fresh = False
    if token_res and token_res[0]:
        last_up = token_res[0]
        if last_up.tzinfo is None:
            last_up = last_up.replace(tzinfo=pytz.utc)
        if last_up.astimezone(ist).date() == today_ist:
            is_token_fresh = True

    if current_source == "FYERS" and not is_token_fresh:
        current_source = "YAHOO"
        cursor.execute("UPDATE system_config SET key_value = 'YAHOO', last_updated = NOW() WHERE key_name = 'ACTIVE_DATA_SOURCE';")
        conn.commit()
        st.sidebar.warning("⚠️ Fyers Token expired. UI Auto-Reverted to YAHOO.")

    new_source = st.sidebar.radio(
        "Active Pipeline Source:", 
        ["YAHOO (Default / Free)", "FYERS (Requires Daily Token)"], 
        index=0 if current_source == "YAHOO" else 1,
        help="Select Fyers for premium intraday data. If you forget to forge the token, the pipeline will auto-fallback to Yahoo."
    )
    new_source_val = "YAHOO" if "YAHOO" in new_source else "FYERS"

    if new_source_val != current_source:
        cursor.execute("""
            INSERT INTO system_config (key_name, key_value, last_updated)
            VALUES ('ACTIVE_DATA_SOURCE', %s, NOW())
            ON CONFLICT (key_name) DO UPDATE SET key_value = EXCLUDED.key_value, last_updated = NOW();
        """, (new_source_val,))
        conn.commit()
    conn.close()
except Exception as e:
    st.sidebar.warning(f"DB Router Offline: {e}")


# 🔑 THE FYERS API FORGE
st.sidebar.divider()
st.sidebar.subheader("🔑 Fyers API Forge")
with st.sidebar.expander("Authenticate Broker"):
    fyers_client_id = st.text_input("App ID (client_id)").strip()
    fyers_secret = st.text_input("Secret Key", type="password").strip()
    fyers_redirect = "https://127.0.0.1"

    if fyers_client_id and fyers_secret:
        session = fyersModel.SessionModel(
            client_id=fyers_client_id, 
            secret_key=fyers_secret, 
            redirect_uri=fyers_redirect, 
            response_type="code", 
            grant_type="authorization_code"
        )
        login_url = session.generate_authcode()
        
        st.markdown(f"**1. [🔗 CLICK HERE TO LOGIN]({login_url})**")
        st.caption("Log in. Look at the URL bar on the final page. Copy the text after 'auth_code=' and before '&state'.")
        
        auth_code = st.text_input("2. Paste Auth Code Here:").strip()
        
        if st.button("3. Forge Master Token"):
            session.set_token(auth_code)
            response = session.generate_token()
            if "access_token" in response:
                try:
                    conn = psycopg2.connect(
                        host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb",    
                        user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"]
                    )
                    cursor = conn.cursor()
                    
                    update_token = """
                        INSERT INTO system_config (key_name, key_value, last_updated) 
                        VALUES ('FYERS_ACCESS_TOKEN', %s, NOW())
                        ON CONFLICT (key_name) DO UPDATE SET key_value = EXCLUDED.key_value, last_updated = NOW();
                    """
                    cursor.execute(update_token, (response["access_token"],))
                    
                    update_router = """
                        INSERT INTO system_config (key_name, key_value, last_updated) 
                        VALUES ('ACTIVE_DATA_SOURCE', 'FYERS', NOW())
                        ON CONFLICT (key_name) DO UPDATE SET key_value = EXCLUDED.key_value, last_updated = NOW();
                    """
                    cursor.execute(update_router)
                    
                    conn.commit()
                    conn.close()
                    st.success("✅ Handshake Successful! Token secured and Data Router switched to FYERS.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Token acquired, but DB save failed: {e}")
            else:
                st.error(f"Failed: {response}")

st.sidebar.divider()

if data_result[0] is None: st.stop() 

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

st.sidebar.subheader("🌐 Global Macro Radar")
macro_data = load_global_macro_pulse()
if macro_data:
    for asset, data in macro_data.items():
        if asset in ["USD / INR", "Crude Oil"]:
            st.sidebar.metric(label=asset, value=f"{data['value']:,.2f}", delta=f"{data['delta']:.2f}%", delta_color="inverse")
        else:
            st.sidebar.metric(label=asset, value=f"{data['value']:,.2f}", delta=f"{data['delta']:.2f}%", delta_color="normal")
            
st.sidebar.divider()


# ==========================================
# 5. MAIN UI (Tabs)
# ==========================================
st.title("⚖️ The Market Oracle")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 The Screener", 
    "📈 The X-Ray Sandbox", 
    "⚡ Intraday Ledger", 
    "🏛️ Macro Ledger", 
    "🎯 ETF Sniper Radar"
])

# ------------------------------------------
# TAB 1: THE SCREENER (Gold Layer)
# ------------------------------------------
with tab1:
    st.subheader("🏆 The Oracle's True Win Rate")
    try:
        ledger_df = load_ledger_scoreboard()
        if not ledger_df.empty:
            total_settled = ledger_df['total_signals'].iloc[0]
            if total_settled > 0:
                win_rate = (ledger_df['total_wins'].iloc[0] / total_settled) * 100
                avg_ret = ledger_df['average_return'].iloc[0]
                st.metric(label=f"System Accuracy ({total_settled} Settled Trades)", value=f"{win_rate:.1f}%", delta=f"Avg Return: {avg_ret}%")
            else:
                st.info("📊 Forward-Testing Engine Active. Awaiting first T+1 settlements...")
        else:
            st.info("📊 Forward-Testing Engine Active. Awaiting first T+1 settlements...")
    except Exception as e:
        st.warning("Ledger Database Offline.")
    
    st.divider()
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

    bullish_mask = (df['trend_15m'] == 'BULLISH')
    bearish_mask = (df['trend_15m'] == 'BEARISH')
    
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

    st.divider()
    st.subheader("📁 The Full Data Vault")
    search_query = st.text_input("🔍 Search Stock Symbol (e.g., RELIANCE, HDFC)", "").upper()
    vault_df = df[df['ticker'].str.contains(search_query, na=False)] if search_query else df
    st.dataframe(vault_df[['ticker', 'latest_close', 'stochrsi_15m', 'smart_money_daily', 'trend_15m']], use_container_width=True, height=400)
    st.divider()
    st.caption(f"Last Vault Update: {filename}")


# ------------------------------------------
# TAB 2: THE X-RAY SANDBOX
# ------------------------------------------
with tab2:
    st.subheader("🔬 Institutional Indicator X-Ray")
    ctrl_col1, ctrl_col2 = st.columns([2, 1])
    with ctrl_col1:
        target_ticker = st.selectbox("Select Asset to Analyze:", df['ticker'].sort_values().unique())
    with ctrl_col2:
        selected_tf_label = st.radio("Lens (Timeframe):", ["15m (Intraday)", "1h (Swing)", "1d (Macro)"], horizontal=True)
    
    tf_map = {"15m (Intraday)": "15m", "1h (Swing)": "1h", "1d (Macro)": "1d"}
    target_timeframe = tf_map[selected_tf_label]
    
    if target_ticker:
        chart_df = load_silver_history(target_ticker, target_timeframe)
        if not chart_df.empty:
            chart_df['macd_hist'] = chart_df['macd_black'] - chart_df['macd_red']
            chart_df['rsi_2_over'] = chart_df['rsi_2'].clip(lower=75)
            chart_df['rsi_2_under'] = chart_df['rsi_2'].clip(upper=20)

            if target_timeframe == '1d':
                chart_df['display_time'] = chart_df['datetime'].dt.strftime('%b %d, %Y')
            else:
                chart_df['display_time'] = chart_df['datetime'].dt.strftime('%b %d, %H:%M')

            fig = make_subplots(
                rows=6, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                row_heights=[0.25, 0.15, 0.15, 0.15, 0.15, 0.15],
                subplot_titles=(
                    f"{target_ticker} - Close Price", "MACD (12, 26, 9)", 
                    "RSI (2) - Extreme Mean Reversion", "Stochastic RSI (14, 14, 3, 3)", 
                    "RSI (14) - Structural Trend", "NVI - Institutional Flow"
                )
            )

            # ROW 1: PRICE
            fig.add_trace(go.Candlestick(
                x=chart_df['display_time'], open=chart_df['open'], high=chart_df['high'],
                low=chart_df['low'], close=chart_df['close'], name='Price',
                increasing_line_color='#26A69A', decreasing_line_color='#EF5350' 
            ), row=1, col=1)
            
            # ROW 2: MACD 
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['macd_black'], name='MACD Line', line=dict(color='white', width=1.5)), row=2, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['macd_red'], name='Signal Line', line=dict(color='red', width=1.5)), row=2, col=1)
            
            # ROW 3: RSI (2)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=[75]*len(chart_df), mode='lines', line=dict(color='rgba(0,0,0,0)', width=0), hoverinfo='skip'), row=3, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['rsi_2_over'], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(255,255,255,0.3)', hoverinfo='skip'), row=3, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=[20]*len(chart_df), mode='lines', line=dict(color='rgba(0,0,0,0)', width=0), hoverinfo='skip'), row=3, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['rsi_2_under'], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(255,255,255,0.3)', hoverinfo='skip'), row=3, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['rsi_2'], name='RSI(2)', line=dict(color='#FFA500', width=1.5)), row=3, col=1)

            # ROW 4: TRADINGVIEW PARITY STOCHASTIC RSI
            fig.add_hrect(y0=20, y1=80, fillcolor="rgba(255, 100, 100, 0.05)", layer="below", line_width=0, row=4, col=1)
            fig.add_hline(y=80, line_width=1, line_color="gray", line_dash="dash", row=4, col=1)
            fig.add_hline(y=20, line_width=1, line_color="gray", line_dash="dash", row=4, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['stochrsi_k'], name='%K Line (Blue)', line=dict(color='#0055FF', width=1.5)), row=4, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['stochrsi_d'], name='%D Line (Orange)', line=dict(color='#FF9900', width=1.2, dash='dot')), row=4, col=1)

            # ROW 5: RSI (14)
            fig.add_hline(y=70, line_dash="dot", line_color="red", row=5, col=1)
            fig.add_hline(y=30, line_dash="dot", line_color="green", row=5, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['rsi_14'], name='RSI(14)', line=dict(color='#E0E0E0', width=1.5)), row=5, col=1)

            # ROW 6: NVI
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['nvi_black'], name='NVI Raw', line=dict(color='white', width=1.5)), row=6, col=1)
            fig.add_trace(go.Scatter(x=chart_df['display_time'], y=chart_df['nvi_red'], name='NVI EMA(255)', line=dict(color='#FF3333', width=1.5)), row=6, col=1)

            # VALUE BUBBLES
            last_date = chart_df['display_time'].iloc[-1]
            last_k = chart_df['stochrsi_k'].iloc[-1]
            last_d = chart_df['stochrsi_d'].iloc[-1]
            
            if pd.notna(last_k):
                fig.add_annotation(x=last_date, y=last_k, text=f"<b>K: {last_k:.1f}</b>", showarrow=False, xanchor='left', xshift=10, bgcolor="#0055FF", font=dict(color="white", size=10), borderpad=2, row=4, col=1)
            if pd.notna(last_d):
                fig.add_annotation(x=last_date, y=last_d, text=f"<b>D: {last_d:.1f}</b>", showarrow=False, xanchor='left', xshift=55, bgcolor="#FF9900", font=dict(color="white", size=10), borderpad=2, row=4, col=1)

            last_nvi_black = chart_df['nvi_black'].iloc[-1]
            last_nvi_red = chart_df['nvi_red'].iloc[-1]
            if pd.notna(last_nvi_black):
                fig.add_annotation(x=last_date, y=last_nvi_black, text=f"<b>{last_nvi_black:.2f}</b>", showarrow=False, xanchor='left', xshift=10, bgcolor="white", font=dict(color="black", size=11), borderpad=3, row=6, col=1)
            if pd.notna(last_nvi_red):
                fig.add_annotation(x=last_date, y=last_nvi_red, text=f"<b>{last_nvi_red:.2f}</b>", showarrow=False, xanchor='left', xshift=10, bgcolor="#FF3333", font=dict(color="white", size=11), borderpad=3, row=6, col=1)

            fig.update_layout(
                height=1200, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                showlegend=False, margin=dict(l=0, r=90, t=30, b=0), dragmode='pan', xaxis_rangeslider_visible=False
            )
            fig.update_xaxes(
                type='category', 
                nticks=12, 
                tickangle=-45, 
                categoryorder='array', 
                categoryarray=chart_df['display_time']
            )
            fig.update_yaxes(fixedrange=True)

            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom':False, 'displayModeBar': False})
        else:
            st.warning("Historical data is still warming up for this asset.")

# ------------------------------------------
# TAB 3: INTRADAY LEDGER (15m)
# ------------------------------------------
with tab3:
    st.subheader("⚡ Intraday Sniper Operations")

    df_intra_today = load_daily_executions('15m')
    intra_pnl_today = load_daily_pnl('15m')
    df_intra_portfolio = load_active_portfolio('15m')

    intra_avg_pnl = df_intra_portfolio["Unrealized PNL (%)"].mean() if not df_intra_portfolio.empty else 0.00

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Today's Executions", len(df_intra_today))
    col2.metric("Today's Settled PNL", f"{intra_pnl_today:.2f}%", delta=f"{intra_pnl_today:.2f}%" if intra_pnl_today >= 0 else f"{intra_pnl_today:.2f}%")
    col3.metric("Open Intraday Positions", len(df_intra_portfolio))
    col4.metric("Avg Unrealized PNL", f"{intra_avg_pnl:.2f}%", delta="Profitable" if intra_avg_pnl > 0 else "Drawdown", delta_color="normal" if intra_avg_pnl > 0 else "inverse")

    st.divider()

    st.markdown("### 📡 Live Signal Radar (The Matrix)")
    st.caption("Displays the real-time computational scores. Tracks targets as they heat up before AWS execution.")
    df_live_signals = load_live_intraday_signals()

    if not df_live_signals.empty:
        def color_signal_status(val):
            val_str = str(val).upper()
            if 'BOUGHT' in val_str:
                return 'background-color: rgba(9, 171, 59, 0.2); color: #09ab3b; font-weight: bold;'
            elif 'TRIGGERED' in val_str:
                return 'background-color: rgba(255, 75, 75, 0.2); color: #ff4b4b; font-weight: bold;'
            elif 'HEATING' in val_str:
                return 'color: #FFA500; font-weight: bold;'
            return 'color: gray;'

        st.dataframe(
            df_live_signals.style.map(color_signal_status, subset=['Signal Status']),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Radar is quiet. No stocks are currently showing intraday momentum.")

    st.divider()

    st.markdown("### 🟢 Active Open Intraday")
    if not df_intra_portfolio.empty:
        def color_pnl(val):
            color = '#26A69A' if val > 0 else '#EF5350' if val < 0 else 'gray'
            return f'color: {color}; font-weight: bold;'

        st.dataframe(df_intra_portfolio.style.map(color_pnl, subset=["Unrealized PNL (%)"]), use_container_width=True, hide_index=True)
    else:
        st.info("No active open intraday positions.")

    st.divider()

    st.markdown("### 📋 Today's Order Book")
    if not df_intra_today.empty:
        st.dataframe(df_intra_today, use_container_width=True, hide_index=True)
    else:
        st.info("No intraday actions executed yet during today's session.")

    st.divider()

    st.markdown("### 📈 Weekly Performance Curve (Last 7 Days)")
    df_intra_weekly = load_period_performance('15m', 7)
    if not df_intra_weekly.empty:
        df_intra_weekly["Cumulative Growth (%)"] = df_intra_weekly["Daily PNL (%)"].cumsum()
        fig_intra = px.line(df_intra_weekly, x="Date", y="Cumulative Growth (%)", title="Intraday Cumulative Variance", markers=True)
        st.plotly_chart(fig_intra, use_container_width=True)
    else:
        st.warning("Insufficient baseline data available to plot the 7-day intraday equity curve.")


# ------------------------------------------
# TAB 4: MACRO Ledger (1D)
# ------------------------------------------
with tab4:
    st.subheader("🏛️ Structural Allocation & Positions")
    
    df_macro_portfolio = load_active_portfolio('1d')
    if not df_macro_portfolio.empty:
        macro_avg_pnl = df_macro_portfolio["Unrealized PNL (%)"].mean()
        col1, col2 = st.columns(2)
        col1.metric("Open Macro Positions", len(df_macro_portfolio))
        col2.metric("Average Unrealized PNL", f"{macro_avg_pnl:.2f}%", delta="Profitable" if macro_avg_pnl > 0 else "Drawdown", delta_color="normal" if macro_avg_pnl > 0 else "inverse")
        
        def color_pnl(val):
            color = '#26A69A' if val > 0 else '#EF5350' if val < 0 else 'gray'
            return f'color: {color}; font-weight: bold;'
            
        st.dataframe(df_macro_portfolio.style.map(color_pnl, subset=["Unrealized PNL (%)"]), use_container_width=True, hide_index=True)
    else:
        st.info("No active open macro positions.")
        
    st.divider()
    
    st.subheader("📅 Historical Macro Performance")
    
    macro_period = st.radio("Select Lookback Period:", ["Last 7 Days", "Last 30 Days"], horizontal=True)
    days_lookback = 7 if "7" in macro_period else 30
    
    df_macro_history = fetch_macro_trade_lifecycle('1d', days_lookback)
    macro_period_pnl = load_historical_pnl('1d', days_lookback)
    
    col3, col4 = st.columns(2)
    col3.metric(f"Total Executions ({macro_period})", len(df_macro_history))
    col4.metric(f"Settled PNL ({macro_period})", f"{macro_period_pnl:.2f}%", delta=f"{macro_period_pnl:.2f}%" if macro_period_pnl >= 0 else f"{macro_period_pnl:.2f}%")
    
    st.markdown(f"### 📋 Trade Ledger ({macro_period})")
    
    if not df_macro_history.empty:
        st.dataframe(
            df_macro_history, 
            use_container_width=True, 
            hide_index=True
        )
    else:
        st.info(f"No systemic macro shifts or settled trades detected in the {macro_period.lower()}.")
        
    st.divider()
    
    st.markdown(f"### 🏛️ Structural Capital Curve ({macro_period})")
    df_macro_curve = load_period_performance('1d', days_lookback)
    if not df_macro_curve.empty:
        df_macro_curve["Structural Growth (%)"] = df_macro_curve["Daily PNL (%)"].cumsum()
        fig_macro = px.area(df_macro_curve, x="Date", y="Structural Growth (%)", title=f"Macro Framework Long-Term Equity Curve ({macro_period})")
        st.plotly_chart(fig_macro, use_container_width=True)
    else:
        st.warning(f"Insufficient baseline data available to plot the {macro_period.lower()} macro position curve.")

# ------------------------------------------
# TAB 5: ETF SNIPER RADAR
# ------------------------------------------
with tab5:
    st.subheader("🎯 Institutional ETF Sniper Radar")
    st.markdown("Live monitoring of Dual-Matrix execution signals exclusively for indexed ETFs.")
    
    etf_df = load_etf_sniper_radar()
    
    if not etf_df.empty:
        col1, col2, col3 = st.columns(3)
        total_etf_signals = len(etf_df)
        intraday_etf_count = len(etf_df[etf_df['Signal Type'].str.contains('INTRADAY', na=False)])
        macro_etf_count = len(etf_df[etf_df['Signal Type'].str.contains('LONG_TERM', na=False)])
        
        col1.metric("Total ETF Locks (Recent)", total_etf_signals)
        col2.metric("Intraday Snipes (15m)", intraday_etf_count)
        col3.metric("Macro Bull Locks (1d)", macro_etf_count)
        
        st.divider()
        
        def color_etf_signals(val):
            val_str = str(val).upper()
            if 'SELL_HARVEST' in val_str:
                return 'background-color: rgba(255, 215, 0, 0.2); color: #ffd700; font-weight: bold;'
            elif 'SELL_EVAC' in val_str:
                return 'background-color: rgba(255, 100, 100, 0.2); color: #ff0000; font-weight: bold;'
            elif 'INTRADAY' in val_str:
                return 'background-color: rgba(255, 75, 75, 0.2); color: #ff4b4b; font-weight: bold;'
            elif 'LONG_TERM' in val_str:
                return 'background-color: rgba(9, 171, 59, 0.2); color: #09ab3b; font-weight: bold;'
            return ''

        st.dataframe(
            etf_df.style.map(color_etf_signals, subset=['Signal Type']),
            use_container_width=True,
            hide_index=True
        )
        
        if st.button("🔄 Force Radar Sweep"):
            st.cache_data.clear()
            st.rerun()
            
    else:
        st.info("🛡️ ETF Radar Clear. No targets locked recently.")
