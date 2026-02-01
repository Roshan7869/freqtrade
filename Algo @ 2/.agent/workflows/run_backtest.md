---
description: How to run backtests for strategies
---

# Run Backtest

This workflow explains how to run backtests using the RBI system or individual strategy runners.

## Option 1: RBI Parallel Backtesting (Recommended)

1. **Define Strategy**:
   Create or edit `ideas.txt` in `_engine/_data_storage/rbi_pp_multi/`.

   ```text
   Buy when RSI < 30 and sell when RSI > 70
   ```

2. **Run RBI Agent**:

   ```bash
   python MoondevRED/_engine/03_strategy_development/strategy_generators/rbi_agent_pp_multi.py
   ```

3. **View Results**:
   - Check `_engine/_data_storage/rbi_pp_multi/backtest_stats.csv` for summary stats.
   - Detailed logs and code are in `_engine/_data_storage/rbi_pp_multi/user_folders/`.

## Option 2: Single Strategy Backtest

1. **Locate Strategy**: Ensure your strategy is in `_engine/03_strategy_development/strategy_library/`.

2. **Run Backtester**:

   ```bash
   python MoondevRED/_engine/04_validation_testing/backtest_runners/backtest_runner.py
   ```

   (Note: You may need to specify the strategy name or edit the runner script to select your strategy).

## Option 3: Dashboard

1. **Start Dashboard**:

   ```bash
   cd MoondevRED/_engine/_data_storage/rbi_pp_multi
   python app.py
   ```

2. Open `http://localhost:8001` in your browser.
