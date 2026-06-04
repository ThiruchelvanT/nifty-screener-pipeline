import os
import pandas as pd
import numpy as np
from pyspark.sql import SparkSession
import psycopg2

print("🏗️ Waking the EOD Macro Healer Engine...")

db_password = os.getenv("NEON_PASSWORD")
NEON_HOST = "ep-holy-star-amh8eg8r-pooler.c-5.us-east-1.aws.neon.tech"
jdbc_url = f"jdbc:postgresql://{NEON_HOST}:5432/neondb?sslmode=require"
properties = {"user": "neondb_owner", "password": db_password, "driver": "org.postgresql.Driver", "fetchsize": "10000"}
jar_path = os.path.join(os.getcwd(), "jars", "postgresql-42.7.11.jar")

spark = SparkSession.builder \
    .appName("NiftyMacroHealer") \
    .config("spark.jars", jar_path) \
    .config("spark.sql.execution.arrow.pyspark.enabled", "true") \
    .getOrCreate()

# ==========================================
# 1. HEAVY FETCH (1 Year of 1D History)
# ==========================================
print("📥 Fetching macro-batch (1D timeframe)...")
query = "(SELECT * FROM bronze_raw_ohlcv WHERE timeframe = '1d') as macro_bronze"
df = spark.read.jdbc(url=jdbc_url, table=query, properties=properties)

macro_schema = "ticker string, datetime timestamp, timeframe string, close double, nvi_black double, nvi_red double, rsi_14 double, macd_black double, macd_red double, rsi_2 double, stochrsi_k double, stochrsi_d double"

def process_macro_partition(pdf):
    """
    🏗️ THE HEALER ENGINE (MACRO)
    Calculates heavy institutional footprints (NVI), daily macro-trends, 
    and hyper-sensitive daily exhaustion trackers (RSI 2, StochRSI).
    """
    import numpy as np
    import pandas as pd
    
    pdf = pdf.sort_values('datetime').reset_index(drop=True)
    pdf['close'] = pdf['close'].astype(float)
    pdf['volume'] = pdf['volume'].astype(float)
    
    close_series = pdf['close']
    volume_series = pdf['volume']
    
    # --- 1. MACRO MACD ---
    ema12 = close_series.ewm(span=12, adjust=False).mean()
    ema26 = close_series.ewm(span=26, adjust=False).mean()
    pdf['macd_black'] = ema12 - ema26
    pdf['macd_red'] = pdf['macd_black'].ewm(span=9, adjust=False).mean()
    
    # --- 2. RSI (14) & FAST RSI (2) ---
    delta = close_series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    
    # Base RSI 14
    avg_gain_14 = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss_14 = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs_14 = np.where(avg_loss_14 != 0, avg_gain_14 / avg_loss_14, 0.0)
    pdf['rsi_14'] = np.where(avg_loss_14 != 0, 100 - (100 / (1 + rs_14)), 100.0)
    
    # Hyper-sensitive RSI 2
    avg_gain_2 = gain.ewm(alpha=1/2, min_periods=2, adjust=False).mean()
    avg_loss_2 = loss.ewm(alpha=1/2, min_periods=2, adjust=False).mean()
    rs_2 = np.where(avg_loss_2 != 0, avg_gain_2 / avg_loss_2, 0.0)
    pdf['rsi_2'] = np.where(avg_loss_2 != 0, 100 - (100 / (1 + rs_2)), 100.0)

    # --- 3. STOCHASTIC RSI ---
    min_rsi = pdf['rsi_14'].rolling(window=14, min_periods=14).min()
    max_rsi = pdf['rsi_14'].rolling(window=14, min_periods=14).max()
    range_rsi = max_rsi - min_rsi
    
    raw_stoch = np.where(range_rsi != 0, ((pdf['rsi_14'] - min_rsi) / range_rsi) * 100, 0.0)
    
    pdf['stochrsi_k'] = pd.Series(raw_stoch, index=pdf.index).rolling(window=3, min_periods=3).mean()
    pdf['stochrsi_d'] = pdf['stochrsi_k'].rolling(window=3, min_periods=3).mean()
    
    # --- 4. HEAVY NVI LOOP (Institutional Tracking) ---
    nvi_values = np.zeros(len(pdf))
    nvi_values[0] = 1000.0 
    closes = close_series.values
    volumes = volume_series.values
    
    for i in range(1, len(pdf)):
        if volumes[i] < volumes[i-1]:
            price_return = (closes[i] - closes[i-1]) / closes[i-1]
            nvi_values[i] = nvi_values[i-1] + (price_return * nvi_values[i-1])
        else:
            nvi_values[i] = nvi_values[i-1]
            
    pdf['nvi_black'] = nvi_values
    if pdf['nvi_black'].notnull().any():
        pdf['nvi_red'] = pdf['nvi_black'].ewm(span=255, adjust=False).mean()
    else:
        pdf['nvi_red'] = None

    return pdf[['ticker', 'datetime', 'timeframe', 'close', 'nvi_black', 'nvi_red', 'rsi_14', 'macd_black', 'macd_red', 'rsi_2', 'stochrsi_k', 'stochrsi_d']]

# ==========================================
# 2. TRANSFORM & WRITE (To the Macro Table)
# ==========================================
print("⚙️ Calculating institutional footprints...")
macro_df = df.groupBy("ticker").applyInPandas(process_macro_partition, schema=macro_schema)

write_props = properties.copy()
write_props["truncate"] = "true"

macro_df.write.jdbc(
    url=jdbc_url, 
    table="silver_1d_macro", 
    mode="overwrite", 
    properties=write_props
)

print("✅ Concrete Poured. silver_1d_macro table successfully created and updated.")
spark.stop()
