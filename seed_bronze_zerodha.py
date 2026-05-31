import os
import pandas as pd
from sqlalchemy import create_engine, text

# 1. ESTABLISH VAULT CONNECTION
print("🔌 Connecting to Neon Vault...")

try:
    import streamlit as st
    db_url = os.environ.get("DATABASE_URL") or st.secrets["DATABASE_URL"]
except ImportError:
    db_url = os.environ.get("DATABASE_URL")

if not db_url:
    raise ValueError("CRITICAL: DATABASE_URL is missing! Check your GitHub Secrets.")

engine = create_engine(db_url)
target_ticker = 'ADANIPORTS.NS'

# 2. THE DEFENSIVE INGESTION ENGINE
def inject_zerodha_timeline(csv_filename, timeframe):
    print(f"\n========================================")
    print(f"🚀 INITIALIZING {timeframe.upper()} PIPELINE FOR {csv_filename}")
    print(f"========================================")
    
    try:
        df = pd.read_csv(csv_filename)
    except FileNotFoundError:
        print(f"⚠️ Could not find '{csv_filename}'. Please ensure it is pushed to GitHub with exactly this name!")
        return

    # --- DEFENSIVE DATA CLEANING ---
    print("🧽 Scrubbing CSV headers for hidden spaces and case issues...")
    df.columns = df.columns.str.strip()
    df.columns = df.columns.str.lower()
    
    try:
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
    except KeyError as e:
        print(f"❌ CRITICAL ERROR: The CSV does not have the expected columns. Found: {list(df.columns)}")
        return

    df = df.rename(columns={'date': 'datetime'})

    # --- DEFENSIVE TIMEZONE PARSING ---
    # --- DEFENSIVE TIMEZONE PARSING & UTC CONVERSION ---
    print("🕒 Standardizing to UTC...")
    # 1. Chop off the messy GMT string if it exists
    df['datetime'] = df['datetime'].astype(str).apply(lambda x: x.split(' GMT')[0])
    
    # 2. Convert to Pandas Datetime
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # 3. THE TRANSLATOR: 
    # Tell pandas these raw times are Indian Standard Time
    df['datetime'] = df['datetime'].dt.tz_localize('Asia/Kolkata')
    # Convert them mathematically to UTC (e.g., 09:15 IST becomes 03:45 UTC)
    df['datetime'] = df['datetime'].dt.tz_convert('UTC')
    # Strip the timezone tag so Postgres accepts it as a standard naive timestamp
    df['datetime'] = df['datetime'].dt.tz_localize(None)
    # -------------------------------
    
    # Now pandas can safely parse it
    df['datetime'] = pd.to_datetime(df['datetime'])
    # -------------------------------

    df['ticker'] = target_ticker  
    df['timeframe'] = timeframe 
    df = df[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 'volume']]

    min_date = df['datetime'].min().strftime('%Y-%m-%d %H:%M:%S')

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
        print(f"❌ Database Operation failed for {timeframe}: {e}")

# ==========================================
# 3. EXECUTE THE DUAL INJECTION
# ==========================================
if __name__ == "__main__":
    inject_zerodha_timeline("adani_zerodha_15m.csv", "15m")
    inject_zerodha_timeline("adani_zerodha_1d.csv", "1d")
    print("\n🏆 BOTH TIMELINES SECURED. The Launchpad is ready.")
