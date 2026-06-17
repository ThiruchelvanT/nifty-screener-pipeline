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
