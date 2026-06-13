# 🏛️ Omni-Matrix Intraday Trading Architecture

This living documentation outlines the automated, event-driven data pipeline orchestrating market ingestion and trade signal calculation.

## 📡 System Topology Flow

```mermaid
graph TD
    %% Define System Styles
    classDef aws style fill:#FF9900,stroke:#333,stroke-width:2px,color:#fff;
    classDef github style fill:#24292e,stroke:#333,stroke-width:2px,color:#fff;
    classDef database style fill:#00E676,stroke:#333,stroke-width:2px,color:#000;

    subgraph AWS_Cloud [☁️ Amazon Web Services]
        EB1[⏰ Clock: Opening Strike<br/>03:46 UTC / 09:16 AM IST]:::aws
        EB2[⏱️ Clock: Sustained Pulse<br/>Every 15m / 04:00-09:59 UTC]:::aws
        Lambda[🦅 AWS Lambda Engine<br/>IntradaySniperEngine]:::aws
    end

    subgraph GitHub_Platform [🐙 GitHub Enterprise]
        Runner[⚡ Actions Runner<br/>intraday_feeder.yml]:::github
    end

    subgraph Storage_Fabric [🐘 Neon PostgreSQL]
        Bronze[(🥉 Bronze Layer<br/>bronze_raw_ohlcv)]:::database
        Gold[(🥇 Gold Ledger<br/>gold_signal_ledger)]:::database
    end

    %% Execution Sequences
    EB1 -->|1. HTTP POST: repository_dispatch| Runner
    EB2 -->|1. HTTP POST: repository_dispatch| Runner
    
    Runner -->|2. Execute Ingestion<br/>yfinance API Pull| Bronze
    Runner -->|3. Trigger Payload<br/>aws lambda invoke --type Event| Lambda
    
    Lambda -.->|4. Verify Freshness<br/>Timestamp Liveness Check| Bronze
    Lambda -->|5. Vector Math Calculations<br/>Log Target Positions| Gold

    %% Visual Layout Optimization
    style AWS_Cloud fill:#fff3e0,stroke:#ffb74d,stroke-width:1px;
    style GitHub_Platform fill:#eceff1,stroke:#b0bec5,stroke-width:1px;
    style Storage_Fabric fill:#e8f5e9,stroke:#a5d6a7,stroke-width:1px;
