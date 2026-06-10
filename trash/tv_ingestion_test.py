from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import os
import time

# 1. Initialize TradingView (Guest Mode for the test)
print("Connecting to TradingView...")
try:
    tv = TvDatafeed() # Running without credentials for a quick 3-stock test
    print("Connection Successful.")
except Exception as e:
    print(f"Failed to connect: {e}")
    exit(1)

# 2. The Micro-Batch Tickers
tickers = ["RELIANCE", "TCS", "HDFCBANK"]

# 3. The Extraction Engine
def fetch_and_save_data(ticker, exchange='NSE'):
    try:
        print(f"Fetching {ticker}...")
        # Pull 15-Minute and 1-Hour Data
        df_15m = tv.get_hist(symbol=ticker, exchange=exchange, interval=Interval.in_15_minute, n_bars=500)
        df_1h = tv.get_hist(symbol=ticker, exchange=exchange, interval=Interval.in_1_hour, n_bars=500)

        if df_15m is not None and not df_15m.empty and df_1h is not None and not df_1h.empty:
            df_15m = df_15m.reset_index().rename(columns={'datetime': 'Datetime'})
            df_1h = df_1h.reset_index().rename(columns={'datetime': 'Datetime'})
            
            df_15m['Ticker'] = f"{ticker}.NS" 
            df_1h['Ticker'] = f"{ticker}.NS"
            
            # Save to Parquet Data Lake
            df_15m.to_parquet(f"./data_lake/raw_15m/{ticker}_15m.parquet", index=False)
            df_1h.to_parquet(f"./data_lake/raw_1h/{ticker}_1h.parquet", index=False)
            return True
        return False
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return False

# 4. Execution
if __name__ == "__main__":
    os.makedirs("./data_lake/raw_15m", exist_ok=True)
    os.makedirs("./data_lake/raw_1h", exist_ok=True)

    success_count = 0
    for ticker in tickers:
        if fetch_and_save_data(ticker):
            success_count += 1
        time.sleep(1) 

    print(f"\nTest Complete. Successfully downloaded {success_count}/3 assets to the Data Lake.")