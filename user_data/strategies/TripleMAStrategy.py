"""
Triple Moving Average (3MA) Trend Engine
=========================================
Trend-Following / Stacked Moving Average Alignment

Captures sustained trends by requiring total price isolation above/below
the short-term MA while confirmed by a hierarchical moving average stack.

Source: Quant Tactics
Timeframe: 4H
Performance: 275% Return / 11% MDD / 3.21 Sharpe
"""

from datetime import datetime
from typing import Optional, Union
import logging

from freqtrade.strategy import IStrategy, Trade
from freqtrade.strategy import (
    IntParameter,
)
from pandas import DataFrame
import talib.abstract as ta

logger = logging.getLogger(__name__)


class TripleMAStrategy(IStrategy):
    """
    Triple Moving Average Trend Engine

    Entry Long: Candle LOW > Short MA + Bullish MA Stack (S > M > L) + All Sloping Up
    Entry Short: Candle HIGH < Short MA + Bearish MA Stack (S < M < L) + All Sloping Down
    Exit Long: Candle HIGH < Medium MA
    Exit Short: Candle LOW > Medium MA
    """

    INTERFACE_VERSION = 3
    can_short = True

    # ROI disabled - use indicator-based exits
    minimal_roi = {"0": 100}

    # Wide stoploss - strategy relies on MA exits
    stoploss = -0.99

    # Timeframe
    timeframe = "4h"

    # Process only new candles
    process_only_new_candles = True

    # Use exit signals
    use_exit_signal = True

    # Startup candle count (need enough for Long MA)
    startup_candle_count: int = 150

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # MA Lengths (Optimized via Bayesian Search)
    sma_short = IntParameter(5, 20, default=10, space="buy", optimize=True)
    sma_medium = IntParameter(20, 40, default=27, space="buy", optimize=True)
    sma_long = IntParameter(80, 150, default=122, space="buy", optimize=True)

    # Slope lookback period
    slope_period = IntParameter(2, 5, default=3, space="buy", optimize=False)

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate Triple SMA stack and slopes."""

        # Simple Moving Averages
        dataframe["sma_short"] = ta.SMA(dataframe, timeperiod=self.sma_short.value)
        dataframe["sma_medium"] = ta.SMA(dataframe, timeperiod=self.sma_medium.value)
        dataframe["sma_long"] = ta.SMA(dataframe, timeperiod=self.sma_long.value)

        # Slope calculation (current - previous N periods)
        sp = self.slope_period.value
        dataframe["slope_short"] = dataframe["sma_short"] - dataframe[
            "sma_short"
        ].shift(sp)
        dataframe["slope_medium"] = dataframe["sma_medium"] - dataframe[
            "sma_medium"
        ].shift(sp)
        dataframe["slope_long"] = dataframe["sma_long"] - dataframe["sma_long"].shift(
            sp
        )

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long Entry: Bullish Stack + All Sloping Up + Candle LOW > Short MA
        Short Entry: Bearish Stack + All Sloping Down + Candle HIGH < Short MA
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Bullish Stack: Short > Medium > Long
        bullish_stack = (dataframe["sma_short"] > dataframe["sma_medium"]) & (
            dataframe["sma_medium"] > dataframe["sma_long"]
        )

        # All MAs sloping up
        all_sloping_up = (
            (dataframe["slope_short"] > 0)
            & (dataframe["slope_medium"] > 0)
            & (dataframe["slope_long"] > 0)
        )

        # Candle LOW completely above Short MA (price isolation)
        candle_above_short = dataframe["low"] > dataframe["sma_short"]

        # Long Entry Conditions
        long_conditions = (
            bullish_stack
            & all_sloping_up
            & candle_above_short
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "3ma_bullish_isolation"

        # Bearish Stack: Short < Medium < Long
        bearish_stack = (dataframe["sma_short"] < dataframe["sma_medium"]) & (
            dataframe["sma_medium"] < dataframe["sma_long"]
        )

        # All MAs sloping down
        all_sloping_down = (
            (dataframe["slope_short"] < 0)
            & (dataframe["slope_medium"] < 0)
            & (dataframe["slope_long"] < 0)
        )

        # Candle HIGH completely below Short MA (price isolation)
        candle_below_short = dataframe["high"] < dataframe["sma_short"]

        # Short Entry Conditions
        short_conditions = (
            bearish_stack
            & all_sloping_down
            & candle_below_short
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[short_conditions, "enter_short"] = 1
        dataframe.loc[short_conditions, "enter_tag"] = "3ma_bearish_isolation"

        return dataframe

    # ==================== EXIT LOGIC ====================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit Long: Candle HIGH < Medium MA (completely below)
        Exit Short: Candle LOW > Medium MA (completely above)
        """
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        # Exit Long: Candle HIGH completely below Medium MA
        exit_long = dataframe["high"] < dataframe["sma_medium"]
        dataframe.loc[exit_long, "exit_long"] = 1

        # Exit Short: Candle LOW completely above Medium MA
        exit_short = dataframe["low"] > dataframe["sma_medium"]
        dataframe.loc[exit_short, "exit_short"] = 1

        return dataframe

    # ==================== PLOT CONFIG ====================

    plot_config = {
        "main_plot": {
            "sma_short": {"color": "blue"},
            "sma_medium": {"color": "orange"},
            "sma_long": {"color": "red"},
        },
    }
