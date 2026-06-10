from tvDatafeed import TvDatafeed, Interval
from sqlalchemy import create_engine
import pandas as pd
import requests
import io
import time

# 1. Initialize TradingView Connection
tv = TvDatafeed()

# 2. Neon DB Connection Configuration
# Replace with your actual Neon URL
NEON_DB_URL = "postgresql://neondb_owner:npg_Hz6ngXfB0yKJ@ep-holy-star-amh8eg8r-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
engine = create_engine(NEON_DB_URL)

# 3. Fetch Nifty 500 Tickers
print("🌐 Fetching live Nifty 500 list...")
url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
headers = {"User-Agent": "Mozilla/5.0"}
response = requests.get(url, headers=headers, timeout=10)
nifty_df = pd.read_csv(io.StringIO(response.text))
tickers = nifty_df['Symbol'].tolist()
tickers.extend(["SILVERBEES", "GOLDBEES"])

print(f"🚀 Starting 1D Ingestion for {len(tickers)} assets...")

for index, ticker in enumerate(tickers, start=1):
    print(f"[{index}/{len(tickers)}] Fetching 1D for {ticker}...")
    
    try:
        # Fetch 1D data
        df = tv.get_hist(symbol=ticker, exchange="NSE", interval=Interval.in_daily, n_bars=300)
        
        if df is None or df.empty:
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
        
        # Add metadata
        df['ticker'] = f"{ticker}.NS"
        df['timeframe'] = '1D'
        
        final_df = df[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 'volume']]
        
        # Stream to Neon
        final_df.to_sql(
            name='bronze_raw_ohlcv',
            con=engine,
            if_exists='append',
            index=False,
            method='multi'
        )
        
        time.sleep(2) # Throttle to prevent bans
        
    except Exception as e:
        print(f"   ❌ Failed 1D for {ticker}: {e}")

print("\n🏆 1D Bronze Ingestion Complete.")