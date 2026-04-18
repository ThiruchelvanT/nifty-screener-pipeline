import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
import requests
import io
from datetime import datetime
import os
import psycopg2
from psycopg2.extras import execute_values

def get_nifty_500_tickers():
    """Fetches the Nifty 500 ticker list safely and adds custom ETFs."""
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    # Spoofing a browser request to bypass NSE bot blocks
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() 
        df_list = pd.read_csv(io.StringIO(response.text))
        tickers = df_list['Symbol'].apply(lambda x: x + ".NS").tolist()
        print("Successfully fetched live Nifty 500 list from NSE.")
    except Exception as e:
        print(f"Error fetching live list: {e}. Using fallback.")
        tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"] # Fallback
        
    # Add your specific target ETFs
    for etf in ["SILVERBEES.NS", "GOLDBEES.NS"]:
        if etf not in tickers:
            tickers.append(etf)
    return tickers

def calculate_metrics(df, interval_prefix):
    """Calculates all indicators for a given dataframe with error handling."""
    if df is None or df.empty or len(df) < 260:
        return {}

    try:
        # Flatten yfinance MultiIndex if present (handles yfinance update behavior)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 1. MACD (12, 26, 9)
        macd = df.ta.macd(fast=12, slow=26, signal=9)
        
        # 2. RSI (2) and RSI (14)
        rsi2 = df.ta.rsi(length=2)
        rsi14 = df.ta.rsi(length=14)
        
        # 3. Stochastic RSI (14, 14, 3, 3)
        stoch = df.ta.stochrsi(length=14, rsi_length=14, k=3, d=3)
        
        # 4. NVI Logic (255 EMA)
        nvi_vals = [100.0]
        for i in range(1, len(df)):
            if df['Volume'].iloc[i] < df['Volume'].iloc[i-1]:
                roc = (df['Close'].iloc[i] - df['Close'].iloc[i-1]) / df['Close'].iloc[i-1]
                nvi_vals.append(nvi_vals[-1] + (roc * nvi_vals[-1]))
            else:
                nvi_vals.append(nvi_vals[-1])
        
        df['NVI_B'] = nvi_vals
        df['NVI_R'] = ta.ema(df['NVI_B'], length=255)

        # Extracting values safely
        return {
            f"{interval_prefix}_Price": round(df['Close'].iloc[-1], 2),
            f"{interval_prefix}_MACD_Black": round(macd.iloc[-1, 0], 2),
            f"{interval_prefix}_MACD_Red": round(macd.iloc[-1, 2], 2),
            f"{interval_prefix}_RSI_2": round(rsi2.iloc[-1], 2),
            f"{interval_prefix}_RSI_14": round(rsi14.iloc[-1], 2),
            f"{interval_prefix}_Stoch_K_Black": round(stoch.iloc[-1, 0], 2),
            f"{interval_prefix}_Stoch_D_Red": round(stoch.iloc[-1, 1], 2),
            f"{interval_prefix}_NVI_Black": round(df['NVI_B'].iloc[-1], 2),
            f"{interval_prefix}_NVI_Red": round(df['NVI_R'].iloc[-1], 2)
        }
    except Exception as e:
        # If a specific stock's data shape breaks the indicator calculation, catch it safely
        print(f"   [!] Indicator math failed for {interval_prefix}: {e}")
        return {}

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    tickers = get_nifty_500_tickers()
    print(f"\nScanning {len(tickers)} symbols. This will take some time due to rate limits...")

    results = []
    for i, ticker in enumerate(tickers):
        try:
            # 1. Download Data & immediately drop NaN values to prevent math errors
            d1_df = yf.download(ticker, period="3y", interval="1d", auto_adjust=True, progress=False).dropna()
            m15_df = yf.download(ticker, period="1mo", interval="15m", auto_adjust=True, progress=False).dropna()
            
            # 2. Calculate Indicators
            d1_metrics = calculate_metrics(d1_df, "1D")
            m15_metrics = calculate_metrics(m15_df, "15m")
            
            # 3. Combine and Append if both calculations were successful
            if d1_metrics and m15_metrics:
                combined = {"Ticker": ticker}
                combined.update(d1_metrics)
                combined.update(m15_metrics)
                results.append(combined)
                
            if (i + 1) % 25 == 0:
                print(f"Progress: {i + 1}/{len(tickers)} stocks processed...")

            # 4. Polite delay to prevent Yahoo Finance IP bans (HTTP 429)
            time.sleep(0.5) 

        except Exception as e:
            print(f"Skipping {ticker} due to error: {e}")

    # --- ENTERPRISE CLOUD INGESTION (Replacing CSV Export) ---
    if results:
        supabase_uri = os.environ.get("SUPABASE_URI")
        
        if not supabase_uri:
            print("\nFATAL ERROR: SUPABASE_URI environment variable not found. Check GitHub Secrets.")
            exit(1)

        try:
            print("\nConnecting to the Cloud Vault (Supabase)...")
            # 1. Establish Secure Connection
            conn = psycopg2.connect(supabase_uri)
            cursor = conn.cursor()

            # 2. Format data for Bulk Execution
            # Order must match the columns in the UPSERT query below
            data_tuples = [
                (
                    r['Ticker'], 
                    r.get('1D_Price', None), 
                    r.get('1D_Stoch_K_Black', None),
                    r.get('15m_MACD_Black', None),
                    r.get('15m_MACD_Red', None),
                    r.get('1D_NVI_Black', None),
                    r.get('1D_NVI_Red', None)
                ) 
                for r in results
            ]

            # 3. The Idempotent "Upsert" Query
            upsert_query = """
                INSERT INTO nifty_daily_signals 
                (ticker, price, stoch_k, macd_black, macd_red, nvi_black, nvi_red, trade_date)
                VALUES %s
                ON CONFLICT (ticker, trade_date) 
                DO UPDATE SET 
                    price = EXCLUDED.price,
                    stoch_k = EXCLUDED.stoch_k,
                    macd_black = EXCLUDED.macd_black,
                    macd_red = EXCLUDED.macd_red,
                    nvi_black = EXCLUDED.nvi_black,
                    nvi_red = EXCLUDED.nvi_red,
                    updated_at = CURRENT_TIMESTAMP;
            """
            
            # 4. Execute Bulk Transaction
            execute_values(cursor, upsert_query, data_tuples)
            conn.commit()
            
            print(f"SUCCESS: {len(data_tuples)} records transactionally committed to Supabase.")

        except Exception as e:
            print(f"\nDATABASE ERROR: {e}")
            if 'conn' in locals(): conn.rollback()
        finally:
            if 'cursor' in locals(): cursor.close()
            if 'conn' in locals(): conn.close()
            
    else:
        print("\nFAILURE: No data was successfully processed.")
