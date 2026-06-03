import os
import pandas as pd
import pandas_ta as ta
from pyspark.sql import SparkSession
import psycopg2

# ==========================================
# 1. SETUP AND CREDENTIALS
# ==========================================
jar_path = os.path.join(os.getcwd(), "jars", "postgresql-42.7.11.jar")

db_password = os.getenv("NEON_PASSWORD")
if not db_password:
    raise ValueError("⚠️ NEON_PASSWORD environment variable is not set!")

NEON_HOST = "ep-holy-star-amh8eg8r-pooler.c-5.us-east-1.aws.neon.tech"

jdbc_url = f"jdbc:postgresql://{NEON_HOST}:5432/neondb?sslmode=require"
properties = {
    "user": "neondb_owner",
    "password": db_password,
    "driver": "org.postgresql.Driver"
}

print("🚀 Initializing Spark Session...")
spark = SparkSession.builder \
    .appName("NiftyScreenerSilverLayer") \
    .config("spark.jars", jar_path) \
    .config("spark.sql.execution.arrow.pyspark.enabled", "true") \
    .getOrCreate()

# ==========================================
# 2. FETCH BRONZE DATA (THE 400-DAY DELTA FILTER)
# ==========================================
print("📥 Fetching Bronze Data (Last 400 Days Only)...")
# The Architect's Hack: Pass a SQL subquery instead of the full table name
delta_query = "(SELECT * FROM bronze_raw_ohlcv WHERE datetime >= CURRENT_DATE - INTERVAL '400 days') as recent_bronze"

df = spark.read.jdbc(url=jdbc_url, table=delta_query, properties=properties)

# ==========================================
# 3. DEFINE SCHEMA AND LOGIC
# ==========================================
silver_schema = """
    ticker string, 
    datetime timestamp, 
    timeframe string, 
    open double, 
    high double, 
    low double, 
    close double, 
    macd_black double, 
    macd_red double, 
    rsi_2 double, 
    rsi_14 double, 
    stochrsi_k double, 
    nvi_black double,
    nvi_red double
"""

def process_partition(pdf):
    # 'pdf' is now a single Pandas DataFrame containing one ticker's timeframe data
    import pandas_ta as ta
    
    pdf = pdf.sort_values('datetime')

    pdf['open'] = pdf['open'].astype(float)
    pdf['high'] = pdf['high'].astype(float)
    pdf['low'] = pdf['low'].astype(float)
    pdf['close'] = pdf['close'].astype(float)
    pdf['volume'] = pdf['volume'].astype(float)
    
    # ---------------------------------------------------------
    # MACD (Standard EMA math is fine here)
    # ---------------------------------------------------------
    macd = pdf.ta.macd(fast=12, slow=26, signal=9)
    if macd is not None:
        pdf['macd_black'] = macd['MACD_12_26_9']
        pdf['macd_red'] = macd['MACDs_12_26_9']
    else:
        pdf['macd_black'] = None
        pdf['macd_red'] = None
        
    # ==============================================================
    # THE TRADINGVIEW PARITY ENGINE (Custom RSI & StochRSI Math)
    # ==============================================================
    # STEP 1: Calculate Wilder's Smoothing (RMA) for the base RSI(14)
    delta = pdf['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    # alpha=1/14 mathematically perfectly matches TradingView's RMA
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    pdf['rsi_14'] = 100 - (100 / (1 + rs))
    
    # STEP 2: The Hyper-Sensitive RSI(2) using the same exact RMA logic
    avg_gain_2 = gain.ewm(alpha=1/2, min_periods=2, adjust=False).mean()
    avg_loss_2 = loss.ewm(alpha=1/2, min_periods=2, adjust=False).mean()
    pdf['rsi_2'] = 100 - (100 / (1 + (avg_gain_2 / avg_loss_2)))

    # STEP 3: The TradingView Stochastic RSI (%K Line)
    # 3A. Find the 14-period rolling Min and Max of the RSI_14 we just calculated
    min_rsi = pdf['rsi_14'].rolling(window=14).min()
    max_rsi = pdf['rsi_14'].rolling(window=14).max()
    
    # 3B. Calculate the Raw Stochastic Value (0 to 100)
    raw_stoch_rsi = ((pdf['rsi_14'] - min_rsi) / (max_rsi - min_rsi)) * 100
    
    # 3C. THE FATAL FLAW FIXED: Apply the 3-period SMA Smoothing to get %K
    pdf['stochrsi_k'] = raw_stoch_rsi.rolling(window=3).mean()
    # ==============================================================
        
    # ---------------------------------------------------------
    # NVI (Negative Volume Index)
    # ---------------------------------------------------------
    pdf['nvi_black'] = pdf.ta.nvi(close=pdf['close'], volume=pdf['volume'])
    if pdf['nvi_black'] is not None:
        pdf['nvi_red'] = ta.ema(pdf['nvi_black'], length=255)
    else:
        pdf['nvi_red'] = None
    
    # Return a standard Pandas DataFrame matching the exact schema
    return pdf[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 
                'macd_black', 'macd_red', 'rsi_2', 'rsi_14', 'stochrsi_k', 'nvi_black', 'nvi_red']]

# ==========================================
# 4. EXECUTE SILVER TRANSFORMATION
# ==========================================
print("⚙️ Calculating Technical Indicators for entire dataset...")
# Apply the math to the FULL dataframe (df)
silver_df = df.groupBy("ticker", "timeframe").applyInPandas(process_partition, schema=silver_schema)

print("📊 Transformation Complete! Here is a sample:")
silver_df.filter("macd_black IS NOT NULL").show(10, truncate=False)

# ==========================================
# 5. WRITE TO NEON DB
# ==========================================
print("💾 Saving enriched data to Neon Database...")

# CRITICAL: Prevent Spark from dropping the table and destroying the Primary Key
write_properties = properties.copy()
write_properties["truncate"] = "true"

silver_df.write.jdbc(
    url=jdbc_url, 
    table="silver_technical_indicators", 
    mode="overwrite", 
    properties=write_properties
)
print("✅ Data successfully locked in the vault!")

spark.stop()

# ==========================================
# 6. THE GOLD LAYER AUTOMATION (Compute Pushdown)
# ==========================================
print("🔄 Triggering Gold Layer Materialized View Refresh...")

try:
    # Connect directly to Neon via psycopg2
    conn = psycopg2.connect(
        host=NEON_HOST,
        database="neondb",
        user="neondb_owner",
        password=db_password,
        port="5432"
    )
    conn.autocommit = True # Required for REFRESH commands
    cursor = conn.cursor()
    
    # Instruct the database engine to refresh the Gold view
    cursor.execute("REFRESH MATERIALIZED VIEW gold_screener_latest;")
    
    print("🏆 Gold Layer successfully refreshed! The pipeline is complete.")
    
except Exception as e:
    print(f"❌ Failed to refresh Gold Layer: {e}")
finally:
    if 'cursor' in locals():
        cursor.close()
    if 'conn' in locals():
        conn.close()

# ==========================================
# ⚖️ THE ORACLE'S FORWARD-TESTING LEDGER
# ==========================================
print("Initiating Forward-Testing Ledger Protocol...")

try:
    # THE FIX: Use the exact credentials already defined at the top of the script
    conn = psycopg2.connect(
        host=NEON_HOST,
        database="neondb",
        user="neondb_owner",
        password=db_password,
        port="5432"
    )
    conn.autocommit = True
    cursor = conn.cursor()

    # ------------------------------------------
    # PHASE 1: THE SETTLEMENT (Grade Yesterday's Trades)
    # ------------------------------------------
    cursor.execute("SELECT signal_id, ticker, entry_price FROM gold_signal_ledger WHERE verdict = 'PENDING';")
    pending_trades = cursor.fetchall()
    
    if pending_trades:
        print(f"Settling {len(pending_trades)} pending trades from previous session...")
        for trade in pending_trades:
            signal_id, ticker, entry_price = trade
            
            # Fetch today's closing price for this ticker
            cursor.execute(f"SELECT latest_close FROM gold_screener_latest WHERE ticker = '{ticker}';")
            result = cursor.fetchone()
            
            if result:
                settlement_price = float(result[0])
                entry_price = float(entry_price)
                pnl = round(((settlement_price - entry_price) / entry_price) * 100, 2)
                
                # A BULLISH signal wins if the price went up
                verdict = 'WIN' if pnl > 0 else 'LOSS'
                
                cursor.execute(f"""
                    UPDATE gold_signal_ledger 
                    SET settlement_date = NOW(), 
                        settlement_price = {settlement_price}, 
                        pnl_percentage = {pnl}, 
                        verdict = '{verdict}'
                    WHERE signal_id = {signal_id};
                """)
    else:
        print("No pending trades to settle.")

    # ------------------------------------------
    # PHASE 2: THE CAPTURE (Log Today's New Trades)
    # ------------------------------------------
    # We only want to capture stocks that are actually firing a BULLISH structural trend today
    cursor.execute("SELECT ticker, latest_close FROM gold_screener_latest WHERE trend_15m = 'BULLISH';")
    todays_bulls = cursor.fetchall()
    
    if todays_bulls:
        print(f"Capturing {len(todays_bulls)} new Elite Bulls for tomorrow's settlement...")
        for bull in todays_bulls:
            ticker, close_price = bull
            
            # Prevent duplicate inserts if the engine is run multiple times in one day
            cursor.execute(f"""
                SELECT COUNT(*) FROM gold_signal_ledger 
                WHERE ticker = '{ticker}' AND DATE(signal_date) = CURRENT_DATE AND verdict = 'PENDING';
            """)
            is_duplicate = cursor.fetchone()[0] > 0
            
            if not is_duplicate:
                cursor.execute(f"""
                    INSERT INTO gold_signal_ledger (ticker, signal_date, signal_type, entry_price, target_timeframe, verdict)
                    VALUES ('{ticker}', NOW(), 'BULLISH', {close_price}, '1d', 'PENDING');
                """)
    else:
        print("No Elite Bulls found today. The Council remains silent.")

    cursor.close()
    conn.close()
    print("Forward-Testing Ledger updated successfully.")

except Exception as e:
    print(f"CRITICAL ERROR in Ledger Protocol: {e}")
