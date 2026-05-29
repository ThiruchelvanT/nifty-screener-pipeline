import os
import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine, text
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
# 3. YAHOO FINANCE FETCHING (ANTI-BAN BATCHING)
# ==========================================
print(f"🚀 Starting Bronze Ingestion for {len(tickers)} assets...")
master_df = pd.DataFrame()

# --- STEP 3A: THE MACRO PULL (Bulk) ---
# YF allows bulk daily pulls without triggering massive rate limits
print("📥 Downloading Macro 1d timeframe (Bulk)...")
data_1d = yf.download(tickers, period="2y", interval="1d", group_by='ticker', threads=True, progress=False)

for ticker in tickers:
    if ticker in data_1d:
        df = data_1d[ticker].dropna(how='all')
        if not df.empty:
            df = df.reset_index()
            df.columns = [col.lower() for col in df.columns]
            if 'date' in df.columns: 
                df = df.rename(columns={'date': 'datetime'})
            
            df['ticker'] = ticker
            df['timeframe'] = '1d'
            
            try:
                df = df[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 'volume']]
                master_df = pd.concat([master_df, df], ignore_index=True)
            except KeyError:
                continue

# --- STEP 3B: THE INTRADAY PULL (Phalanx Formation) ---
print("📥 Downloading Intraday 15m & 1h timeframes (Batch Mode)...")
intraday_tfs = {"15m": "60d", "1h": "730d"}

# Break the 500 tickers into manageable batches of 100 to avoid rate limits
batch_size = 100
ticker_batches = [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]

for tf_name, period in intraday_tfs.items():
    for i, batch in enumerate(ticker_batches):
        print(f"   Fetching {tf_name} Batch {i+1}/{len(ticker_batches)}...")
        try:
            # Bulk download only the current batch of 100
            data = yf.download(batch, period=period, interval=tf_name, group_by='ticker', threads=True, progress=False)
            
            for ticker in batch:
                if ticker in data:
                    df = data[ticker].dropna(how='all')
                    if not df.empty:
                        df = df.reset_index()
                        df.columns = [col.lower() for col in df.columns]
                        if 'datetime' not in df.columns: 
                            if 'date' in df.columns:
                                df = df.rename(columns={'date': 'datetime'})
                        
                        df['ticker'] = ticker
                        df['timeframe'] = tf_name
                        
                        try:
                            df = df[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 'volume']]
                            master_df = pd.concat([master_df, df], ignore_index=True)
                        except KeyError:
                            continue
            
            # Anti-ban sleep between massive batches
            time.sleep(2)
            
        except Exception as e:
            print(f"   ⚠️ Batch {i+1} failed for {tf_name}: {e}")

# ==========================================
# 4. LOAD TO BRONZE VAULT (THE UPSERT ARCHITECTURE)
# ==========================================
# ==========================================
# 4. LOAD TO BRONZE VAULT (DELTA LOAD ARCHITECTURE)
# ==========================================
if not master_df.empty:
    print(f"📊 Downloaded {len(master_df)} raw rows. Calculating Delta...")
    
    try:
        # 1. Ask the Database for the most recent timestamps it already has
        latest_dates_query = "SELECT ticker, timeframe, MAX(datetime) as max_date FROM bronze_raw_ohlcv GROUP BY ticker, timeframe"
        latest_dates = pd.read_sql(latest_dates_query, engine)
        
        if not latest_dates.empty:
            # Standardize timezones so Pandas can compare them flawlessly
            master_df['datetime'] = pd.to_datetime(master_df['datetime'], utc=True)
            latest_dates['max_date'] = pd.to_datetime(latest_dates['max_date'], utc=True)
            
            # 2. Merge the database memory with the downloaded data
            master_df = master_df.merge(latest_dates, on=['ticker', 'timeframe'], how='left')
            
            # 3. THE FILTER: Keep ONLY rows that are newer than the database's max_date
            master_df = master_df[(master_df['datetime'] > master_df['max_date']) | (master_df['max_date'].isnull())]
            master_df = master_df.drop(columns=['max_date'])
            
    except Exception as e:
        print(f"⚠️ Delta check bypassed (maybe table doesn't exist yet). Proceeding with all rows. Error: {e}")

    # 4. Push only the tiny fraction of new rows
    if not master_df.empty:
        print(f"💾 Pushing {len(master_df)} NEW rows into the Bronze Vault...")
        master_df.to_sql("bronze_raw_ohlcv", engine, if_exists="append", index=False)
        print("✅ Bronze Delta Ingestion Complete!")
    else:
        print("✅ Vault is perfectly up to date. No new rows needed.")
else:
    print("⚠️ FATAL: No data was fetched across any timeframes.")
