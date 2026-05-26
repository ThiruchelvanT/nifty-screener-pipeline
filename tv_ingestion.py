from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import time
import os
import requests
import io

# 1. Initialize TradingView Connection
# IMPORTANT: Provide your TradingView Username and Password here.
# If you don't, it connects as a guest, which has severe rate limits.
USERNAME = 'tthiruchelvansibi' 
PASSWORD = 'ThiruJobHunt9787$'

print("Connecting to TradingView...")
try:
    tv = TvDatafeed(USERNAME, PASSWORD)
    print("Connection Successful.")
except Exception as e:
    print(f"Failed to connect: {e}")
    exit(1)

# 2. Get Nifty 500 Tickers (TradingView Format)
# def get_tv_tickers():
#     url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
#     headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
#     try:
#         response = requests.get(url, headers=headers, timeout=10)
#         df_list = pd.read_csv(io.StringIO(response.text))
#         # TradingView uses 'NSE' as the exchange prefix, not '.NS' suffix
#         tickers = df_list['Symbol'].tolist()
#     except Exception as e:
#         tickers = ["RELIANCE", "TCS", "HDFCBANK"]
    
#     for etf in ["SILVERBEES", "GOLDBEES"]:
#         if etf not in tickers: tickers.append(etf)
#     return tickers

def get_tv_tickers():
    # Temporarily bypassing the 500 list for local testing
    return ["RELIANCE", "TCS", "HDFCBANK"]

# 3. The Extraction Engine
def fetch_and_save_data(ticker, exchange='NSE'):
    try:
        # Pull 15-Minute Data (We need enough bars for a 255 EMA)
        # TradingView limits guest historical data, but logged-in users get more.
        # 15m bars: 1 day = ~25 bars. 2000 bars = ~80 trading days.
        df_15m = tv.get_hist(symbol=ticker, exchange=exchange, interval=Interval.in_15_minute, n_bars=2000)
        
        # Pull 1-Hour Data
        # 1H bars: 1 day = ~7 bars. 2000 bars = ~285 trading days.
        df_1h = tv.get_hist(symbol=ticker, exchange=exchange, interval=Interval.in_1_hour, n_bars=2000)

        if df_15m is not None and not df_15m.empty and df_1h is not None and not df_1h.empty:
            # Clean up index and formatting for PySpark
            df_15m = df_15m.reset_index().rename(columns={'datetime': 'Datetime'})
            df_1h = df_1h.reset_index().rename(columns={'datetime': 'Datetime'})
            
            # Add ticker column
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

# 4. Execution Loop
if __name__ == "__main__":
    # Create Data Lake Directories
    os.makedirs("./data_lake/raw_15m", exist_ok=True)
    os.makedirs("./data_lake/raw_1h", exist_ok=True)

    tickers = get_tv_tickers()
    print(f"Beginning extraction for {len(tickers)} symbols...")

    success_count = 0
    for i, ticker in enumerate(tickers):
        if fetch_and_save_data(ticker):
            success_count += 1
        
        # Politeness Delay: TradingView will ban you if you hammer their servers
        time.sleep(1.5) 
        
        if (i + 1) % 25 == 0:
            print(f"Progress: {i + 1}/{len(tickers)}... (Success: {success_count})")

    print(f"Data Lake population complete. Successfully downloaded {success_count} assets.")