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

macro_schema = "ticker string, datetime timestamp, timeframe string, close double, nvi_black double, nvi_red double, rsi_14 double, macd_black double, macd_red double"

def process_macro_partition(pdf):
    pdf = pdf.sort_values('datetime').reset_index(drop=True)
    pdf['close'] = pdf['close'].astype(float)
    pdf['volume'] = pdf['volume'].astype(float)
    close_series = pdf['close']
    
    # 1. Macro MACD
    ema12 = close_series.ewm(span=12, adjust=False).mean()
    ema26 = close_series.ewm(span=26, adjust=False).mean()
    pdf['macd_black'] = ema12 - ema26
    pdf['macd_red'] = pdf['macd_black'].ewm(span=9, adjust=False).mean()
    
    # 2. Macro RSI (14)
    delta = close_series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain_14 = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss_14 = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs_14 = np.where(avg_loss_14 != 0, avg_gain_14 / avg_loss_14, 0.0)
    pdf['rsi_14'] = np.where(avg_loss_14 != 0, 100 - (100 / (1 + rs_14)), 100.0)
    
    # 3. Institutional NVI (The Foundation)
    nvi = [1000.0]
    for i in range(1, len(pdf)):
        if pdf['volume'].iloc[i] < pdf['volume'].iloc[i-1]:
            pct_change = (pdf['close'].iloc[i] - pdf['close'].iloc[i-1]) / pdf['close'].iloc[i-1]
            nvi.append(nvi[-1] + (nvi[-1] * pct_change))
        else:
            nvi.append(nvi[-1])
            
    pdf['nvi_black'] = nvi
    pdf['nvi_red'] = pd.Series(nvi).ewm(span=255, adjust=False).mean()
    
    return pdf[['ticker', 'datetime', 'timeframe', 'close', 'nvi_black', 'nvi_red', 'rsi_14', 'macd_black', 'macd_red']]

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
