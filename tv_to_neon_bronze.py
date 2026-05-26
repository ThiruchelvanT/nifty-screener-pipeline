from tvDatafeed import TvDatafeed, Interval
from sqlalchemy import create_engine
import pandas as pd
import requests
import io
import time
import os

# 1. Initialize TradingView Connection
tv = TvDatafeed()

# 2. Neon DB Connection Configuration
# Ensure this is set to your actual database URL
NEON_DB_URL = "postgresql://neondb_owner:npg_Hz6ngXfB0yKJ@ep-holy-star-amh8eg8r-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
engine = create_engine(NEON_DB_URL)

# 3. Define Intervals
intervals = {
    "15m": Interval.in_15_minute,
    "1H": Interval.in_1_hour
}

# 4. Dynamically Fetch Nifty 500 Tickers from NSE
print("🌐 Fetching live Nifty 500 list from NSE servers...")
url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    nifty_df = pd.read_csv(io.StringIO(response.text))
    tickers = nifty_df['Symbol'].tolist()
    tickers.extend(["SILVERBEES", "GOLDBEES"])
    print(f"✅ Successfully loaded {len(tickers)} tickers including ETFs.")
except Exception as e:
    print(f"⚠️ Failed to fetch live tickers from NSE: {e}. Defaulting to sample list.")
    tickers = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]

# 5. Execution Loop
print(f"🚀 Starting Bronze Ingestion for {len(tickers)} assets...")
success_count = 0
fail_list = []

for index, ticker in enumerate(tickers, start=1):
    print(f"\n[{index}/{len(tickers)}] Processing {ticker}...")
    
    for tf_name, tv_interval in intervals.items():
        try:
            # Fetch raw data
            df = tv.get_hist(symbol=ticker, exchange="NSE", interval=tv_interval, n_bars=300)
            
            if df is None or df.empty:
                print(f"   ⚠️ No data for {ticker} ({tf_name}). Skipping.")
                fail_list.append(f"{ticker}_{tf_name}")
                continue
                
            df = df.reset_index()
            
            # Schema Mapping
            df = df.rename(columns={
                'symbol': 'ticker',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume'
            })
            
            # Format ticker and add columns
            df['ticker'] = f"{ticker}.NS"
            df['timeframe'] = tf_name
            
            final_df = df[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 'volume']]
            
            # Stream to Neon
            final_df.to_sql(
                name='bronze_raw_ohlcv',
                con=engine,
                if_exists='append',
                index=False,
                method='multi'
            )
            print(f"   ✅ Loaded {tf_name} ({len(final_df)} rows)")
            success_count += 1
            
            # Anti-Ban Throttling
            time.sleep(2)
            
        except Exception as e:
            print(f"   ❌ Failed {tf_name}: {e}")
            fail_list.append(f"{ticker}_{tf_name}")
            time.sleep(5) 

print("\n" + "="*40)
print(f"🏆 Bronze Ingestion Complete.")
print(f"📊 Total Successful Ingestions: {success_count}")
if fail_list:
    print(f"⚠️ Failed Ingestions ({len(fail_list)}): {fail_list}")
print("="*40)