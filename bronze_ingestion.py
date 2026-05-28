import os
import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine
import requests
import io
import time

# ==========================================
# 1. SETUP AND SECURE CREDENTIALS
# ==========================================
db_password = os.getenv("NEON_PASSWORD")
if not db_password:
    raise ValueError("⚠️ CRITICAL: NEON_PASSWORD environment variable is missing!")

NEON_HOST = "ep-holy-star-amh8eg8r-pooler.c-5.us-east-1.aws.neon.tech"
db_url = f"postgresql://neondb_owner:{db_password}@{NEON_HOST}:5432/neondb?sslmode=require"
engine = create_engine(db_url)

# ==========================================
# 2. DYNAMIC NIFTY 500 INGESTION
# ==========================================
print("🌐 Fetching live Nifty 500 list from NSE servers...")
url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    nifty_df = pd.read_csv(io.StringIO(response.text))
    raw_tickers = nifty_df['Symbol'].tolist()
    # Format for Yahoo Finance
    tickers = [f"{sym}.NS" for sym in raw_tickers]
    tickers.extend(["SILVERBEES.NS", "GOLDBEES.NS"])
    print(f"✅ Successfully loaded {len(tickers)} tickers.")
except Exception as e:
    print(f"⚠️ NSE Fetch failed: {e}. Defaulting to core list.")
    tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ADANIPORTS.NS"]

# ==========================================
# 3. BULK YAHOO FINANCE FETCHING
# ==========================================
print(f"🚀 Starting Bronze Ingestion for {len(tickers)} assets...")

# Define the exact timeframes your Oracle requires
timeframes = {
    "15m": "60d", # Max allowed by YF for intraday
    "1h": "730d", # Max allowed by YF for hourly
    "1d": "2y"    # Standard macro lookback
}

master_df = pd.DataFrame()

# We use YF's built-in bulk download feature to avoid IP bans
for tf_name, period in timeframes.items():
    print(f"📥 Downloading {tf_name} timeframe...")
    
    # Bulk download is faster and less likely to trigger rate limits
    data = yf.download(tickers, period=period, interval=tf_name, group_by='ticker', threads=True, progress=False)
    
    for ticker in tickers:
        if ticker in data:
            df = data[ticker].dropna(how='all')
            if not df.empty:
                df = df.reset_index()
                
                # Standardize Column Names
                df.columns = [col.lower() for col in df.columns]
                if 'datetime' not in df.columns:
                    df = df.rename(columns={'date': 'datetime'})
                    
                df['ticker'] = ticker
                df['timeframe'] = tf_name
                
                # Keep only necessary columns
                try:
                    df = df[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 'volume']]
                    master_df = pd.concat([master_df, df], ignore_index=True)
                except KeyError:
                    continue

# ==========================================
# 4. LOAD TO BRONZE VAULT
# ==========================================
if not master_df.empty:
    print("💾 Pushing fresh data into the Bronze Vault...")
    # if_exists="replace" prevents the massive duplicate bloat issue. 
    # It wipes the slate clean and loads the perfect, rolling 60-day window.
    master_df.to_sql("bronze_raw_ohlcv", engine, if_exists="replace", index=False)
    print("✅ Bronze Ingestion Complete!")
else:
    print("⚠️ FATAL: No data was fetched across any timeframes.")
