# from pyspark.sql import SparkSession
# import pandas as pd
# import pandas_ta as ta
# import os

# # Initialize Spark with JDBC driver
# # Get the absolute path to your JAR file
# jar_path = os.path.abspath("jars/postgresql-42.7.4.jar")

# spark = SparkSession.builder \
#     .appName("NiftyScreenerSilverLayer") \
#     .config("spark.jars", jar_path) \
#     .getOrCreate()
# spark = SparkSession.builder \
#     .appName("NiftyScreenerSilverLayer") \
#     .config("spark.jars", "/path/to/postgresql-42.7.4.jar") \
#     .getOrCreate()

# jdbc_url = "jdbc:postgresql://YOUR_NEON_HOST:5432/neondb"
# properties = {"user": "neondb_owner", "password": "YOUR_PASSWORD", "driver": "org.postgresql.Driver"}

# # 1. Load Bronze Data
# df = spark.read.jdbc(url=jdbc_url, table="bronze_raw_ohlcv", properties=properties)

# # 2. Transformation Logic using mapInPandas for vectorization
# def process_partition(pdf_iterator):
#     for pdf in pdf_iterator:
#         # Sort for indicator consistency
#         pdf = pdf.sort_values('datetime')
        
#         # Calculate Indicators
#         macd = pdf.ta.macd(fast=12, slow=26, signal=9)
#         pdf['macd_black'] = macd['MACD_12_26_9']
#         pdf['macd_red'] = macd['MACDs_12_26_9']
        
#         pdf['rsi_2'] = pdf.ta.rsi(length=2)
#         pdf['rsi_14'] = pdf.ta.rsi(length=14)
        
#         # StochRSI
#         stoch = pdf.ta.stochrsi(length=14)
#         pdf['stochrsi_k'] = stoch['STOCHRSIk_14_14_3_3']
        
#         # NVI Logic: Normalized vs Daily Volume
#         # This will be computed based on your volume columns
#         pdf['nvi_black'] = pdf.ta.nvi()
        
#         yield pdf

# # 3. Apply transformation grouped by ticker and timeframe
# # This prevents math leakage between different stocks/timeframes
# silver_df = df.groupBy("ticker", "timeframe").applyInPandas(process_partition, schema=...) 

# # 4. Write back to Silver table
# silver_df.write.jdbc(url=jdbc_url, table="silver_technical_indicators", mode="append", properties=properties)






import os
import pandas as pd
import pandas_ta as ta
from pyspark.sql import SparkSession

# 1. Dynamic Path for the JDBC Driver
jar_path = os.path.join(os.getcwd(), "jars", "postgresql-42.7.11.jar")

# 2. Secure Credential Loading
# Make sure you run: export NEON_PASSWORD='your_real_password' before executing
db_password = os.getenv("NEON_PASSWORD")
if not db_password:
    raise ValueError("⚠️ NEON_PASSWORD environment variable is not set!")

# 3. REPLACE THIS with your actual Neon host from the dashboard
# Example: "ep-holy-star-amh8eg8r.us-east-1.aws.neon.tech"
NEON_HOST = "ep-holy-star-amh8eg8r-pooler.c-5.us-east-1.aws.neon.tech"

# Construct the JDBC URL
jdbc_url = f"jdbc:postgresql://{NEON_HOST}:5432/neondb?sslmode=require"
properties = {
    "user": "neondb_owner",
    "password": db_password,
    "driver": "org.postgresql.Driver"
}

# 4. Initialize Spark
print("🚀 Initializing Spark Session for Connection Test...")
spark = SparkSession.builder \
    .appName("SilverTransformationTest") \
    .config("spark.jars", jar_path) \
    .config("spark.sql.execution.arrow.pyspark.enabled", "true") \
    .getOrCreate()


print("📥 Fetching Bronze Data...")
df = spark.read.jdbc(url=jdbc_url, table="bronze_raw_ohlcv", properties=properties)

# We will limit the test to just 2 tickers to make the terminal output fast and clean
test_df = df.filter(df.ticker.isin("RELIANCE.NS", "HDFCBANK.NS"))

# 3. Define the Schema for the output
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
    nvi_black double
"""

# 4. Transformation Logic (Corrected for applyInPandas)
def process_partition(pdf):
    # 'pdf' is now a single Pandas DataFrame containing one ticker's timeframe data
    pdf = pdf.sort_values('datetime')
    
    # MACD
    macd = pdf.ta.macd(fast=12, slow=26, signal=9)
    if macd is not None:
        pdf['macd_black'] = macd['MACD_12_26_9']
        pdf['macd_red'] = macd['MACDs_12_26_9']
    else:
        pdf['macd_black'] = None
        pdf['macd_red'] = None
        
    # RSI
    pdf['rsi_2'] = pdf.ta.rsi(length=2)
    pdf['rsi_14'] = pdf.ta.rsi(length=14)
    
    # StochRSI
    stoch = pdf.ta.stochrsi(length=14)
    if stoch is not None:
        pdf['stochrsi_k'] = stoch['STOCHRSIk_14_14_3_3']
    else:
        pdf['stochrsi_k'] = None
        
    # NVI
    pdf['nvi_black'] = pdf.ta.nvi(close=pdf['close'], volume=pdf['volume'])
    
    # Return a standard Pandas DataFrame matching the exact schema
    return pdf[['ticker', 'datetime', 'timeframe', 'open', 'high', 'low', 'close', 
               'macd_black', 'macd_red', 'rsi_2', 'rsi_14', 'stochrsi_k', 'nvi_black']]

print("⚙️ Calculating Technical Indicators...")

# 5. Apply the math
silver_df = test_df.groupBy("ticker", "timeframe").applyInPandas(process_partition, schema=silver_schema)

# 6. View the Results
print("📊 Transformation Complete! Here is the enriched data:")
# Filter out nulls (which naturally occur at the start of moving averages) to see real numbers
silver_df.filter("macd_black IS NOT NULL").show(10, truncate=False)

spark.stop()