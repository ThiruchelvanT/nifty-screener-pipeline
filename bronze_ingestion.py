import os
import sys
import pandas as pd
from sqlalchemy import create_engine, text
import requests
import io
import time
from sqlalchemy.dialects.postgresql import insert
from fyers_apiv3 import fyersModel # ⬅️ ADDED FYERS SDK

# ==========================================
# 0. THE MODE SWITCH (Command Line Argument)
# ==========================================
is_intraday_mode = "--intraday" in sys.argv

if is_intraday_mode:
    print("⚡ INTRADAY MODE ACTIVATED: Featherweight 15m fetch.")
else:
    print("🏗️ MACRO MODE ACTIVATED: Heavy 1D historical fetch.")

# ==========================================
# 1. SETUP CREDENTIALS & FYERS SESSION
# ==========================================
db_password = os.getenv("NEON_PASSWORD")
if not db_password:
    raise ValueError("⚠️ CRITICAL: NEON_PASSWORD environment variable is missing!")

# Pull the Fyers Secrets from GitHub Environments
client_id = os.getenv("FYERS_CLIENT_ID")
access_token = os.getenv("FYERS_ACCESS_TOKEN")

if not client_id or not access_token:
    raise ValueError("⚠️ CRITICAL: Fyers API Credentials missing from environment!")

NEON_HOST = "ep-holy-star-amh8eg8r-pooler.c-5.us-east-1.aws.neon.tech"
db_url = f"postgresql://neondb_owner:{db_password}@{NEON_HOST}:5432/neondb?sslmode=require"
engine = create_engine(db_url)

# Initialize the Fyers Client
fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=access_token, log_path="")

# 🛡️ THE GRANDMASTER'S PATCH: Institutional UPSERT Logic
def postgres_upsert(table, conn, keys, data_iter):
    data = [dict(zip(keys, row)) for row in data_iter]
    insert_stmt = insert(table.table).values(data)
    do_nothing_stmt = insert_stmt.on_conflict_do_nothing(
        index_elements=['ticker', 'timeframe', 'datetime']
    )
    conn.execute(do_nothing_stmt)

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
    
    # FORMAT FOR FYERS: NSE:RELIANCE-EQ
    fyers_tickers = [f"NSE:{sym}-EQ" for sym in raw_tickers]
    
    # Add ETF exceptions (Fyers usually lists ETFs as -EQ as well, but we must map them)
    etf_list = ["SILVERBEES", "GOLDBEES"]
    fyers_tickers.extend([f"NSE:{sym}-EQ" for sym in etf_list])
    
    # Keep a mapping dictionary so we can save it back to the DB with the Yahoo style .NS format
    # This prevents your Silver/Gold tables from breaking.
    ticker_map = {f"NSE:{sym}-EQ": f"{sym}.NS" for sym in raw_tickers + etf_list}
    
    print(f"✅ Successfully loaded {len(fyers_tickers)} Fyers tickers.")
except Exception as e:
    print(f"⚠️ NSE Fetch failed: {e}. Defaulting to core list.")
    fyers_tickers = ["NSE:RELIANCE-EQ", "NSE:TCS-EQ", "NSE:HDFCBANK-EQ"]
    ticker_map = {t: t.replace("NSE:", "").replace("-EQ", ".NS") for t in fyers_tickers}

# ==========================================
# 3. FYERS API FETCHING (INSTITUTIONAL PIPELINE)
# ==========================================
print(f"🚀 Starting Bronze Ingestion for {len(fyers_tickers)} assets...")
master_df = pd.DataFrame()

def fetch_fyers_history(symbol, resolution, start_date, end_date):
    """Helper function to pull clean dataframe from Fyers API"""
    data = {
        "symbol": symbol,
        "resolution": str(resolution),
        "date_format": "1", # 1 means we provide dates as YYYY-MM-DD
        "range_from": start_date,
        "range_to": end_date,
        "cont_flag": "1"
    }
    
    response = fyers.history(data=data)
    
    if response['s'] == 'ok':
        df = pd.DataFrame(response['candles'], columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
        # Fyers returns epoch timestamps. Convert to IST datetime strings.
        df['datetime'] = pd.to_datetime(df['datetime'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
        return df
    else:
        print(f"⚠️ Failed to fetch {symbol}: {response['message']}")
        return pd.DataFrame()

# Set date ranges based on mode
import datetime
today = datetime.datetime.now().strftime("%Y-%m-%d")

if not is_intraday_mode:
    # --- 1D MACRO PULL (Last 60 Days) ---
    start_date = (datetime.datetime.now() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
    print(f"📥 Downloading Macro 1d timeframe ({start_date} to {today})...")
    
    for symbol in fyers_tickers:
        df = fetch_fyers_history(symbol, "D", start_date, today)
        if not df.empty:
            df['ticker'] = ticker_map[symbol]
            df['timeframe'] = '1d'
            master_df = pd.concat([master_df, df], ignore_index=True)
        time.sleep(0.1) # Respect API limits (Fyers allows ~10 req/sec)
else:
    # --- 15M INTRADAY PULL (Last 5 Days) ---
    start_date = (datetime.datetime.now() - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    print(f"📥 Downloading Intraday 15m timeframe ({start_date} to {today})...")
    
    for symbol in fyers_tickers:
        df = fetch_fyers_history(symbol, "15", start_date, today)
        if not df.empty:
            df['ticker'] = ticker_map[symbol]
            df['timeframe'] = '15m'
            master_df = pd.concat([master_df, df], ignore_index=True)
        time.sleep(0.1) # Respect API limits

# ==========================================
# 4. SELF-HEALING DELTA LOAD ARCHITECTURE
# ==========================================
if not master_df.empty:
    print(f"📊 Downloaded {len(master_df)} raw rows from Fyers. Initiating Database Memory Check...")
    
    try:
        memory_query = """
            SELECT DISTINCT ON (ticker, timeframe) 
                ticker, timeframe, datetime AS db_max_date, close AS db_close 
            FROM bronze_raw_ohlcv 
            ORDER BY ticker, timeframe, datetime DESC;
        """
        db_memory = pd.read_sql(memory_query, engine)
        
        if not db_memory.empty:
            master_df['datetime'] = pd.to_datetime(master_df['datetime'])
            db_memory['db_max_date'] = pd.to_datetime(db_memory['db_max_date'])
            
            # The Delta Filter: Keep only rows newer than db_max_date
            master_df = master_df.merge(db_memory[['ticker', 'timeframe', 'db_max_date']], on=['ticker', 'timeframe'], how='left')
            master_df = master_df[(master_df['datetime'] > master_df['db_max_date']) | (master_df['db_max_date'].isnull())]
            master_df = master_df.drop(columns=['db_max_date'])
            
    except Exception as e:
        print(f"⚠️ Memory check bypassed. Error: {e}")

    # 5. Push the standard daily Delta
    if not master_df.empty:
        print(f"💾 Pushing {len(master_df)} NEW Delta rows into the Bronze Vault...")
        master_df.to_sql(
            "bronze_raw_ohlcv", 
            engine, 
            if_exists="append", 
            index=False,
            method=postgres_upsert,
            chunksize=2000
        )
        print("✅ Bronze Ingestion Complete!")
    else:
        print("✅ Vault is perfectly up to date. No new rows needed.")
else:
    print("⚠️ FATAL: No data was fetched across any timeframes.")
