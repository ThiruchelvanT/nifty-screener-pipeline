import os
import sys
import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine, text
import requests
import io
import time
import random
from requests import Session

# ==========================================
# 0. THE MODE SWITCH (Command Line Argument)
# ==========================================
# If "--intraday" is passed, we skip the heavy 1D pull and only fetch recent 15m data
is_intraday_mode = "--intraday" in sys.argv

if is_intraday_mode:
    print("⚡ INTRADAY MODE ACTIVATED: Featherweight fetch to prevent API bans.")
else:
    print("🏗️ MACRO MODE ACTIVATED: Heavy historical fetch.")

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
# 3. YAHOO FINANCE FETCHING (GUERRILLA EVASION PROTOCOL)
# ==========================================
print(f"🚀 Starting Bronze Ingestion for {len(tickers)} assets...")
master_df = pd.DataFrame()

# 🛡️ THE DISGUISE: A pool of real human browser signatures
user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

# Create a custom session to spoof the headers
session = Session()
session.headers.update({
    'User-Agent': random.choice(user_agents),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
})

# --- STEP 3A: THE MACRO PULL (Only run if NOT in intraday mode) ---
if not is_intraday_mode:
    # ⚡ OPTIMIZATION: We only fetch 5 days now to save memory, relying on the DB for deep history
    print("📥 Downloading Macro 1d timeframe (Optimized 5-Day Sip)...")
    data_1d = yf.download(tickers, period="5d", interval="1d", group_by='ticker', threads=True, progress=False, session=session)

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

# --- STEP 3B: THE INTRADAY PULL (Phalanx Formation & Micro-Batching) ---
# If Intraday mode, ONLY pull the last 5 days to save bandwidth. Otherwise, pull 60 days.
intraday_period = "5d" if is_intraday_mode else "60d"
print(f"📥 Downloading Intraday 15m timeframe (Period: {intraday_period})...")
intraday_tfs = {"15m": intraday_period}

# 🛡️ MICRO-BATCHING: Shrink the batch size from 100 to 50 to avoid massive parallel spikes
batch_size = 50
ticker_batches = [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]

for tf_name, period in intraday_tfs.items():
    for i, batch in enumerate(ticker_batches):
        print(f"   Fetching {tf_name} Batch {i+1}/{len(ticker_batches)}...")
        try:
            # Pass the spoofed session directly into yfinance
            data = yf.download(batch, period=period, interval=tf_name, group_by='ticker', threads=True, progress=False, session=session)
            
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
            
            # 🛡️ ALGORITHMIC JITTER: Random sleep between 2.1 and 4.7 seconds
            jitter = random.uniform(2.1, 4.7)
            time.sleep(jitter)
            
            # Rotate the user-agent mid-run to further confuse the WAF
            session.headers.update({'User-Agent': random.choice(user_agents)})
            
        except Exception as e:
            print(f"   ⚠️ Batch {i+1} failed for {tf_name}: {e}")

# ==========================================
# 4. SELF-HEALING DELTA LOAD ARCHITECTURE
# ==========================================
if not master_df.empty:
    print(f"📊 Downloaded {len(master_df)} raw rows. Initiating Database Memory Check...")
    
    try:
        # 1. Ask Database for its memory: What was the exact closing price on the latest date you have?
        memory_query = """
            SELECT DISTINCT ON (ticker, timeframe) 
                ticker, timeframe, datetime AS db_max_date, close AS db_close 
            FROM bronze_raw_ohlcv 
            ORDER BY ticker, timeframe, datetime DESC;
        """
        db_memory = pd.read_sql(memory_query, engine)
        
        corrupted_tickers = []
        
        if not db_memory.empty:
            master_df['datetime'] = pd.to_datetime(master_df['datetime'], utc=True)
            db_memory['db_max_date'] = pd.to_datetime(db_memory['db_max_date'], utc=True)
            
            # 2. Merge Yahoo's fresh data with the Database's memory based on the exact same date
            check_df = master_df.merge(
                db_memory, 
                left_on=['ticker', 'timeframe', 'datetime'], 
                right_on=['ticker', 'timeframe', 'db_max_date'], 
                how='inner'
            )
            
            # 3. THE SPLIT DETECTOR: Find where Database Close differs from Yahoo Close by > 10%
            if not check_df.empty:
                check_df['price_diff_pct'] = abs(check_df['close'] - check_df['db_close']) / check_df['db_close']
                corrupted_tickers = check_df[check_df['price_diff_pct'] > 0.10]['ticker'].unique().tolist()
            
            # ==========================================
            # 🚨 THE SELF-HEALING PROTOCOL 🚨
            # ==========================================
            if corrupted_tickers and not is_intraday_mode:
                print(f"🚨 ANOMALY DETECTED: {len(corrupted_tickers)} stocks underwent Splits/Adjustments!")
                print(f"🩹 Triggering Self-Healing Protocol for: {corrupted_tickers}")
                
                # A. Vaporize the corrupted history from the Neon DB
                placeholders = ', '.join([f"'{t}'" for t in corrupted_tickers])
                with engine.begin() as conn:
                    conn.execute(text(f"DELETE FROM bronze_raw_ohlcv WHERE ticker IN ({placeholders}) AND timeframe = '1d';"))
                
                # B. Re-download 2 Full Years of history ONLY for the corrupted stocks
                print("📥 Downloading 2-Year Replacement History...")
                healing_data = yf.download(corrupted_tickers, period="2y", interval="1d", group_by='ticker', threads=True, progress=False, session=session)
                
                healing_df = pd.DataFrame()
                for ticker in corrupted_tickers:
                    if ticker in healing_data:
                        df = healing_data[ticker] if len(corrupted_tickers) > 1 else healing_data
                        df = df.dropna(how='all').reset_index()
                        df.columns = [col.lower() for col in df.columns]
                        if 'date' in df.columns: df = df.rename(columns={'date': 'datetime'})
                        df['ticker'], df['timeframe'] = ticker, '1d'
                        try:
                            df = df[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 'volume']]
                            healing_df = pd.concat([healing_df, df], ignore_index=True)
                        except: pass
                
                # C. Push the healed 2-year history directly into the database
                if not healing_df.empty:
                    healing_df.to_sql("bronze_raw_ohlcv", engine, if_exists="append", index=False)
                    print(f"✅ Vault Healed: Replaced history for {len(corrupted_tickers)} stocks.")
                
            # 4. Standard Delta Filter (Keep only rows newer than db_max_date)
            master_df = master_df.merge(db_memory[['ticker', 'timeframe', 'db_max_date']], on=['ticker', 'timeframe'], how='left')
            master_df = master_df[(master_df['datetime'] > master_df['db_max_date']) | (master_df['db_max_date'].isnull())]
            master_df = master_df.drop(columns=['db_max_date'])
            
    except Exception as e:
        print(f"⚠️ Self-Healing bypassed. Proceeding with standard delta. Error: {e}")

    # 5. Push the standard daily Delta
    if not master_df.empty:
        # Filter out the tickers we already healed so we don't insert duplicate rows today
        if 'corrupted_tickers' in locals() and corrupted_tickers:
            master_df = master_df[~master_df['ticker'].isin(corrupted_tickers)]
            
        print(f"💾 Pushing {len(master_df)} NEW Delta rows into the Bronze Vault...")
        if not master_df.empty:
            master_df.to_sql("bronze_raw_ohlcv", engine, if_exists="append", index=False)
        print("✅ Bronze Ingestion Complete!")
    else:
        print("✅ Vault is perfectly up to date. No new rows needed.")
else:
    print("⚠️ FATAL: No data was fetched across any timeframes.")
