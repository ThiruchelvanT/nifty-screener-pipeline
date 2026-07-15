import os
import sys
import pandas as pd
from sqlalchemy import create_engine
import requests
import io
import time
import datetime
import pytz
from sqlalchemy.dialects.postgresql import insert
import yfinance as yf
from curl_cffi import requests as cffi_requests
from fyers_apiv3 import fyersModel 

# ==========================================
# 0. THE MODE SWITCH
# ==========================================
is_intraday_mode = "--intraday" in sys.argv

if is_intraday_mode:
    print("⚡ INTRADAY MODE ACTIVATED: Featherweight 15m fetch.")
else:
    print("🏗️ MACRO MODE ACTIVATED: Heavy 1D historical fetch.")

# ==========================================
# 1. SETUP CREDENTIALS & DB CONNECTION
# ==========================================
db_password = os.getenv("NEON_PASSWORD")
client_id = os.getenv("FYERS_CLIENT_ID")

if not db_password:
    raise ValueError("⚠️ CRITICAL: Missing DB Password in environment!")

NEON_HOST = "ep-holy-star-amh8eg8r-pooler.c-5.us-east-1.aws.neon.tech"
db_url = f"postgresql://neondb_owner:{db_password}@{NEON_HOST}:5432/neondb?sslmode=require"
engine = create_engine(db_url)

# ==========================================
# 2. INTELLIGENT ROUTER (FYERS VS YAHOO)
# ==========================================
import psycopg2
ist = pytz.timezone('Asia/Kolkata')
today_ist = datetime.datetime.now(ist).date()

USE_FYERS = False
access_token = None

try:
    conn = psycopg2.connect(
        host=NEON_HOST, port="5432", dbname="neondb",    
        user="neondb_owner", password=db_password
    )
    cursor = conn.cursor()
    
    # Check Streamlit Router Preference
    cursor.execute("SELECT key_value FROM system_config WHERE key_name = 'ACTIVE_DATA_SOURCE';")
    source_res = cursor.fetchone()
    active_source = source_res[0] if source_res else 'YAHOO'
    
    # Check Fyers Token freshness
    cursor.execute("SELECT key_value, last_updated FROM system_config WHERE key_name = 'FYERS_ACCESS_TOKEN';")
    token_res = cursor.fetchone()
    
    if active_source == 'FYERS' and token_res and token_res[0] not in ('INITIAL_BLANK_TOKEN', 'blank', None):
        last_updated = token_res[1]
        
        # Ensure timestamp has timezone so we can compare to today
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=pytz.utc)
            
        last_updated_ist = last_updated.astimezone(ist).date()
        
        if last_updated_ist == today_ist:
            access_token = token_res[0]
            USE_FYERS = True
            print("🟢 ROUTER: Streamlit preference is FYERS. Token is fresh. Initializing API...")
        else:
            print("⚠️ ROUTER: Streamlit preference is FYERS, but token is stale (not from today). Falling back to YAHOO.")
    else:
        print(f"🟡 ROUTER: Preference is {active_source}. Using YAHOO fallback.")
        
    conn.close()
except Exception as e:
    print(f"⚠️ DB Config Warning: {e}. Defaulting to YAHOO.")

# 🛡️ Institutional UPSERT Logic
def postgres_upsert(table, conn, keys, data_iter):
    data = [dict(zip(keys, row)) for row in data_iter]
    insert_stmt = insert(table.table).values(data)
    do_nothing_stmt = insert_stmt.on_conflict_do_nothing(
        index_elements=['ticker', 'timeframe', 'datetime']
    )
    conn.execute(do_nothing_stmt)

# ==========================================
# 3. DYNAMIC NIFTY 500 ASSET MAPPER
# ==========================================
print("🌐 Fetching live Nifty 500 list from NSE servers...")
url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
headers = {"User-Agent": "Mozilla/5.0"}

try:
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    nifty_df = pd.read_csv(io.StringIO(response.text))
    raw_tickers = nifty_df['Symbol'].tolist()
    
    # ETF Exceptions
    etf_list = ["SILVERBEES", "GOLDBEES", "NIFTYBEES", "BANKBEES", "ITBEES", "LIQUIDBEES"]
    raw_tickers.extend(etf_list)
    print(f"✅ Successfully loaded {len(raw_tickers)} assets.")
except Exception as e:
    print(f"⚠️ NSE Fetch failed: {e}. Defaulting to core list.")
    raw_tickers = ["RELIANCE", "TCS", "HDFCBANK", "SILVERBEES"]

master_df = pd.DataFrame()

# ==========================================
# 4A. FYERS INGESTION PROTOCOL
# ==========================================
if USE_FYERS:
    fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=access_token, log_path="")
    fyers_tickers = [f"NSE:{sym}-EQ" for sym in raw_tickers]
    ticker_map = {f"NSE:{sym}-EQ": f"{sym}.NS" for sym in raw_tickers}
    
    def fetch_fyers_history(symbol, resolution, start_date, end_date):
        data = {
            "symbol": symbol,
            "resolution": str(resolution),
            "date_format": "1", 
            "range_from": start_date,
            "range_to": end_date,
            "cont_flag": "1"
        }
        response = fyers.history(data=data)
        if response.get('s') == 'ok':
            # 🛡️ FYERS TIME FIX: Fyers gives us IST seconds natively. We just format it and stop.
            df = pd.DataFrame(response['candles'], columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['datetime'], unit='s')
            return df
        return pd.DataFrame()

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    if not is_intraday_mode:
        start_date = (datetime.datetime.now() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
        for symbol in fyers_tickers:
            df = fetch_fyers_history(symbol, "D", start_date, today_str)
            if not df.empty:
                df['ticker'] = ticker_map[symbol]
                df['timeframe'] = '1d'
                master_df = pd.concat([master_df, df], ignore_index=True)
            time.sleep(0.1)
    else:
        start_date = (datetime.datetime.now() - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
        for symbol in fyers_tickers:
            df = fetch_fyers_history(symbol, "15", start_date, today_str)
            if not df.empty:
                df['ticker'] = ticker_map[symbol]
                df['timeframe'] = '15m'
                master_df = pd.concat([master_df, df], ignore_index=True)
            time.sleep(0.1)

# ==========================================
# 4B. YAHOO INGESTION PROTOCOL (Ghost Session)
# ==========================================
else:
    ghost_session = cffi_requests.Session(impersonate="chrome")
    yahoo_tickers = [f"{sym}.NS" for sym in raw_tickers]
    
    print(f"📥 Using Yahoo Ghost Downloader for {len(yahoo_tickers)} assets...")
    
    if not is_intraday_mode:
        for symbol in yahoo_tickers:
            ticker = yf.Ticker(symbol, session=ghost_session)
            df = ticker.history(period="60d", interval="1d")
            
            if not df.empty:
                df = df.reset_index()
                date_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
                df.rename(columns={date_col: 'datetime', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
                
                # 🛡️ YAHOO TIME FIX: Yahoo gives us strict UTC. We convert to IST, then strip the tag.
                if df['datetime'].dt.tz is not None:
                    df['datetime'] = df['datetime'].dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
                    
                df['ticker'] = symbol
                df['timeframe'] = '1d'
                master_df = pd.concat([master_df, df[['ticker', 'timeframe', 'datetime', 'open', 'high', 'low', 'close', 'volume']]], ignore_index=True)
            time.sleep(0.5) 
    else:
        for symbol in yahoo_tickers:
            ticker = yf.Ticker(symbol, session=ghost_session)
            df = ticker.history(period="5d", interval="15m")
            
            if not df.empty:
                df = df.reset_index()
                date_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
                df.rename(columns={date_col: 'datetime', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
                
                # 🛡️ YAHOO TIME FIX: Yahoo gives us strict UTC. We convert to IST, then strip the tag.
                if df['datetime'].dt.tz is not None:
                    df['datetime'] = df['datetime'].dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
                    
                df['ticker'] = symbol
                df['timeframe'] = '15m'
                master_df = pd.concat([master_df, df[['ticker', 'timeframe', 'datetime', 'open', 'high', 'low', 'close', 'volume']]], ignore_index=True)
            time.sleep(0.5)

# ==========================================
# 5. SELF-HEALING DELTA LOAD ARCHITECTURE
# ==========================================
if not master_df.empty:
    print(f"📊 Downloaded {len(master_df)} raw rows. Initiating Database Memory Check...")
    
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
            
            master_df = master_df.merge(db_memory[['ticker', 'timeframe', 'db_max_date']], on=['ticker', 'timeframe'], how='left')
            master_df = master_df[(master_df['datetime'] > master_df['db_max_date']) | (master_df['db_max_date'].isnull())]
            master_df = master_df.drop(columns=['db_max_date'])
            
    except Exception as e:
        print(f"⚠️ Memory check bypassed. Error: {e}")

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
