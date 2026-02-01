# Algotrading System - Low Level Design (LLD) Architecture

## Overview

This document describes the clean, structured architecture of the Algotrading system after comprehensive cleanup and reorganization.

---

## Directory Structure

```
Algotrading/
├── .env                        # Environment variables (API keys, secrets)
├── .gitignore                  # Git ignore rules
├── strategy_requirements.json  # Strategy indicator requirements mapping
│
├── analysis_layer/             # 🔍 MARKET ANALYSIS & AI
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── adapters/           # LLM integrations
│       │   ├── __init__.py
│       │   └── llm.py
│       ├── domain/
│       │   └── regime/         # Market regime detection
│       │       ├── __init__.py
│       │       └── analyst.py
│       ├── market_quant.py     # Quantitative analysis
│       └── regime_analyzer.py  # Market regime analyzer
│
├── data_layer/                 # 📊 DATA INGESTION
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── market_data_ingestion.py
│       └── services/
│           ├── candle_aggregator.py
│           ├── history_loader.py
│           └── tick_consumer.py
│
├── decision_layer/             # 🧠 DECISION ENGINE
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── config.py
│       ├── decision_engine.py
│       ├── regime_detection.py
│       ├── scoring_analysis.py
│       └── scoring/
│           ├── run_scoring_demo.py
│           ├── scoring_engine.py
│           └── strategy_profile.py
│
├── execution_layer/            # ⚡ ORDER EXECUTION
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── check_config.py
│       ├── config.py
│       └── order_executor.py
│
├── signal_layer/               # 📶 SIGNAL GENERATION
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── config.py
│       └── signal_publisher.py
│
├── risk_layer/                 # 🛡️ RISK MANAGEMENT
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       └── position_sizer.py
│
├── monitoring/                 # 📢 ALERTS & NOTIFICATIONS
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── config.py
│       ├── telegram_alerts.py
│       └── alerts/
│           ├── __init__.py
│           └── send_results_to_telegram.py
│
├── shared/                     # 📦 SHARED UTILITIES
│   ├── config/
│   │   ├── settings.py
│   │   └── __init__.py
│   ├── logging/
│   │   └── setup_logger.py
│   └── utils/
│       └── helpers.py
│
├── scripts/                    # 🔧 OPERATIONAL SCRIPTS
│   ├── backtesting/            # Backtest execution scripts
│   │   ├── backtest_all_strategies.py
│   │   ├── chunked_backtest.py
│   │   ├── robust_backtest.py
│   │   ├── run_all_backtests.py
│   │   ├── run_backtest.py
│   │   └── run_solana_backtest.py
│   ├── analysis/               # Analysis & scanning scripts
│   │   ├── aggregate_recent_results.py
│   │   ├── analyze_regime_log.py
│   │   ├── analyze_strategy_requirements.py
│   │   ├── analyze_trades.py
│   │   ├── diagnostic_scan.py
│   │   ├── live_entry_checker.py
│   │   ├── proximity_scan.py
│   │   ├── scan_recent_entries.py
│   │   ├── score_strategies.py
│   │   └── summarize_momentum.py
│   ├── data/                   # Data download & validation
│   │   ├── check_data.py
│   │   ├── check_data_ranges.py
│   │   ├── download_required_data.py
│   │   └── get_market_trending.py
│   ├── monitoring/             # Reporting scripts
│   │   └── send_backtest_report.py
│   ├── run_backtest_task.ps1   # PowerShell backtest runner
│   ├── run_control_panel.ps1   # Control panel launcher
│   └── run_robust_backtest.ps1 # Robust backtest runner
│
├── infrastructure/             # 🐳 DOCKER & DEPLOYMENT
│   ├── docker-compose.yml
│   ├── docker-compose.download.yml
│   └── docker-compose.backtest.yml
│
├── docs/                       # 📖 DOCUMENTATION
│   ├── ARCHITECTURE_LLD.md     # This file
│   ├── BACKTEST_RESULTS_COMPARISON.md
│   ├── BACKTEST_RESULTS_FINAL.md
│   ├── DATA_DOWNLOAD_QUICK_REF.md
│   ├── INDICATOR_REQUIREMENTS.md
│   ├── SOLANA_10MONTH_RESULTS.md
│   └── WORKFLOW_GUIDE.md
│
└── user_data/                  # 📁 FREQTRADE USER DATA
    ├── config.json             # Main Freqtrade config
    ├── config_api.json         # API configuration
    ├── config_backtest.json    # Backtest configuration
    ├── config_coindcx.json     # CoinDCX exchange config
    ├── config_solana.json      # Solana backtest config
    ├── backtest_config.json    # Backtest params
    ├── best_strategies.json    # Top performing strategies
    ├── strategy_performance_db.json # Performance database
    ├── tradesv3.sqlite         # Trade history database
    │
    ├── strategies/             # 🎯 TRADING STRATEGIES (42 strategies)
    │   ├── AroonMACDStrategy.py
    │   ├── ADXOBVMomentumStrategy.py
    │   ├── (... and more)
    │   └── archive/            # Deprecated strategies
    │
    ├── backtest_results/       # Backtest output (kept last 20)
    ├── data/                   # Historical market data
    ├── logs/                   # Runtime logs
    ├── hyperopt_results/       # Hyperopt optimization results
    ├── hyperopts/              # Hyperopt configurations
    ├── freqaimodels/           # FreqAI models
    ├── notebooks/              # Jupyter notebooks
    └── plot/                   # Chart visualizations
```

---

## Operational Workflow

### 1. Data Flow

```
[Market Data APIs] 
        ↓
    data_layer/          (Ingest & aggregate candles)
        ↓
    analysis_layer/      (Detect market regime)
        ↓
    decision_layer/      (Score strategies, select signals)
        ↓
    signal_layer/        (Publish trade signals)
        ↓
    risk_layer/          (Position sizing, safety checks)
        ↓
    execution_layer/     (Place orders on exchange)
        ↓
    monitoring/          (Telegram alerts, logging)
```

### 2. Backtesting Workflow

```
scripts/data/download_required_data.py   → Download historical data
        ↓
scripts/backtesting/run_backtest.py      → Execute backtest via Docker
        ↓
scripts/analysis/score_strategies.py     → Score & rank results
        ↓
scripts/monitoring/send_backtest_report.py → Send to Telegram
```

### 3. Strategy Development Workflow

```
user_data/strategies/               → Create new strategy
        ↓
scripts/backtesting/backtest_all_strategies.py → Test strategy
        ↓
scripts/analysis/analyze_trades.py  → Analyze trade patterns
        ↓
decision_layer/scoring/             → Add to scoring engine
```

---

## Key Files & Responsibilities

| File/Folder | Purpose |
|------------|---------|
| `analysis_layer/src/regime_analyzer.py` | Detect Bull/Bear/Ranging market |
| `decision_layer/src/scoring_engine.py` | Score and rank strategies |
| `execution_layer/src/order_executor.py` | Execute trades on exchange |
| `scripts/backtesting/*.py` | Backtest execution utilities |
| `user_data/strategies/` | All trading strategy implementations |
| `infrastructure/docker-compose.yml` | Main Docker orchestration |

---

## Cleanup Summary

### Files Deleted

- ✅ `infrastructure/archive/` (Legacy files, old venv)
- ✅ `user_data/*.backup*` (Backup files)
- ✅ `user_data/*.lock` (Lock files)
- ✅ `user_data/*.log` (Old logs)
- ✅ `user_data/*.sqlite-*` (Temp DB files)
- ✅ `scripts/debug_*.py` (Debug scripts)
- ✅ `scripts/investigate_*.py` (Investigation scripts)
- ✅ `market_scan_pairs.txt` (Temp file)
- ✅ 501 old backtest results (kept last 20)
- ✅ 5 `__pycache__` directories

### Structure Improvements

- ✅ Scripts organized into `scripts/{backtesting,analysis,data,monitoring}/`
- ✅ PowerShell scripts moved to `scripts/`
- ✅ Clear layer separation (analysis, decision, execution, etc.)
- ✅ Documentation consolidated in `docs/`

---

## Quick Commands

```powershell
# Run a backtest
docker-compose -f infrastructure/docker-compose.backtest.yml up

# Download data
python scripts/data/download_required_data.py

# Score strategies
python scripts/analysis/score_strategies.py

# Send report to Telegram
python scripts/monitoring/send_backtest_report.py
```

---

*Last Updated: 2026-01-28*
