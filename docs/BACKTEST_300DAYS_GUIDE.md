# 300-Day Backtest: XRP, DOGE, SOL - Quick Start Guide

## Overview

This guide will help you download 300 days of data for XRP, DOGE, and SOL, then backtest all your strategies to find the best performers.

---

## Prerequisites

### Option 1: Docker Desktop (Recommended)

1. **Start Docker Desktop**
   - Open Docker Desktop application
   - Wait for it to fully start (whale icon in system tray should be stable)

### Option 2: WSL Ubuntu

1. **Start WSL and install Freqtrade**

   ```bash
   wsl -d Ubuntu
   # Inside WSL:
   cd /mnt/c/Users/USER/Desktop/Algotrading
   # Follow Freqtrade installation if not already installed
   ```

---

## Quick Run (Automated)

### Using the Python Script

```powershell
# Make sure Docker Desktop is running first!
python scripts/backtesting/backtest_300days_xrp_doge_sol.py
```

This script will:

1. ✅ Download 300 days of data for XRP, DOGE, SOL (5m, 15m, 1h, 4h, 1d timeframes)
2. ✅ Backtest ALL 43 strategies on each pair
3. ✅ Generate a ranked list of best strategies
4. ✅ Save results to `user_data/backtest_300days_results.json`

**Estimated Time:** 2-4 hours (depending on your machine)

---

## Manual Step-by-Step

### Step 1: Download Data

```powershell
# Download XRP data
docker run --rm -v ${PWD}/user_data:/freqtrade/user_data freqtradeorg/freqtrade:stable download-data --config /freqtrade/user_data/config.json --pairs XRP/USDT:USDT --timeframes 5m 15m 1h 4h 1d --days 300 --exchange binance --trading-mode futures

# Download DOGE data
docker run --rm -v ${PWD}/user_data:/freqtrade/user_data freqtradeorg/freqtrade:stable download-data --config /freqtrade/user_data/config.json --pairs DOGE/USDT:USDT --timeframes 5m 15m 1h 4h 1d --days 300 --exchange binance --trading-mode futures

# Download SOL data
docker run --rm -v ${PWD}/user_data:/freqtrade/user_data freqtradeorg/freqtrade:stable download-data --config /freqtrade/user_data/config.json --pairs SOL/USDT:USDT --timeframes 5m 15m 1h 4h 1d --days 300 --exchange binance --trading-mode futures
```

### Step 2: Run Backtests

Example for one strategy:

```powershell
docker run --rm -v ${PWD}/user_data:/freqtrade/user_data freqtradeorg/freqtrade:stable backtesting --config /freqtrade/user_data/config.json --strategy AroonMACDStrategy --timerange 20250403-20260128 --pairs XRP/USDT:USDT DOGE/USDT:USDT SOL/USDT:USDT --timeframe 1h --export trades
```

Repeat for all 43 strategies.

### Step 3: Analyze Results

```powershell
python scripts/analysis/score_strategies.py
```

---

## Expected Output

The script will generate:

### Console Output

```
🏆 TOP STRATEGIES (by successful backtests):
Rank   Strategy                                 Success Rate   
────────────────────────────────────────────────────────────
1      AroonMACDStrategy                        3/3            
2      SupertrendEMAMomentumStrategy            3/3            
3      MeanReversionBBStrategy                  3/3            
...
```

### JSON Results File

Location: `user_data/backtest_300days_results.json`

Contains:

- Timerange tested
- Pairs tested
- Per-strategy, per-pair results
- Top 10 strategies ranked

---

## Troubleshooting

### Docker not running

```
Error: cannot connect to Docker daemon
```

**Solution:** Start Docker Desktop and wait for it to fully initialize

### Insufficient data

```
Error: Not enough data for backtesting
```

**Solution:** Ensure download completed successfully. Check `user_data/data/binance/futures/`

### Strategy import errors

```
Error: Could not import strategy
```

**Solution:** Check strategy file for syntax errors. Skip problematic strategies.

---

## Quick Commands Reference

```powershell
# Check if Docker is running
docker ps

# Check downloaded data
Get-ChildItem user_data/data/binance/futures/ -Recurse -Filter "*.json"

# View latest backtest results
Get-ChildItem user_data/backtest_results/ | Sort-Object LastWriteTime -Descending | Select-Object -First 5

# Run automated workflow
python scripts/backtesting/backtest_300days_xrp_doge_sol.py
```

---

## Next Steps After Completion

1. **Review Top Strategies**
   - Check `user_data/backtest_300days_results.json`
   - Focus on strategies with 3/3 success rate

2. **Deep Dive Analysis**

   ```powershell
   python scripts/analysis/analyze_trades.py
   ```

3. **Optimize Top Performers**
   - Run hyperopt on top 3-5 strategies
   - Fine-tune parameters

4. **Forward Test**
   - Deploy best strategy in paper trading mode
   - Monitor for 1-2 weeks before live trading

---

*Created: 2026-01-28*
*Timerange: Last 300 days (~10 months)*
