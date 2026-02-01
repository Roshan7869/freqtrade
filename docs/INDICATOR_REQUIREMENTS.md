# Indicator Requirements Mapping

## Most Common Indicators (Optimization Priority)

### ta.ATR

 **Used by 18 strategies:**

- ALMA_MACDStrategy.py
- AroonMACDStrategy.py
- AwesomeMACDRSIStrategy.py
- DAVEY_01_EURO_NIGHT_ADAPTED.py
- DAVEY_02_EURO_DAY_ADAPTED.py
- DAVEY_03_WC_2005_DAILY.py
- Donchian_ADX_CHOPStrategy.py
- EdriExtremePointsStrategy.py
- LLM_Regime_Strategy.py
- MeanReversionBBStrategy.py
- QuantTactics_Supertrend_Strategy.py
- Stockbee_EP_Strategy.py
- TEMA_ADX_CMOStrategy.py
- UnifiedTrendStrategy.py
- VWAPDMIStrategy.py
- WhaleMomentumStrategy.py
- WilliamsRSI_MACDStrategy.py
- WMA_MACDStrategy.py

### ta.RSI

 **Used by 12 strategies:**

- AwesomeMACDRSIStrategy.py
- ChrisVerma_GapShort_Strategy.py
- DAVEY_02_EURO_DAY_ADAPTED.py
- DAVEY_03_WC_2005_DAILY.py
- EdriExtremePointsStrategy.py
- LLM_Regime_Strategy.py
- MarcoAcetoni_LiquidityTrap_Strategy.py
- MeanReversionBBStrategy.py
- MeanReversionSqueezeStrategy.py
- QuantTactics_DCA_RSI_Strategy.py
- UnifiedTrendStrategy.py
- WilliamsRSI_MACDStrategy.py

### qtpylib.crossed_above

 **Used by 11 strategies:**

- ALMA_MACDStrategy.py
- AroonMACDStrategy.py
- AwesomeMACDRSIStrategy.py
- Donchian_ADX_CHOPStrategy.py
- EdriExtremePointsStrategy.py
- LLM_Regime_Strategy.py
- TEMA_ADX_CMOStrategy.py
- VWAPDMIStrategy.py
- WhaleMomentumStrategy.py
- WilliamsRSI_MACDStrategy.py
- WMA_MACDStrategy.py

### qtpylib.crossed_below

 **Used by 11 strategies:**

- ALMA_MACDStrategy.py
- AroonMACDStrategy.py
- AwesomeMACDRSIStrategy.py
- Donchian_ADX_CHOPStrategy.py
- EdriExtremePointsStrategy.py
- LLM_Regime_Strategy.py
- TEMA_ADX_CMOStrategy.py
- VWAPDMIStrategy.py
- WhaleMomentumStrategy.py
- WilliamsRSI_MACDStrategy.py
- WMA_MACDStrategy.py

### ta.MACD

 **Used by 8 strategies:**

- ALMA_MACDStrategy.py
- AroonMACDStrategy.py
- AwesomeMACDRSIStrategy.py
- LLM_Regime_Strategy.py
- UnifiedTrendStrategy.py
- WhaleMomentumStrategy.py
- WilliamsRSI_MACDStrategy.py
- WMA_MACDStrategy.py

### ta.ADX

 **Used by 7 strategies:**

- Donchian_ADX_CHOPStrategy.py
- EdriExtremePointsStrategy.py
- LLM_Regime_Strategy.py
- MeanReversionBBStrategy.py
- TEMA_ADX_CMOStrategy.py
- UnifiedTrendStrategy.py
- VWAPDMIStrategy.py

### ta.EMA

 **Used by 6 strategies:**

- ChrisVerma_GapShort_Strategy.py
- Donchian_ADX_CHOPStrategy.py
- EdriExtremePointsStrategy.py
- LLM_Regime_Strategy.py
- MeanReversionSqueezeStrategy.py
- Stockbee_EP_Strategy.py

### qtpylib.bollinger_bands

 **Used by 4 strategies:**

- LLM_Regime_Strategy.py
- MeanReversionBBStrategy.py
- MeanReversionSqueezeStrategy.py
- UnifiedTrendStrategy.py

### ta.SMA

 **Used by 4 strategies:**

- ChrisVerma_GapShort_Strategy.py
- DAVEY_01_EURO_NIGHT_ADAPTED.py
- ForestKnight_VPE_Strategy.py
- Stockbee_EP_Strategy.py

### qtpylib.typical_price

 **Used by 3 strategies:**

- LLM_Regime_Strategy.py
- MeanReversionBBStrategy.py
- UnifiedTrendStrategy.py

### ta.AROON

 **Used by 3 strategies:**

- AroonMACDStrategy.py
- UnifiedTrendStrategy.py
- WhaleMomentumStrategy.py

### ta.MOM

 **Used by 2 strategies:**

- EdriExtremePointsStrategy.py
- QuantTactics_Supertrend_Strategy.py

### ta.TRANGE

 **Used by 2 strategies:**

- Donchian_ADX_CHOPStrategy.py
- QuantTactics_Supertrend_Strategy.py

### custom.choppiness

 **Used by 1 strategies:**

- QuantTactics_Supertrend_Strategy.py

### custom.supertrend

 **Used by 1 strategies:**

- QuantTactics_Supertrend_Strategy.py

## Strategy-Specific Indicators

- **custom.choppiness**: QuantTactics_Supertrend_Strategy.py
- **custom.supertrend**: QuantTactics_Supertrend_Strategy.py
- **qtpylib.awesome_oscillator**: AwesomeMACDRSIStrategy.py
- **qtpylib.rolling_vwap**: ForestKnight_VPE_Strategy.py
- **ta.AROONOSC**: UnifiedTrendStrategy.py
- **ta.CCI**: EdriExtremePointsStrategy.py
- **ta.CMO**: TEMA_ADX_CMOStrategy.py
- **ta.TEMA**: TEMA_ADX_CMOStrategy.py
- **ta.WILLR**: WilliamsRSI_MACDStrategy.py
- **ta.WMA**: WMA_MACDStrategy.py

## Hyperopt Parameters by Strategy

### ALMA_MACDStrategy.py

- alma_length (Int)
- atr_multiplier (Decimal)
- risk_reward (Decimal)

### AroonMACDStrategy.py

- aroon_period (Int)
- atr_multiplier (Decimal)
- risk_reward (Decimal)

### AwesomeMACDRSIStrategy.py

- rsi_period (Int)
- atr_multiplier (Decimal)
- risk_reward (Decimal)
- ao_fast (Int)
- ao_slow (Int)

### ChrisVerma_GapShort_Strategy.py

- ema_fast (Decimal)
- ema_slow (Decimal)

### Donchian_ADX_CHOPStrategy.py

- donchian_period (Int)
- adx_threshold (Int)
- chop_threshold (Decimal)
- chop_period (Int)
- atr_multiplier (Decimal)

### EdriExtremePointsStrategy.py

- cci_period (Int)
- mom_period (Int)
- rsi_period (Int)
- rsi_oversold (Int)
- rsi_overbought (Int)
- ema_period (Int)
- atr_sl_multiplier (Decimal)
- atr_tp_multiplier (Decimal)

### LLM_Regime_Strategy.py

- rsi_buy (Int)
- rsi_sell (Int)
- adx_threshold (Int)
- bb_period (Int)
- bb_std (Decimal)
- atr_multiplier (Decimal)
- risk_reward (Decimal)
- llm_weight (Decimal)

### MarcoAcetoni_LiquidityTrap_Strategy.py

- swing_lookback_1h (Int)
- sweep_tolerance_pct (Decimal)

### MeanReversionBBStrategy.py

- bb_period (Int)
- bb_std (Decimal)
- rsi_long_threshold (Int)
- rsi_short_threshold (Int)
- adx_1h_threshold (Int)
- adx_4h_threshold (Int)
- atr_multiplier (Decimal)

### QuantTactics_DCA_RSI_Strategy.py

- rsi_period (Int)
- rsi_threshold (Decimal)
- max_safety_orders (Int)
- price_deviation_pct (Decimal)
- safety_order_volume_scale (Decimal)
- safety_order_step_scale (Decimal)
- take_profit_pct (Decimal)

### QuantTactics_Supertrend_Strategy.py

- supertrend_length (Int)
- supertrend_multiplier (Decimal)
- chop_threshold (Decimal)

### TEMA_ADX_CMOStrategy.py

- adx_threshold (Int)
- cmo_period (Int)
- atr_multiplier (Decimal)
- risk_reward (Decimal)
- tema_short (Int)
- tema_medium (Int)
- tema_long (Int)

### UnifiedTrendStrategy.py

- aroon_period (Int)
- adx_threshold (Int)
- rsi_buy (Int)
- rsi_sell (Int)

### VWAPDMIStrategy.py

- vwap_window (Int)
- adx_threshold (Int)
- atr_multiplier (Decimal)
- risk_reward (Decimal)

### WMA_MACDStrategy.py

- wma_short (Int)
- wma_medium (Int)
- wma_long (Int)
- atr_multiplier (Decimal)
- risk_reward (Decimal)

### WhaleMomentumStrategy.py

- min_whale_confidence (Decimal)
- whale_signal_ttl (Int)
- aroon_period (Int)
- atr_multiplier (Decimal)
- risk_reward (Decimal)

### WilliamsRSI_MACDStrategy.py

- rsi_long_threshold (Int)
- rsi_short_threshold (Int)
- atr_multiplier (Decimal)
- risk_reward (Decimal)
- willr_long_pullback (Int)
- willr_short_pullback (Int)
- willr_long_recovery (Int)
- willr_short_recovery (Int)
