# 🏛️ Omni-Matrix Intraday Trading Architecture

This living documentation outlines the automated, event-driven data pipeline orchestrating market ingestion and trade signal calculation.

## 📡 System Topology Flow

```mermaid
graph TD
    %% Theme-Agnostic Styling (Works in Light & Dark Mode)
    classDef aws fill:#e68a00,stroke:#cc7a00,stroke-width:2px,color:#ffffff;
    classDef github fill:#424a53,stroke:#24292e,stroke-width:2px,color:#ffffff;
    classDef database fill:#00a859,stroke:#007a41,stroke-width:2px,color:#ffffff;

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

    %% Transparent Subgraph Styling for Dark Mode Compatibility
    style AWS_Cloud fill:transparent,stroke:#e68a00,stroke-width:2px,stroke-dasharray: 5 5;
    style GitHub_Platform fill:transparent,stroke:#768390,stroke-width:2px,stroke-dasharray: 5 5;
    style Storage_Fabric fill:transparent,stroke:#00a859,stroke-width:2px,stroke-dasharray: 5 5;

