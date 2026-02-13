---
description: Strategic Pipeline - Simplified backtesting and trading workflow
---

# Strategic Pipeline Workflow

This workflow provides a **simplified, sequential pipeline** for backtesting and trading that eliminates the need to create multiple configuration files.

## Quick Start

### Backtest with Default Settings (300 days, 6x leverage)

```powershell
cd c:\Users\USER\Desktop\Algotrading
.\scripts\Run-Trading.ps1 -Mode backtest
```

### Backtest with Custom Parameters

```powershell
# 7-day backtest with 9x leverage
.\scripts\Run-Trading.ps1 -Mode backtest -Days 7 -Leverage 9

# 300-day backtest with specific pairs
.\scripts\Run-Trading.ps1 -Mode backtest -Days 300 -Leverage 6 -Pairs "SOL/USDT:USDT,XRP/USDT:USDT,DOGE/USDT:USDT"

# Different strategy with 5x leverage
.\scripts\Run-Trading.ps1 -Mode backtest -Strategy VWAPDMIStrategy -Days 30 -Leverage 5
```

### Dry Run (Paper Trading)

```powershell
.\scripts\Run-Trading.ps1 -Mode dry-run -Leverage 6
```

### Live Trading (Real Money)

```powershell
.\scripts\Run-Trading.ps1 -Mode live -Leverage 3
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `-Mode` | Yes | - | `backtest`, `dry-run`, or `live` |
| `-Strategy` | No | `AroonMomentumEngine_Hybrid` | Strategy name (without .py) |
| `-Days` | No | `300` | Number of days to backtest |
| `-Leverage` | No | `6` | Leverage multiplier |
| `-StakeAmount` | No | `1000` | Initial capital in USDT |
| `-Pairs` | No | (from config) | Comma-separated pairs |

## How It Works

1. **Reads** `config_base.json` (the single source of truth)
2. **Applies** your runtime parameters (leverage, days, pairs)
3. **Generates** a temporary `config_runtime.json`
4. **Executes** Freqtrade with the runtime config
5. **Saves** results to `user_data/backtest_results/`

## Benefits

✅ **No more duplicate configs** - One base config, infinite variations  
✅ **No hallucinations** - Script always uses existing files  
✅ **Sequential workflow** - Clear, predictable execution  
✅ **Easy leverage changes** - Just change the `-Leverage` parameter  
✅ **Automatic timerange** - Calculates dates based on `-Days`  

## File Structure

```
Algotrading/
├── user_data/
│   ├── config_base.json          # ← Source of truth (DO NOT DELETE)
│   ├── config_runtime.json        # ← Auto-generated (temporary)
│   └── backtest_results/          # ← Results saved here
└── scripts/
    └── Run-Trading.ps1            # ← The strategic pipeline script
```

## Migration from Old Workflow

**OLD WAY (Error-Prone):**

```powershell
# Had to manually create/edit config files
# Led to config_aroon_300day_backtest.json, config_aroon_300day_backtest_9x.json, etc.
```

**NEW WAY (Simple):**

```powershell
# Just change parameters
.\scripts\Run-Trading.ps1 -Mode backtest -Leverage 9
```

## Troubleshooting

### "Base config not found"

- Ensure `user_data/config_base.json` exists
- Run from the project root directory

### "Strategy not found"

- Check that the strategy file exists in `user_data/strategies/`
- Use the exact class name (case-sensitive)

### Backtest shows no data

- Ensure you have downloaded data for the pairs
- Use `freqtrade download-data` first if needed
