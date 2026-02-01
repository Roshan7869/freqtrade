# QUICK REFERENCE - Data & Backtesting

## Download All Data (One Command)

```bash
freqtrade download-data --timeframe 5m 30m 1h 2h 4h 1d --days 365
```

## Timeframe Quick Lookup

**1h strategies (15):** ALMA_MACD, AroonMACD, AwesomeMACD, DAVEY_02, Donchian_ADX, EdriExtreme, ForestKnight, LLM_Regime, MeanReversionBB, MeanReversionSqueeze, Supertrend, StrategyOrchestrator, TEMA_ADX, UnifiedTrend, VWAPDMI, WMA_MACD, WhaleMomentum, WilliamsRSI_MACD

**5m strategies (3):** ChrisVerma, LiquidityTrap, Stockbee_EP

**2h strategies (1):** DAVEY_01

**30m strategies (1):** DCA_RSI

**1d strategies (1):** DAVEY_03

## Backtesting Examples

```bash
# Most common (1h)
freqtrade backtesting --strategy ALMA_MACDStrategy --timeframe 1h

# 5-minute strategies
freqtrade backtesting --strategy Stockbee_EP_Strategy --timeframe 5m
freqtrade backtesting --strategy MarcoAcetoni_LiquidityTrap_Strategy --timeframe 5m

# Daily
freqtrade backtesting --strategy DAVEY_03_WC_2005_DAILY --timeframe 1d

# DCA
freqtrade backtesting --strategy QuantTactics_DCA_RSI_Strategy --timeframe 30m
```

## Update Data Daily

```bash
freqtrade download-data --timeframe 5m 30m 1h 2h 4h 1d --days 2
```
