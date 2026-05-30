import datetime
import os
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType
import yfinance as yf
import pandas as pd

def get_spark_session():
    """Initializes an S3A-compatible PySpark Session targeting Cloudflare R2 / Backblaze B2."""
    # We pull the AWS Hadoop package so Spark knows how to speak S3 API
    spark = SparkSession.builder \
        .appName("Nifty500_Bronze_Ingestion") \
        .config("spark.jars.packages", "org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262") \
        .config("spark.hadoop.fs.s3a.endpoint", os.getenv("STORAGE_ENDPOINT")) \
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("STORAGE_ACCESS_KEY")) \
        .config("spark.hadoop.fs.s3a.secret.key", os.getenv("STORAGE_SECRET_KEY")) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.sql.session.timeZone", "Asia/Kolkata") \
        .getOrCreate()
    return spark

def fetch_ticker_list():
    """Fetches the Nifty 500 tickers from NSE official source and appends Bees."""
    try:
        url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
        df_nifty = pd.read_csv(url)
        tickers = [f"{symbol}.NS" for symbol in df_nifty['Symbol'].tolist()]
    except Exception as e:
        print(f"Failed to fetch live Nifty 500 list, falling back to basic array. Error: {e}")
        tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS"] # Minimal fallback array
        
    # Append the Gold and Silver ETF instruments
    tickers.extend(["GOLDBEES.NS", "SILVERBEES.NS"])
    return sorted(list(set(tickers)))

def ingest_timeframe(spark, tickers, interval, period, s3_bucket_path):
    """Downloads data for all tickers and writes it to the designated Bronze path."""
    print(f"Starting ingestion for interval: {interval} over period: {period}")
    
    # Batch download using yfinance for speed optimization
    raw_data = yf.download(tickers=tickers, period=period, interval=interval, group_by='ticker', threads=True)
    
    parsed_records = []
    
    # Parse out the multi-index DataFrame returned by yfinance
    for ticker in tickers:
        if ticker not in raw_data.columns.levels[0]:
            continue
        ticker_df = raw_data[ticker].dropna(subset=['Close'])
        
        for timestamp, row in ticker_df.iterrows():
            parsed_records.append({
                "ticker": ticker,
                "timestamp": timestamp.to_pydatetime(),
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": float(row['Volume'])
            })
            
    if not parsed_records:
        print(f"No records parsed for interval {interval}. Skipping save.")
        return

    # Define strict schema for the Bronze table
    schema = StructType([
        StructField("ticker", StringType(), False),
        StructField("timestamp", TimestampType(), False),
        StructField("open", DoubleType(), True),
        StructField("high", DoubleType(), True),
        StructField("low", DoubleType(), True),
        StructField("close", DoubleType(), True),
        StructField("volume", DoubleType(), True)
    ])
    
    # Convert Python dictionary records to a Spark DataFrame
    spark_df = spark.createDataFrame(parsed_records, schema=schema)
    
    # Enforce Bronze standard metadata constraints (Ingestion timestamp + Source system)
    spark_df = spark_df.withColumn("ingested_at", F.current_timestamp()) \
                       .withColumn("source_system", F.lit("YahooFinance"))
                       
    # Write optimized, compressed parquet data straight to the free object storage bucket
    full_target_path = f"{s3_bucket_path}/interval={interval}"
    print(f"Writing data to path: {full_target_path}")
    spark_df.write.mode("overwrite").parquet(full_target_path)
    print(f"Successfully updated Bronze table for {interval} interval.")

if __name__ == "__main__":
    bucket_name = os.getenv("STORAGE_BUCKET_NAME")
    s3_base_path = f"s3a://{bucket_name}/bronze/market_data"
    
    spark_session = get_spark_session()
    ticker_list = fetch_ticker_list()
    
    print(f"Total assets queued for processing: {len(ticker_list)}")
    
    # 1. Daily Ingestion: Grab 2 years of daily history (500 trading days lookback for accurate NVI 255-EMA)
    ingest_timeframe(spark_session, ticker_list, interval="1d", period="2y", s3_bucket_path=s3_base_path)
    
    # 2. Intraday Ingestion: Grab max allowed lookback for 15m intervals (60 calendar days)
    ingest_timeframe(spark_session, ticker_list, interval="15m", period="60d", s3_bucket_path=s3_base_path)
    
    spark_session.stop()
    print("Bronze Ingestion Lifecycle Complete.")
