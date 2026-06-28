# ⚖️ The Omni-Matrix: System Architecture & Logic Rules

Welcome to the central nervous system of the Omni-Matrix Medallion Architecture. This document serves as the absolute source of truth for the algorithmic trading pipeline, detailing data lineage, object-oriented structures, and execution logic.

---

## 🏗️ 1. Medallion Data Lineage (The Flow)

Data enters raw, is refined through vectorized mathematics, and is ultimately forged into execution signals.

```mermaid
flowchart LR
    subgraph External Sources
        YF(Yahoo Finance / Broker API)
    end

    subgraph Bronze Layer [Raw Data]
        BR[bronze_raw_ohlcv]
    end

    subgraph Silver Layer [Mathematical Brain]
        S_TECH[silver_technical_indicators]
        S_MACRO[silver_1d_macro]
    end

    subgraph Gold Layer [Execution & UI]
        G_LEDGER[gold_signal_ledger]
        G_SCREENER[(gold_screener_latest)]
    end

    subgraph Boundaries [User Interface]
        UI(Streamlit Oracle Dashboard)
    end

    YF -->|Raw Candles| BR
    BR -->|Lambda Vector Engine| S_TECH
    BR -->|PySpark EOD Healer| S_MACRO
    S_TECH -->|Omni-Matrix Handshake| G_LEDGER
    S_MACRO -->|Omni-Matrix Handshake| G_LEDGER
    S_MACRO -.->|Materialized View| G_SCREENER
    G_LEDGER --> UI
    G_SCREENER --> UI
```



```mermaid
classDiagram
    %% CONTROLLERS
    class IntradaySniperAWS {
        <<Controller>>
        +check_golden_window()
        +fetch_micro_batch()
        +process_vectorized_math()
        +execute_omni_handshake()
    }
    class EODHealerPySpark {
        <<Controller>>
        +fetch_macro_batch()
        +calculate_institutional_nvi()
        +refresh_materialized_views()
    }

    %% ENTITIES
    class BronzeRawOHLCV {
        <<Entity>>
        +String ticker
        +Timestamp datetime
        +Float open_high_low_close
        +Float volume
    }
    class SilverTechIndicators {
        <<Entity>>
        +Float macd_black_red
        +Float rsi_14
        +Float rsi_2
        +Float stochrsi_k_d
    }
    class Silver1DMacro {
        <<Entity>>
        +Float nvi_black_red
        +String smart_money_status
    }
    class GoldSignalLedger {
        <<Entity>>
        +String signal_type
        +Float entry_price
        +String verdict (PENDING/WIN/CLOSED)
        +Float pnl_percentage
    }

    %% BOUNDARY
    class TheOracleDashboard {
        <<Boundary>>
        +render_screener()
        +render_xray_sandbox()
        +calculate_true_win_rate()
    }

    %% RELATIONSHIPS
    IntradaySniperAWS --> BronzeRawOHLCV : Reads
    IntradaySniperAWS --> SilverTechIndicators : Writes
    IntradaySniperAWS --> GoldSignalLedger : Inserts/Updates
    EODHealerPySpark --> BronzeRawOHLCV : Reads
    EODHealerPySpark --> Silver1DMacro : Writes
    TheOracleDashboard --> GoldSignalLedger : Reads
    TheOracleDashboard --> Silver1DMacro : Reads

```


```mermaid
graph TD
    subgraph The Upgraded Omni-Matrix Engine
        START((15m Cycle Start)) --> MACRO_SHIELD
        
        %% THE NEW GLOBAL MACRO SHIELD
        MACRO_SHIELD{Global Macro Scan <br/> DXY & Crude} 
        MACRO_SHIELD -- High Toxicity --> PENALTY[-15 to -50 Pts]
        MACRO_SHIELD -- Stable --> SAFE[-0 Pts]
        
        PENALTY & SAFE --> M1
        PENALTY & SAFE --> M2
        START --> M3
        START --> M4

        %% PILLAR 1: MACRO BUY (RS Upgraded)
        M1[🟢 Macro Entry Gate]
        M1 --> M1A{1D NVI Bullish?} -- Yes --> M1P1(+30 Pts)
        M1 --> M1B{1D RSI 14 > 50?} -- Yes --> M1P2(+20 Pts)
        M1 --> M1C{1D MACD Bullish?} -- Yes --> M1P3(+20 Pts)
        M1 --> M1D{15m RS > 1D RS? <br/> Relative Strength} -- Yes --> M1P4(+30 Pts)
        M1P1 & M1P2 & M1P3 & M1P4 --> M1_SUM[Base Score]
        M1_SUM --> M1_TOT[Base Score MINUS <br/> Macro Penalty >= 75?]
        M1_TOT -- YES --> EXEC_BUY_1D(INSERT PENDING 1d)

        %% PILLAR 2: INTRADAY BUY (VWAP Upgraded)
        M2[⚡ Intraday Entry Gate]
        M2 --> M2A{1D NVI Bullish?} -- Yes --> M2P1(+10 Pts)
        M2 --> M2B{15m MACD Bullish?} -- Yes --> M2P2(+20 Pts)
        M2 --> M2C{15m RSI 14 > 45?} -- Yes --> M2P3(+20 Pts)
        M2 --> M2D{15m RSI 2 & Stoch < 10?} -- Yes --> M2P4(+20 Pts)
        M2 --> M2E{15m Close > VWAP? <br/> Inst. Gravity} -- Yes --> M2P5(+30 Pts)
        M2P1 & M2P2 & M2P3 & M2P4 & M2P5 --> M2_SUM[Base Score]
        M2_SUM --> M2_TOT[Base Score MINUS <br/> Macro Penalty >= 80?]
        M2_TOT -- YES --> EXEC_BUY_15(INSERT PENDING 15m)

        %% PILLAR 3: HARVEST (Unchanged)
        M3[💰 The Harvest Scythe]
        M3 --> M3A{1D RSI 14 >= 75?} -- Yes --> M3P1(+25 Pts)
        M3 --> M3B{1D RSI 2 >= 90?} -- Yes --> M3P2(+20 Pts)
        M3 --> M3C{15m RSI 2 & Stoch >= 90?} -- Yes --> M3P3(+30 Pts)
        M3 --> M3D{15m MACD Cracks?} -- Yes --> M3P4(+25 Pts)
        M3P1 & M3P2 & M3P3 & M3P4 --> M3_TOT[Total Score >= 80?]
        M3_TOT -- YES --> EXEC_SELL_HARV(UPDATE CLOSED)

        %% PILLAR 4: EVACUATION (VWAP Upgraded)
        M4[🚨 Evacuation Hatch]
        M4 --> M4A{1D NVI Bearish?} -- Yes --> M4P1(+40 Pts)
        M4 --> M4B{1D MACD Bearish?} -- Yes --> M4P2(+30 Pts)
        M4 --> M4C{15m Close < VWAP? <br/> Broken Support} -- Yes --> M4P3(+30 Pts)
        M4P1 & M4P2 & M4P3 --> M4_TOT[Total Score >= 75?]
        M4_TOT -- YES --> EXEC_SELL_EVAC(UPDATE CLOSED)
    end
    
    style EXEC_BUY_1D fill:#09ab3b,stroke:#fff,color:#fff
    style EXEC_BUY_15 fill:#09ab3b,stroke:#fff,color:#fff
    style EXEC_SELL_HARV fill:#ffd700,stroke:#000,color:#000
    style EXEC_SELL_EVAC fill:#ff4b4b,stroke:#fff,color:#fff
    style PENALTY fill:#ff4b4b,stroke:#fff,color:#fff
```
