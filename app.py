import streamlit as st
import pandas as pd
import glob
import os
from datetime import datetime

# 1. Page Configuration
st.set_page_config(page_title="The Oracle: Indian Market Decoder", page_icon="⚖️", layout="wide")

# Custom Styling for the "Elite System" Look
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 10px; }
    [data-testid="stMetricDelta"] svg { display: none; } /* Hide default arrows for custom look */
    </style>
    """, unsafe_allow_html=True)

# 2. Data Loading Engine
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

    # --- SIDEBAR: SYSTEM SETTINGS & FILTERS ---
    st.sidebar.title("⚙️ System Core")
    
    # Market Pulse Proxy
    nifty_proxy = df[df['Ticker'] == 'RELIANCE.NS'].iloc[0] if 'RELIANCE.NS' in df['Ticker'].values else None
    if nifty_proxy is not None:
        market_bullish = nifty_proxy['1D_NVI_Black'] > nifty_proxy['1D_NVI_Red']
        st.sidebar.metric("Nifty Health Proxy", "✅ STABLE" if market_bullish else "⚠️ WEAK")
    else:
        market_bullish = True

    st.sidebar.divider()
    st.sidebar.subheader("🎚️ Sensitivity Tuning")
    stoch_threshold = st.sidebar.slider("Stochastic RSI Bound", 10, 50, 25, help="Lower = More Brutal/Selective")
    nvi_required = st.sidebar.toggle("Require NVI Accumulation", value=True)

    # --- MAIN TABS ---
    tab1, tab2 = st.tabs(["🔮 THE ORACLE", "📁 THE DATA VAULT"])

    with tab1:
        st.title("⚖️ The Market Oracle")
        st.markdown("> **The Council:** Decoding mathematically verified reality. No sugarcoating.")
        
        signal_type = st.radio("⚔️ **SIGNAL SELECTION:**", ["BUY (The Rebound)", "SELL (The Collapse)"], horizontal=True)

        # Logic Engine
        if "BUY" in signal_type:
            mask = (df['1D_Stoch_K_Black'] < stoch_threshold) & (df['15m_MACD_Black'] > df['15m_MACD_Red'])
            if nvi_required: mask &= (df['1D_NVI_Black'] > df['1D_NVI_Red'])
            verdict, color, sort_asc = "REBOUND", "green", True
        else:
            mask = (df['1D_Stoch_K_Black'] > (100 - stoch_threshold)) & (df['15m_MACD_Black'] < df['15m_MACD_Red'])
            if nvi_required: mask &= (df['1D_NVI_Black'] < df['1D_NVI_Red'])
            verdict, color, sort_asc = "COLLAPSE", "red", False

        top_10 = df[mask].sort_values(by='1D_Stoch_K_Black', ascending=sort_asc).head(10)

        if not top_10.empty:
            cols = st.columns(5)
            for idx, (i, row) in enumerate(top_10.iterrows()):
                with cols[idx % 5]:
                    st.metric(label=row['Ticker'], value=f"₹{row['1D_Price']}", delta=verdict, delta_color="normal" if color=="green" else "inverse")
            st.divider()
            st.dataframe(top_10, use_container_width=True)
        else:
            st.warning("The Mathematician finds no 100% factual setups. Adjust sensitivity or wait for market alignment.")

    with tab2:
        st.title("📁 The Data Vault")
        st.markdown("Full raw intelligence access. Use the headers to sort and the search icon to filter any column.")
        
        # Professional Excel-like experience
        st.dataframe(
            df, 
            use_container_width=True, 
            height=600,
            column_config={
                "1D_Price": st.column_config.NumberColumn("Price", format="₹%.2f"),
                "1D_Stoch_K_Black": st.column_config.ProgressColumn("Stoch RSI", min_value=0, max_value=100),
                "Ticker": "Stock Symbol"
            }
        )
        
        # Download Button for Excel/CSV
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export Vault to CSV", data=csv, file_name=f"Nifty500_Full_Scan_{datetime.now().date()}.csv", mime="text/csv")

    st.caption(f"Source: {filename} | Engine Active")
