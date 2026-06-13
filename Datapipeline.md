graph TD
    %% Styling Definitions
    classDef aws style fill:#ff9900,stroke:#333,stroke-width:2px,color:#fff;
    classDef github style fill:#24292e,stroke:#333,stroke-width:2px,color:#fff;
    classDef neon style fill:#00e699,stroke:#333,stroke-width:2px,color:#000;

    subgraph AWS_Cloud [AWS Cloud Environment]
        EB[⏰ AWS EventBridge<br/>Master Clock Rules]:::aws
        Lambda[🦅 AWS Lambda Engine<br/>IntradaySniperEngine]:::aws
    end

    subgraph GitHub_Platform [GitHub Ecosystem]
        GA[⚡ GitHub Actions Runner<br/>Intraday Bronze Feeder]:::github
    end

    subgraph Neon_Platform [Neon Serverless Postgres]
        DB_Bronze[(🥉 Bronze Vault<br/>raw_ohlcv table)]:::neon
        DB_Gold[(🥇 Gold Ledger<br/>signal_ledger table)]:::neon
    end

    %% Architectural Flow Links
    EB -->|1. Authenticated API POST<br/>trigger-sniper event| GA
    GA -->|2. Executes Ingestion Script<br/>yfinance to Database| DB_Bronze
    GA -->|3. AWS CLI Remote Invoke<br/>--invocation-type Event| Lambda
    Lambda -.->|4. Liveness Check<br/>Verifies Data Freshness| DB_Bronze
    Lambda -->|5. Vectorized Indicator Math<br/>Logs Target Signals| DB_Gold
