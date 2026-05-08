import streamlit as st
import pandas as pd
import yfinance as yf
import psycopg2
from datetime import datetime

# 1. Page Configuration
st.set_page_config(page_title="The Oracle: Global Intelligence", page_icon="⚖️", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def load_data():
    try:
        conn = psycopg2.connect(host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb", user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"])
        query = "SELECT ticker AS \"Ticker\", price AS \"1D_Price\", stoch_k AS \"1D_Stoch_K_Black\", macd_black AS \"15m_MACD_Black\", macd_red AS \"15m_MACD_Red\", nvi_black AS \"1D_NVI_Black\", nvi_red AS \"1D_NVI_Red\", trade_date AS \"Date\" FROM nifty_daily_signals WHERE trade_date = (SELECT MAX(trade_date) FROM nifty_daily_signals);"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df, f"Cloud Vault - {df['Date'].iloc[0]}" if not df.empty else (None, None)
    except: return None, None

def load_audit_kpis():
    try:
        conn = psycopg2.connect(host=st.secrets["DB_HOST"], port=st.secrets["DB_PORT"], dbname="neondb", user=st.secrets["DB_USER"], password=st.secrets["DB_PASS"])
        df_audit = pd.read_sql_query("SELECT is_accurate FROM signal_audit WHERE is_accurate IS NOT NULL", conn)
        conn.close()
        return df_audit
    except: return pd.DataFrame()

# Data Execution
data_df, filename = load_data()
audit_df = load_audit_kpis()

if data_df is None:
    st.error("🚨 **CRITICAL ALERT:** Connection Lost.")
    st.stop()

# --- MAIN UI ---
if not audit_df.empty:
    acc = (audit_df['is_accurate'].sum() / len(audit_df)) * 100
    k1, k2, k3 = st.columns(3)
    k1.metric("System Accuracy", f"{acc:.1f}%")
    k2.metric("Signals Audited", len(audit_df))
    k3.metric("Last Audit", "✅ WIN" if audit_df['is_accurate'].iloc[-1] else "❌ LOSS")
    st.divider()

st.title("⚖️ The Market Oracle")
signal_type = st.radio("⚔️ **SIGNAL:**", ["BUY", "SELL"], horizontal=True)

# Math Logic
b_mask = (data_df['1D_Stoch_K_Black'] < 40) & (data_df['15m_MACD_Black'] > data_df['15m_MACD_Red']) & (data_df['1D_NVI_Black'] > data_df['1D_NVI_Red'])
s_mask = (data_df['1D_Stoch_K_Black'] > 75) & (data_df['15m_MACD_Black'] < data_df['15m_MACD_Red']) & (data_df['1D_NVI_Black'] < data_df['1D_NVI_Red'])

if "BUY" in signal_type:
    top_10 = data_df[b_mask].sort_values(by='1D_Stoch_K_Black').head(10)
    color, verdict = "green", "REBOUND"
else:
    top_10 = data_df[s_mask].sort_values(by='1D_Stoch_K_Black', ascending=False).head(10)
    color, verdict = "red", "COLLAPSE"

if not top_10.empty:
    cols = st.columns(5)
    for idx, (i, row) in enumerate(top_10.iterrows()):
        with cols[idx % 5]: st.metric(label=row['Ticker'], value=f"₹{row['1D_Price']}", delta=verdict, delta_color="normal" if color=="green" else "inverse")
    st.dataframe(top_10[['Ticker', '1D_Price', '1D_Stoch_K_Black', '1D_NVI_Black']], use_container_width=True)
else:
    st.error("### 🚫 NO TRADE ZONE - The Oracle is Silent")

st.divider()
st.header("📁 Data Vault")
search = st.text_input("🔍 Search Symbol", "").upper()
final_df = data_df[data_df['Ticker'].str.contains(search)] if search else data_df
st.dataframe(final_df, use_container_width=True)
st.caption(f"Update: {filename}")
