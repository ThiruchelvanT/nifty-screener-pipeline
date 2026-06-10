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
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() 
        df_list = pd.read_csv(io.StringIO(response.text))
        tickers = df_list['Symbol'].apply(lambda x: x + ".NS").tolist()
        print("Successfully fetched live Nifty 500 list from NSE.")
    except Exception as e:
        print(f"Error fetching live list: {e}. Using fallback.")
        tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"] 
        
    for etf in ["SILVERBEES.NS", "GOLDBEES.NS"]:
        if etf not in tickers:
            tickers.append(etf)
    return tickers

def validate_yesterday_signals(conn):
    """Checks the signal_audit table for yesterday's signals and marks them as Win/Loss."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ticker, entry_price, signal_type, signal_date 
        FROM signal_audit 
        WHERE exit_price IS NULL AND signal_date < CURRENT_DATE
    """)
    pending = cursor.fetchall()

    for ticker, entry_price, sig_type, sig_date in pending:
        data = yf.download(ticker, period="1d", interval="1m", progress=False)
        if not data.empty:
            if isinstance(data.columns, pd.MultiIndex): 
                data.columns = data.columns.get_level_values(0)
            
            current_price = float(data['Close'].iloc[-1])
            accurate = False
            if sig_type == 'BUY' and current_price > entry_price:
                accurate = True
            elif sig_type == 'SELL' and current_price < entry_price:
                accurate = True
            
            cursor.execute("""
                UPDATE signal_audit 
                SET exit_price = %s, is_accurate = %s 
                WHERE ticker = %s AND signal_date = %s
            """, (current_price, accurate, ticker, sig_date))
    conn.commit()
    cursor.close()

def log_todays_signals_to_audit(conn, full_results_df):
    """Filters the top 10 Buy/Sell signals from today's scan and logs them for tomorrow's audit."""
    cursor = conn.cursor()
    today = datetime.now().date()
    
    # Apply Math Logic to find the Elite signals
    buy_mask = (full_results_df['1D_Stoch_K_Black'] < 40) & \
               (full_results_df['15m_MACD_Black'] > full_results_df['15m_MACD_Red']) & \
               (full_results_df['1D_NVI_Black'] > full_results_df['1D_NVI_Red'])
    
    sell_mask = (full_results_df['1D_Stoch_K_Black'] > 75) & \
                (full_results_df['15m_MACD_Black'] < full_results_df['15m_MACD_Red']) & \
                (full_results_df['1D_NVI_Black'] < full_results_df['1D_NVI_Red'])

    top_buys = full_results_df[buy_mask].sort_values('1D_Stoch_K_Black').head(10)
    top_sells = full_results_df[sell_mask].sort_values('1D_Stoch_K_Black', ascending=False).head(10)

    for _, row in top_buys.iterrows():
        cursor.execute("INSERT INTO signal_audit (ticker, signal_date, signal_type, entry_price) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                       (row['Ticker'], today, 'BUY', float(row['1D_Price'])))
    for _, row in top_sells.iterrows():
        cursor.execute("INSERT INTO signal_audit (ticker, signal_date, signal_type, entry_price) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                       (row['Ticker'], today, 'SELL', float(row['1D_Price'])))
    conn.commit()
    cursor.close()

def calculate_metrics(df, interval_prefix):
    """Calculates all indicators for a given dataframe with error handling."""
    if df is None or df.empty or len(df) < 260: return {}
    try:
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)

        macd = df.ta.macd(fast=12, slow=26, signal=9)
        rsi2 = df.ta.rsi(length=2)
        rsi14 = df.ta.rsi(length=14)
        stoch = df.ta.stochrsi(length=14, rsi_length=14, k=3, d=3)
        
        nvi_vals = [100.0]
        for i in range(1, len(df)):
            if df['Volume'].iloc[i] < df['Volume'].iloc[i-1]:
                roc = (df['Close'].iloc[i] - df['Close'].iloc[i-1]) / df['Close'].iloc[i-1]
                nvi_vals.append(nvi_vals[-1] + (roc * nvi_vals[-1]))
            else:
                nvi_vals.append(nvi_vals[-1])
        
        df['NVI_B'] = nvi_vals
        df['NVI_R'] = ta.ema(df['NVI_B'], length=255)

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
        print(f"   [!] Indicator math failed for {interval_prefix}: {e}")
        return {}

if __name__ == "__main__":
    tickers = get_nifty_500_tickers()
    print(f"\nScanning {len(tickers)} symbols. This will take some time due to rate limits...")

    results = []
    for i, ticker in enumerate(tickers):
        try:
            d1_df = yf.download(ticker, period="3y", interval="1d", auto_adjust=True, progress=False).dropna()
            m15_df = yf.download(ticker, period="1mo", interval="15m", auto_adjust=True, progress=False).dropna()
            
            d1_metrics = calculate_metrics(d1_df, "1D")
            m15_metrics = calculate_metrics(m15_df, "15m")
            
            if d1_metrics and m15_metrics:
                combined = {"Ticker": ticker}
                combined.update(d1_metrics)
                combined.update(m15_metrics)
                results.append(combined)
                
            if (i + 1) % 25 == 0:
                print(f"Progress: {i + 1}/{len(tickers)} stocks processed...")

            time.sleep(0.5) 
        except Exception as e:
            pass

    # --- ENTERPRISE CLOUD INGESTION ---
    if results:
        neon_password = os.environ.get("NEON_PASSWORD")
        if not neon_password:
            print("\nFATAL ERROR: NEON_PASSWORD environment variable not found.")
            exit(1)

        try:
            print("\nConnecting to the Cloud Vault (Neon)...")
            # REMEMBER TO USE YOUR ACTUAL NEON HOST HERE
            conn = psycopg2.connect(
                host="ep-holy-star-amh8eg8r.c-5.us-east-1.aws.neon.tech", 
                port=5432,
                dbname="neondb",    
                user="neondb_owner", 
                password=neon_password,
                sslmode="require"
            )
            
            print("Step 1: Auditing yesterday's signals...")
            validate_yesterday_signals(conn)

            cursor = conn.cursor()
            today_str = datetime.now().strftime('%Y-%m-%d') 
            
            def clean_num(val):
                return float(val) if pd.notna(val) else None
            
            data_tuples = [
                (
                    r['Ticker'], clean_num(r.get('1D_Price')), clean_num(r.get('1D_Stoch_K_Black')),
                    clean_num(r.get('15m_MACD_Black')), clean_num(r.get('15m_MACD_Red')),
                    clean_num(r.get('1D_NVI_Black')), clean_num(r.get('1D_NVI_Red')), today_str 
                ) for r in results
            ]

            upsert_query = """
                INSERT INTO nifty_daily_signals 
                (ticker, price, stoch_k, macd_black, macd_red, nvi_black, nvi_red, trade_date)
                VALUES %s
                ON CONFLICT (ticker, trade_date) DO UPDATE SET 
                    price = EXCLUDED.price, stoch_k = EXCLUDED.stoch_k,
                    macd_black = EXCLUDED.macd_black, macd_red = EXCLUDED.macd_red,
                    nvi_black = EXCLUDED.nvi_black, nvi_red = EXCLUDED.nvi_red;
            """
            execute_values(cursor, upsert_query, data_tuples)
            conn.commit()
            print(f"SUCCESS: {len(data_tuples)} records committed to the Cloud Vault.")

            print("Step 2: Logging today's Elite signals for tomorrow's audit...")
            log_todays_signals_to_audit(conn, pd.DataFrame(results))
            
        except Exception as e:
            print(f"\nDATABASE ERROR: {e}")
            if 'conn' in locals(): conn.rollback()
        finally:
            if 'cursor' in locals(): cursor.close()
            if 'conn' in locals(): conn.close()
    else:
        print("\nFAILURE: No data was successfully processed.")
