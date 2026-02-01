import sys
import os
from pathlib import Path
from functools import reduce
import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from datetime import datetime
from typing import Optional, Union
import logging

# Freqtrade imports
from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    BooleanParameter,
    CategoricalParameter,
    stoploss_from_absolute,
    Trade,
)
import freqtrade.vendor.qtpylib.indicators as qtpylib

# Import Regime Detector
current_path = Path(__file__).resolve()
root_path = current_path.parents[2]
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

try:
    from decision_layer.src.regime_detection import RegimeDetector, MarketRegime
except ImportError:

    class MarketRegime:
        BULL_TREND = "TRENDING_BULL"
        BEAR_TREND = "TRENDING_BEAR"
        SIDEWAYS = "RANGING"

    class RegimeDetector:
        @staticmethod
        def calculate_regime_indicators(df):
            return df

        @staticmethod
        def identify_regime(row):
            return MarketRegime.SIDEWAYS


logger = logging.getLogger(__name__)


class StrategyOrchestratorStrategy(IStrategy):
    """
    Regime-Aware Strategy Orchestrator (Evergreen Edition).
    Dynamically switches between sub-strategies based on Market Regime.
    Modes:
    - Bull: Trend Follow Long (WMA)
    - Bear: Trend Follow Short (Inverse WMA)
    - Range: Mean Reversion (Aroon)
    - Panic: Cash Preservation (Force Exit)
    """

    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    stoploss = -0.99
    use_exit_signal = True  # Enable for Panic Exits
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    minimal_roi = {"0": 100}

    # Parameters
    bull_wma_short = IntParameter(10, 16, default=13, space="buy", optimize=False)
    bull_wma_medium = IntParameter(18, 24, default=21, space="buy", optimize=False)
    bull_wma_long = IntParameter(30, 38, default=34, space="buy", optimize=False)
    bull_atr_multiplier = DecimalParameter(
        1.0, 2.5, default=1.5, space="sell", optimize=False
    )
    bull_risk_reward = DecimalParameter(
        2.5, 3.5, default=3.0, space="sell", optimize=False
    )

    # Bear specific parameters (Reused WMA for symmetry, but distinct namespace if needed)
    # For simplicity in this version, we mirror the Bull WMA settings for the Bear Short

    range_aroon_period = IntParameter(10, 30, default=14, space="buy", optimize=False)
    range_atr_multiplier = DecimalParameter(
        1.0, 2.5, default=1.5, space="sell", optimize=False
    )
    range_risk_reward = DecimalParameter(
        1.5, 3.0, default=2.0, space="sell", optimize=False
    )

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        # Dynamic Leverage based on Regime Confidence
        # Bull/Bear Trend = High Confidence = 12x
        # Range = Medium Confidence = 6x
        if entry_tag in ["bull_wma"]:
            return 8.0
        return 5.0

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: Optional[float],
        max_stake: float,
        leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        return proposed_stake

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        # Double check Panic here to prevent entry during high volatility
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) > 0:
            current_regime = RegimeDetector.get_regime(dataframe, -1)
            if current_regime == MarketRegime.PANIC:
                return False

        logger.info(f"DEBUG: Trade Entry Confirmed! {pair} {side} {entry_tag}")
        return True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Indicators
        dataframe = RegimeDetector.calculate_regime_indicators(dataframe)

        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # Bull/Bear Common (WMA)
        dataframe["bull_wma_short"] = ta.WMA(
            dataframe, timeperiod=self.bull_wma_short.value
        )
        dataframe["bull_wma_medium"] = ta.WMA(
            dataframe, timeperiod=self.bull_wma_medium.value
        )
        dataframe["bull_wma_long"] = ta.WMA(
            dataframe, timeperiod=self.bull_wma_long.value
        )
        dataframe["volume_ma"] = dataframe["volume"].rolling(20).mean()

        # Range
        aroon_range = ta.AROON(dataframe, timeperiod=self.range_aroon_period.value)
        dataframe["range_aroonup"] = aroon_range["aroonup"]
        dataframe["range_aroondown"] = aroon_range["aroondown"]
        dataframe["range_aroon_osc"] = (
            dataframe["range_aroonup"] - dataframe["range_aroondown"]
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Regime Logic (Vectorized)
        # Note: We can't easily vectorize the 'RegimeDetector.identify_regime' logic perfectly
        # without rewriting it as pure pandas ops.
        # For backtesting speed, we replicate the logic here using vector ops.

        # 1. Panic Check (ATR > 2 * ATR_MA)
        is_panic = dataframe["atr"] > (dataframe["atr_ma"] * 2.0)

        # 2. Trend Checks
        is_strong = dataframe["adx"] > 20  # Relaxed from 25
        is_bull = dataframe["close"] > dataframe["sma_200"]

        # Masks
        mask_panic = is_panic
        mask_bull = (~is_panic) & is_strong & is_bull
        mask_bear = (~is_panic) & is_strong & (~is_bull)
        mask_range = (~is_panic) & (~is_strong)

        # --- BULL STRATEGY (Long) ---
        bull_cross = qtpylib.crossed_above(
            dataframe["bull_wma_short"], dataframe["bull_wma_long"]
        )
        bull_alignment = (
            dataframe["bull_wma_short"] > dataframe["bull_wma_medium"]
        ) & (dataframe["bull_wma_medium"] > dataframe["bull_wma_long"])

        bull_entry = (
            mask_bull
            & (bull_cross | bull_alignment)
            & (dataframe["macd"] > dataframe["macdsignal"])
        )
        dataframe.loc[bull_entry, "enter_long"] = 1
        dataframe.loc[bull_entry, "enter_tag"] = "bull_wma"

        # --- BEAR STRATEGY (Short) ---
        # Inverse WMA Logic
        bear_cross = qtpylib.crossed_below(
            dataframe["bull_wma_short"], dataframe["bull_wma_long"]
        )
        bear_alignment = (
            dataframe["bull_wma_short"] < dataframe["bull_wma_medium"]
        ) & (dataframe["bull_wma_medium"] < dataframe["bull_wma_long"])

        bear_entry = (
            mask_bear
            & (bear_cross | bear_alignment)
            & (dataframe["macd"] < dataframe["macdsignal"])
        )
        dataframe.loc[bear_entry, "enter_short"] = 1
        dataframe.loc[bear_entry, "enter_tag"] = "bear_wma_short"

        # --- RANGE STRATEGY (Bi-directional) ---
        range_cross_long = qtpylib.crossed_above(
            dataframe["range_aroonup"], dataframe["range_aroondown"]
        )
        range_entry_long = (
            mask_range & range_cross_long & (dataframe["range_aroon_osc"] > 0)
        )
        dataframe.loc[range_entry_long, "enter_long"] = 1
        dataframe.loc[range_entry_long, "enter_tag"] = "range_aroon"

        range_cross_short = qtpylib.crossed_below(
            dataframe["range_aroonup"], dataframe["range_aroondown"]
        )
        range_entry_short = (
            mask_range & range_cross_short & (dataframe["range_aroon_osc"] < 0)
        )
        dataframe.loc[range_entry_short, "enter_short"] = 1
        dataframe.loc[range_entry_short, "enter_tag"] = "range_aroon_short"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Panic Exit Logic
        # If Panic condition is met, signal exit for all.
        is_panic = dataframe["atr"] > (dataframe["atr_ma"] * 2.0)

        dataframe.loc[is_panic, "exit_long"] = 1
        dataframe.loc[is_panic, "exit_short"] = 1
        dataframe.loc[is_panic, "exit_tag"] = "panic_sell"

        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        tag = trade.enter_tag if trade.enter_tag else ""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        candle = dataframe.iloc[-1]

        # Panic Check
        current_regime = RegimeDetector.get_regime(dataframe, -1)
        if current_regime == MarketRegime.PANIC:
            return -0.01  # Tighten SL immediately if panic detected

        # Bull/Bear Trend Strategies (WMA)
        if "bull_wma" in tag or "bear_wma" in tag:
            if current_profit > 0.05:
                return -0.01
            if current_profit > 0.03:
                return -0.02
            return self._calculate_atr_sl(trade, candle, self.bull_atr_multiplier.value)

        # Range Strategy
        if "range_aroon" in tag:
            if current_profit > 0.02:
                return -0.01
            return self._calculate_atr_sl(
                trade, candle, self.range_atr_multiplier.value
            )

        return -0.10

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        tag = trade.enter_tag if trade.enter_tag else ""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        candle = dataframe.iloc[-1]
        entry_price = trade.open_rate
        atr = candle["atr"]

        # Panic Check
        regime = RegimeDetector.get_regime(dataframe, -1)
        if regime == MarketRegime.PANIC:
            return "panic_exit"

        # Bull/Bear Trend Targets
        if "bull_wma" in tag or "bear_wma" in tag:
            multiplier = self.bull_atr_multiplier.value
            risk_reward = self.bull_risk_reward.value

            if not trade.is_short:
                sl_dist = multiplier * atr
                target_dist = sl_dist * risk_reward
                target_price = entry_price + target_dist
                if current_rate >= target_price:
                    return "trend_tp"
            else:
                sl_dist = multiplier * atr
                target_dist = sl_dist * risk_reward
                target_price = entry_price - target_dist
                if current_rate <= target_price:
                    return "trend_tp"

        # Range Targets
        elif "range_aroon" in tag:
            multiplier = self.range_atr_multiplier.value
            risk_reward = self.range_risk_reward.value

            if not trade.is_short:
                sl_dist = multiplier * atr
                target_dist = sl_dist * risk_reward
                target_price = entry_price + target_dist
                if current_rate >= target_price:
                    return "range_tp"
            else:
                sl_dist = multiplier * atr
                target_dist = sl_dist * risk_reward
                target_price = entry_price - target_dist
                if current_rate <= target_price:
                    return "range_tp"

        return None

    def _calculate_atr_sl(self, trade, candle, multiplier):
        atr = candle["atr"]
        if not trade.is_short:
            sl_abs = candle["close"] - (multiplier * atr)
            return stoploss_from_absolute(sl_abs, trade.open_rate, is_short=False)
        else:
            sl_abs = candle["close"] + (multiplier * atr)
            return stoploss_from_absolute(sl_abs, trade.open_rate, is_short=True)
