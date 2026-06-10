from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit
import pandas as pd
import pandas_ta as ta
import os
os.environ["PYSPARK_PYTHON"] = "/Users/thiruchelvansibi/opt/anaconda3/envs/oracle_env/bin/python"
os.environ["PYSPARK_DRIVER_PYTHON"] = "/Users/thiruchelvansibi/opt/anaconda3/envs/oracle_env/bin/python"


# 1. Initialize the Spark Cluster (Local Mode)
print("Igniting PySpark Engine...")
spark = SparkSession.builder \
    .appName("Nifty_Distributed_Indicator_Engine") \
    .config("spark.sql.execution.arrow.pyspark.enabled", "true") \
    .getOrCreate()

# Disable noisy Spark logs in the terminal
spark.sparkContext.setLogLevel("ERROR")

# 2. Define the Output Schema
indicator_schema = """
    Ticker string, 
    Datetime timestamp, 
    Timeframe string,
    Open double,
    High double,
    Low double,
    Close double,
    MACD_Black double, 
    MACD_Red double, 
    RSI_2 double, 
    RSI_14 double, 
    StochRSI_K double, 
    NVI_Black double, 
    NVI_Red double
"""

# 3. The Math Worker (Executes on Spark Nodes via Pandas UDF)
def calculate_all_indicators(pdf: pd.DataFrame) -> pd.DataFrame:
    # 1. THE DISTRIBUTED FIX: Force the worker to load the extension
    import pandas_ta as ta 
    
    # Lowered the threshold from 260 to 50 for the local test
    if len(pdf) < 50: 
        return pd.DataFrame()

    # Standardize column naming from tvDatafeed's lowercase to Title Case
    pdf = pdf.rename(columns={'close': 'Close', 'volume': 'Volume', 'open': 'Open', 'high': 'High', 'low': 'Low'})
    
    pdf = pdf.sort_values('Datetime').reset_index(drop=True)
    
    try:
        # MACD (12, 26, 9)
        macd = pdf.ta.macd(fast=12, slow=26, signal=9)
        pdf['MACD_Black'] = round(macd.iloc[:, 0], 2)
        pdf['MACD_Red'] = round(macd.iloc[:, 2], 2)

        # RSI (2) & RSI (14)
        pdf['RSI_2'] = round(pdf.ta.rsi(length=2), 2)
        pdf['RSI_14'] = round(pdf.ta.rsi(length=14), 2)

        # Stochastic RSI
        stoch = pdf.ta.stochrsi(length=14, rsi_length=14, k=3, d=3)
        pdf['StochRSI_K'] = round(stoch.iloc[:, 0], 2)

        # NVI (Negative Volume Index)
        nvi_vals = [100.0]
        for i in range(1, len(pdf)):
            if pdf['Volume'].iloc[i] < pdf['Volume'].iloc[i-1]:
                roc = (pdf['Close'].iloc[i] - pdf['Close'].iloc[i-1]) / pdf['Close'].iloc[i-1]
                nvi_vals.append(nvi_vals[-1] + (roc * nvi_vals[-1]))
            else:
                nvi_vals.append(nvi_vals[-1])
        
        pdf['NVI_Black'] = [round(val, 2) for val in nvi_vals]
        # Lowered the EMA from 255 to 20 for the local test
        pdf['NVI_Red'] = round(pdf.ta.ema(close=pd.Series(nvi_vals), length=20), 2)

        result_pdf = pdf[['Ticker', 'Datetime', 'Timeframe', 'Open', 'High', 'Low', 'Close', 
                  'MACD_Black', 'MACD_Red', 'RSI_2', 'RSI_14', 
                  'StochRSI_K', 'NVI_Black', 'NVI_Red']]
        
        return result_pdf.dropna()

    except Exception as e:
        print(f"🚨 UDF Math Error for {pdf['Ticker'].iloc[0]}: {e}")
        return pd.DataFrame()

# 4. The Data Pipeline
if __name__ == "__main__":
    try:
        print("Reading Parquet files from Data Lake...")
        # Read the raw files
        raw_15m_df = spark.read.parquet("./data_lake/raw_15m/*.parquet")
        raw_1h_df = spark.read.parquet("./data_lake/raw_1h/*.parquet")

        # Tag the timeframes
        df_15m_tagged = raw_15m_df.withColumn("Timeframe", lit("15m"))
        df_1h_tagged = raw_1h_df.withColumn("Timeframe", lit("1H"))

        # Union for a single distributed pass
        combined_raw_df = df_15m_tagged.unionByName(df_1h_tagged)

        print("Executing Distributed Math Engine...")
        # Group by Ticker and Timeframe, then execute the math
        calculated_df = combined_raw_df.groupBy("Ticker", "Timeframe") \
            .applyInPandas(calculate_all_indicators, schema=indicator_schema)

        # Show the latest 15 rows to verify the output
        print("\n--- STAGE 2 SUCCESS: CALCULATED INDICATORS ---")
        calculated_df.orderBy(col("Datetime").desc()).show(15, truncate=False)

    except Exception as e:
        print(f"Pipeline Failed: {e}")
    finally:
        spark.stop()