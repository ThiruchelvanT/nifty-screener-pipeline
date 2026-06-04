import os
import pandas as pd
import numpy as np
from pyspark.sql import SparkSession
import psycopg2

print("🦅 Waking the Intraday Sniper Engine...")

db_password = os.getenv("NEON_PASSWORD")
NEON_HOST = "ep-holy-star-amh8eg8r-pooler.c-5.us-east-1.aws.neon.tech"
jdbc_url = f"jdbc:postgresql://{NEON_HOST}:5432/neondb?sslmode=require"
properties = {"user": "neondb_owner", "password": db_password, "driver": "org.postgresql.Driver", "fetchsize": "10000"}
jar_path = os.path.join(os.getcwd(), "jars", "postgresql-42.7.11.jar")

spark = SparkSession.builder \
    .appName("NiftyIntradaySniper") \
    .config("spark.jars", jar_path) \
    .config("spark.sql.execution.arrow.pyspark.enabled", "true") \
    .getOrCreate()

# ==========================================
# 1. FEATHERWEIGHT FETCH (Only 3 days of 15m)
# ==========================================
print("📥 Fetching micro-batch (2 MB payload)...")
query = "(SELECT * FROM bronze_raw_ohlcv WHERE timeframe = '15m' AND datetime >= CURRENT_DATE - INTERVAL '3 days') as micro_bronze"
df = spark.read.jdbc(url=jdbc_url, table=query, properties=properties)

silver_schema = "ticker string, datetime timestamp, timeframe string, close double, macd_black double, macd_red double, rsi_2 double, rsi_14 double, stochrsi_k double, stochrsi_d double"

def process_micro_partition(pdf):
    """
    🎯 THE SNIPER ENGINE (MICRO)
    Hyper-optimized for speed. Stripped of all loops. Pure vector momentum math.
    """
    import numpy as np
    import pandas as pd
    
    pdf = pdf.sort_values('datetime').reset_index(drop=True)
    pdf['close'] = pdf['close'].astype(float)
    
    close_series = pdf['close']
    
    # --- 1. FAST MACD ---
    ema12 = close_series.ewm(span=12, adjust=False).mean()
    ema26 = close_series.ewm(span=26, adjust=False).mean()
    pdf['macd_black'] = ema12 - ema26
    pdf['macd_red'] = pdf['macd_black'].ewm(span=9, adjust=False).mean()
    
    # --- 2. FAST RSI & STOCHASTIC RSI ---
    delta = close_series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    
    # Base RSI 14 (Required for StochRSI math)
    avg_gain_14 = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss_14 = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs_14 = np.where(avg_loss_14 != 0, avg_gain_14 / avg_loss_14, 0.0)
    pdf['rsi_14'] = np.where(avg_loss_14 != 0, 100 - (100 / (1 + rs_14)), 100.0)
    
    # Hyper-sensitive RSI 2
    avg_gain_2 = gain.ewm(alpha=1/2, min_periods=2, adjust=False).mean()
    avg_loss_2 = loss.ewm(alpha=1/2, min_periods=2, adjust=False).mean()
    rs_2 = np.where(avg_loss_2 != 0, avg_gain_2 / avg_loss_2, 0.0)
    pdf['rsi_2'] = np.where(avg_loss_2 != 0, 100 - (100 / (1 + rs_2)), 100.0)

    # Stochastic RSI K & D Lines
    min_rsi = pdf['rsi_14'].rolling(window=14, min_periods=14).min()
    max_rsi = pdf['rsi_14'].rolling(window=14, min_periods=14).max()
    range_rsi = max_rsi - min_rsi
    
    raw_stoch = np.where(range_rsi != 0, ((pdf['rsi_14'] - min_rsi) / range_rsi) * 100, 0.0)
    
    pdf['stochrsi_k'] = pd.Series(raw_stoch, index=pdf.index).rolling(window=3, min_periods=3).mean()
    pdf['stochrsi_d'] = pdf['stochrsi_k'].rolling(window=3, min_periods=3).mean()
    
    return pdf[['ticker', 'datetime', 'timeframe', 'close', 'macd_black', 'macd_red', 'rsi_2', 'rsi_14', 'stochrsi_k', 'stochrsi_d']]

# ==========================================
# 2. TRANSFORM & WRITE (To the Micro Table)
# ==========================================
print("⚙️ Calculating high-speed triggers...")
micro_df = df.groupBy("ticker").applyInPandas(process_micro_partition, schema=silver_schema)

write_props = properties.copy()
write_props["truncate"] = "true"

micro_df.write.jdbc(
    url=jdbc_url, 
    table="silver_15m_micro", 
    mode="overwrite", 
    properties=write_props
)
spark.stop()

# ==========================================
# 3. THE GRANDMASTER HANDSHAKE (Score & Capture)
# ==========================================
print("🤝 Executing Grandmaster Cross-Engine Join...")
try:
    conn = psycopg2.connect(host=NEON_HOST, database="neondb", user="neondb_owner", password=db_password, port="5432")
    conn.autocommit = True
    cursor = conn.cursor()

    scoring_query = """
        WITH latest_1d AS (
            SELECT ticker, nvi_black, nvi_red, rsi_14, macd_black, macd_red FROM (
                -- We pull the foundation from your nightly Healer script
                SELECT ticker, nvi_black, nvi_red, rsi_14, macd_black, macd_red, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY datetime DESC) as rn
                FROM silver_technical_indicators WHERE timeframe = '1d'
            ) d WHERE rn = 1
        ),
        latest_15m AS (
            SELECT ticker, close, rsi_2, stochrsi_k, macd_black, macd_red FROM (
                -- We pull the live trigger from the Sniper script
                SELECT ticker, close, rsi_2, stochrsi_k, macd_black, macd_red, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY datetime DESC) as rn
                FROM silver_15m_micro 
            ) m WHERE rn = 1
        )
        SELECT 
            m.ticker, m.close,
            CASE WHEN d.nvi_black > d.nvi_red THEN 35 ELSE 0 END AS score_nvi,
            CASE WHEN d.rsi_14 BETWEEN 30 AND 45 THEN 20 ELSE 0 END AS score_rsi_1d,
            CASE WHEN d.macd_black >= d.macd_red THEN 15 ELSE 0 END AS score_macd_1d,
            CASE WHEN m.rsi_2 < 5.0 AND m.stochrsi_k < 1.0 THEN 15 ELSE 0 END AS score_exhaust,
            CASE WHEN m.macd_black > m.macd_red AND m.macd_black < 0 THEN 15 ELSE 0 END AS score_trigger
        FROM latest_15m m
        JOIN latest_1d d ON m.ticker = d.ticker
    """
    
    cursor.execute(f"SELECT ticker, close, (score_nvi + score_rsi_1d + score_macd_1d + score_exhaust + score_trigger) as total_score FROM ({scoring_query}) sub WHERE (score_nvi + score_rsi_1d + score_macd_1d + score_exhaust + score_trigger) >= 70")
    snipers = cursor.fetchall()
    
    if snipers:
        print(f"🎯 INTRA-DAY LOCK: {len(snipers)} stocks crossed 70 points!")
        for s in snipers:
            cursor.execute(f"INSERT INTO gold_signal_ledger (ticker, signal_date, signal_type, entry_price, target_timeframe, verdict) VALUES ('{s[0]}', NOW(), 'GM_SCORE_{s[2]}', {s[1]}, '15m', 'PENDING') ON CONFLICT DO NOTHING;")
    else:
        print("🛡️ No 70+ scores detected. Cash mode active.")

except Exception as e:
    print(f"❌ Handshake failed: {e}")
