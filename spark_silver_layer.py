import os
import pandas as pd
from pyspark.sql import SparkSession
import psycopg2

# 1. Initialize the Radar (Starts the stopwatch and logs starting network bytes)
from telemetry_radar import TelemetryRadar
radar = TelemetryRadar()

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
    "driver": "org.postgresql.Driver",
    "fetchsize": "10000"  # 🛡️ Network Armor: Forces streaming in chunks to protect RAM
}

print("🚀 Initializing Spark Session...")
spark = SparkSession.builder \
    .appName("NiftyScreenerSilverLayer") \
    .config("spark.jars", jar_path) \
    .config("spark.sql.execution.arrow.pyspark.enabled", "true") \
    .getOrCreate()

# ==========================================
# 2. FETCH BRONZE DATA (THE ASYMMETRIC DELTA FILTER)
# ==========================================
print("📥 Fetching Bronze Data (Resolution-Optimized Window)...")

# We fetch 400 days for Macro (1d), and 20 days for Intraday (15m)
delta_query = """(
    SELECT * FROM bronze_raw_ohlcv 
    WHERE timeframe = '1d' AND datetime >= CURRENT_DATE - INTERVAL '365 days'
    
    UNION ALL
    
    SELECT * FROM bronze_raw_ohlcv 
    WHERE timeframe = '15m' AND datetime >= CURRENT_DATE - INTERVAL '14 days'
) as recent_bronze"""

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
    stochrsi_d double,
    nvi_black double,
    nvi_red double
"""

def process_partition(pdf):
    """
    🧮 THE PURE-PANDAS PARITY ENGINE
    De-coupled from black-box libraries. High-speed vector operations optimized 
    for absolute alignment with institutional charting engines (TradingView/Zerodha).
    """
    import numpy as np
    import pandas as pd
    
    # 1. Ensure absolute historical chronological alignment
    pdf = pdf.sort_values('datetime').reset_index(drop=True)

    pdf['open'] = pdf['open'].astype(float)
    pdf['high'] = pdf['high'].astype(float)
    pdf['low'] = pdf['low'].astype(float)
    pdf['close'] = pdf['close'].astype(float)
    pdf['volume'] = pdf['volume'].astype(float)
    
    close_series = pdf['close']
    volume_series = pdf['volume']
    
    # ==============================================================
    # MODULE 1: PURE-PANDAS MACD (12, 26, 9)
    # ==============================================================
    # adjust=False enforces the strict standard recursive EMA calculation
    ema12 = close_series.ewm(span=12, adjust=False).mean()
    ema26 = close_series.ewm(span=26, adjust=False).mean()
    
    pdf['macd_black'] = ema12 - ema26
    pdf['macd_red'] = pdf['macd_black'].ewm(span=9, adjust=False).mean()
    
    # ==============================================================
    # MODULE 2: TRADINGVIEW PARITY RSI & STOCHASTIC RSI (14, 14, 3, 3)
    # ==============================================================
    delta = close_series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    
    # alpha=1/length calculates Wilder's Running Moving Average (RMA) perfectly
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    
    # Avoid division by zero if average loss flatlines
    rs = np.where(avg_loss != 0, avg_gain / avg_loss, 0.0)
    pdf['rsi_14'] = np.where(avg_loss != 0, 100 - (100 / (1 + rs)), 100.0)
    
    # Hyper-sensitive RSI(2) using the exact same RMA formulation
    avg_gain_2 = gain.ewm(alpha=1/2, min_periods=2, adjust=False).mean()
    avg_loss_2 = loss.ewm(alpha=1/2, min_periods=2, adjust=False).mean()
    rs_2 = np.where(avg_loss_2 != 0, avg_gain_2 / avg_loss_2, 0.0)
    pdf['rsi_2'] = np.where(avg_loss_2 != 0, 100 - (100 / (1 + rs_2)), 100.0)

    # Stochastic RSI Engine with strict min_periods thresholds
    min_rsi = pdf['rsi_14'].rolling(window=14, min_periods=14).min()
    max_rsi = pdf['rsi_14'].rolling(window=14, min_periods=14).max()
    range_rsi = max_rsi - min_rsi
    
    # Protect against flatline NaN outputs during circuit breaks or freezes
    raw_stoch = np.where(
        range_rsi != 0,
        ((pdf['rsi_14'] - min_rsi) / range_rsi) * 100,
        0.0
    )
    
    # Generate Dual-Line %K and %D tracking structures
    pdf['stochrsi_k'] = pd.Series(raw_stoch, index=pdf.index).rolling(window=3, min_periods=3).mean()
    pdf['stochrsi_d'] = pdf['stochrsi_k'].rolling(window=3, min_periods=3).mean()
    
    # ==============================================================
    # MODULE 3: INSTITUTIONAL NVI ENGINE & SIGNAL LINE
    # ==============================================================
    nvi_values = np.zeros(len(pdf))
    nvi_values[0] = 1000.0  # Seed value
    
    closes = close_series.values
    volumes = volume_series.values
    
    # Native iterative execution loop over partition timeline
    for i in range(1, len(pdf)):
        if volumes[i] < volumes[i-1]:
            # Volume decreased -> institutional tracking triggered
            price_return = (closes[i] - closes[i-1]) / closes[i-1]
            nvi_values[i] = nvi_values[i-1] + (price_return * nvi_values[i-1])
        else:
            # Volume increased or stayed steady -> maintain index flatline
            nvi_values[i] = nvi_values[i-1]
            
    pdf['nvi_black'] = nvi_values
    
    # Use ewm with adjust=False to achieve accurate Wilder/Standard EMA initialization
    if pdf['nvi_black'].notnull().any():
        pdf['nvi_red'] = pdf['nvi_black'].ewm(span=255, adjust=False).mean()
    else:
        pdf['nvi_red'] = None

    # Return matching the exact structured Spark SQL schema constraints
    return pdf[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 
                'macd_black', 'macd_red', 'rsi_2', 'rsi_14', 'stochrsi_k', 'stochrsi_d', 'nvi_black', 'nvi_red']]

# ==========================================
# 4. EXECUTE SILVER TRANSFORMATION
# ==========================================
print("⚙️ Calculating Technical Indicators for entire dataset...")
silver_df = df.groupBy("ticker", "timeframe").applyInPandas(process_partition, schema=silver_schema)

# ==========================================
# 5. WRITE TO NEON DB
# ==========================================
print("💾 Saving enriched data to Neon Database...")
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
    conn = psycopg2.connect(
        host=NEON_HOST, database="neondb", user="neondb_owner", password=db_password, port="5432"
    )
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute("REFRESH MATERIALIZED VIEW gold_screener_latest;")
    print("🏆 Gold Layer successfully refreshed! The pipeline is complete.")
except Exception as e:
    print(f"❌ Failed to refresh Gold Layer: {e}")
finally:
    if 'cursor' in locals(): cursor.close()
    if 'conn' in locals(): conn.close()


# Shut down the Radar and print the final report
radar.shutdown_and_report()
