import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
import os

# ==========================================
# 1. DATABASE CONNECTION
# ==========================================
db_password = os.getenv("NEON_PASSWORD")
if not db_password:
    raise ValueError("⚠️ NEON_PASSWORD environment variable is not set!")

NEON_HOST = "ep-holy-star-amh8eg8r-pooler.c-5.us-east-1.aws.neon.tech"

# SQLAlchemy connection string is highly optimized for Pandas operations
db_url = f"postgresql://neondb_owner:{db_password}@{NEON_HOST}:5432/neondb?sslmode=require"
engine = create_engine(db_url)

# ==========================================
# 2. DYNAMICALLY FETCH TICKERS FROM NEON DB
# ==========================================
print("🔍 Scanning Bronze vault for active tickers...")

try:
    # Query the database for every unique ticker it currently tracks
    query = "SELECT DISTINCT ticker FROM bronze_raw_ohlcv;"
    tickers_df = pd.read_sql(query, engine)
    
    # Convert the pandas column into a standard Python list
    tickers = tickers_df['ticker'].tolist()
    
    if not tickers:
        print("⚠️ No tickers found in the database. Aborting.")
        exit()
        
    print(f"🎯 Discovered {len(tickers)} unique tickers. Initiating Historical Backfill...")

except Exception as e:
    print(f"❌ Failed to fetch tickers from database: {e}")
    exit()

# ==========================================
# 3. FETCH AND FORMAT DATA
# ==========================================
final_dataframes = []

for ticker in tickers:
    print(f"📥 Downloading 2 years of history for {ticker}...")
    try:
        # Pull exactly 2 years of daily candles
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y", interval="1d")
        
        if df.empty:
            print(f"⚠️ No data found for {ticker}")
            continue
            
        # Reset index to get Date as a column
        df = df.reset_index()
        
        # Rename columns to match your exact Bronze schema
        df = df.rename(columns={
            "Date": "datetime",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })
        
        # Add the static tracking columns
        df['ticker'] = ticker
        df['timeframe'] = '1d' # Important: Lowercase '1d' for Gold Layer compatibility
        
        # Select only the required columns and drop Timezone info for Postgres compatibility
        df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)
        df = df[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 'volume']]
        
        final_dataframes.append(df)
        
    except Exception as e:
        print(f"❌ Error fetching {ticker}: {e}")

# ==========================================
# 4. LOAD TO BRONZE VAULT
# ==========================================
if final_dataframes:
    print("⚙️ Combining data...")
    master_df = pd.concat(final_dataframes, ignore_index=True)
    
    print(f"💾 Pushing {len(master_df)} historical rows to NeonDB Bronze Layer...")
    
    # Append this history alongside your existing daily data
    master_df.to_sql('bronze_raw_ohlcv', engine, if_exists='append', index=False)
    
    print("✅ Historical Backfill Complete! The vault is full.")
else:
    print("⚠️ No data was processed.")
