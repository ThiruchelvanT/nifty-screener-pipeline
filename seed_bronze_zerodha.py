import os
import pandas as pd
from sqlalchemy import create_engine, text

# 1. ESTABLISH VAULT CONNECTION
print("🔌 Connecting to Neon Vault...")

# The Cloud-Native Authentication Logic
try:
    # If running locally via Streamlit
    import streamlit as st
    db_url = os.environ.get("DATABASE_URL") or st.secrets["DATABASE_URL"]
except ImportError:
    # If running on GitHub Actions (Streamlit does not exist here)
    db_url = os.environ.get("DATABASE_URL")

if not db_url:
    raise ValueError("CRITICAL: DATABASE_URL is missing! Check your GitHub Secrets.")

engine = create_engine(db_url)
target_ticker = 'ADANIPORTS.NS'

# 2. THE INGESTION ENGINE
def inject_zerodha_timeline(csv_filename, timeframe):
    print(f"\n========================================")
    print(f"🚀 INITIALIZING {timeframe.upper()} PIPELINE FOR {csv_filename}")
    print(f"========================================")
    
    try:
        df = pd.read_csv(csv_filename)
    except FileNotFoundError:
        print(f"⚠️ Could not find {csv_filename}. Skipping...")
        return

    # Strip indicators and rename to PySpark schema
    df = df[['date', 'Open', 'High', 'Low', 'Close', 'Volume']]
    df = df.rename(columns={
        'date': 'datetime',
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close',
        'Volume': 'volume'
    })

    # Add metadata
    df['datetime'] = pd.to_datetime(df['datetime'])
    df['ticker'] = target_ticker  
    df['timeframe'] = timeframe 
    df = df[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 'volume']]

    # Calculate the exact surgical cut point
    min_date = df['datetime'].min().strftime('%Y-%m-%d %H:%M:%S')

    # Execute the surgical swap
    try:
        with engine.begin() as connection:
            delete_query = text(f"""
                DELETE FROM bronze_raw_ohlcv 
                WHERE ticker = '{target_ticker}' 
                  AND timeframe = '{timeframe}'
                  AND datetime >= '{min_date}';
            """)
            result = connection.execute(delete_query)
            print(f"✂️  Purged {result.rowcount} corrupted Yahoo rows starting from {min_date}.")

            df.to_sql('bronze_raw_ohlcv', connection, if_exists='append', index=False, method='multi')
            print(f"✅ Injected {len(df)} pristine Zerodha rows into the {timeframe} timeline.")
            
    except Exception as e:
        print(f"❌ Operation failed for {timeframe}: {e}")

# ==========================================
# 3. EXECUTE THE DUAL INJECTION
# ==========================================
if __name__ == "__main__":
    inject_zerodha_timeline("adani_zerodha_15m.csv", "15m")
    inject_zerodha_timeline("adani_zerodha_1d.csv", "1d")
    print("\n🏆 BOTH TIMELINES SECURED. The Launchpad is ready.")
