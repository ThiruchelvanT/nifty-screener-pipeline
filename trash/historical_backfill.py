import os
import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine
import requests
import io
import time

# ==========================================
# 1. SETUP CREDENTIALS
# ==========================================
db_password = os.getenv("NEON_PASSWORD")
NEON_HOST = "ep-holy-star-amh8eg8r-pooler.c-5.us-east-1.aws.neon.tech"
db_url = f"postgresql://neondb_owner:{db_password}@{NEON_HOST}:5432/neondb?sslmode=require"
engine = create_engine(db_url)

# ==========================================
# 2. FETCH NIFTY 500
# ==========================================
print("🌐 Fetching Nifty 500 list for the V2 Build...")
url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
headers = {"User-Agent": "Mozilla/5.0"}
try:
    response = requests.get(url, headers=headers, timeout=10)
    nifty_df = pd.read_csv(io.StringIO(response.text))
    tickers = [f"{sym}.NS" for sym in nifty_df['Symbol'].tolist()]
    tickers.extend(["SILVERBEES.NS", "GOLDBEES.NS"])
except:
    tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS"] 

# ==========================================
# 3. MASSIVE BATCH DOWNLOAD
# ==========================================
# ==========================================
# 3. MASSIVE BATCH DOWNLOAD (The Storage Diet)
# ==========================================
print(f"🚀 Initiating Great Reset for {len(tickers)} assets...")
master_df = pd.DataFrame()

# ⚠️ REDUCED 1h TO 365 DAYS TO SURVIVE THE 512 MB HARDWARE LIMIT
timeframes = {"1d": "2y", "1h": "365d", "15m": "60d"}

batch_size = 100
ticker_batches = [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]

for tf_name, period in timeframes.items():
    print(f"\n📥 Forcing Massive Pull: {tf_name} timeframe...")
    for i, batch in enumerate(ticker_batches):
        print(f"   Fetching Batch {i+1}/{len(ticker_batches)}...")
        try:
            data = yf.download(batch, period=period, interval=tf_name, group_by='ticker', threads=True, progress=False)
            for ticker in batch:
                if ticker in data:
                    df = data[ticker].dropna(how='all')
                    if not df.empty:
                        df = df.reset_index()
                        df.columns = [col.lower() for col in df.columns]
                        if 'datetime' not in df.columns: 
                            if 'date' in df.columns: df = df.rename(columns={'date': 'datetime'})
                        
                        df['ticker'] = ticker
                        df['timeframe'] = tf_name
                        try:
                            df = df[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 'volume']]
                            master_df = pd.concat([master_df, df], ignore_index=True)
                        except:
                            continue
            time.sleep(2) 
        except Exception as e:
            continue

# ==========================================
# 4. LOAD DIRECTLY TO PRODUCTION VAULT
# ==========================================
if not master_df.empty:
    print(f"💾 Pushing {len(master_df)} rows into the LIVE Bronze Vault...")
    # Writing straight to production since we truncated it
    master_df.to_sql("bronze_raw_ohlcv", engine, if_exists="replace", index=False)
    print("✅ Foundation Rebuilt Successfully!")
else:
    print("⚠️ FATAL ERROR.")
