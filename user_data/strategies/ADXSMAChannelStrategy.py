"""
ADX-SMA High/Low Channel Engine (475% APR)
===========================================
Trend-Following / Volatility-Filtered Channel Breakout

Captures explosive crypto moves by identifying price breakouts from a
High/Low SMA channel, confirmed by structural trend (100 SMA), market
strength (ADX > 25), and sufficient daily volatility (ATR).

Source: Quant Tactics
Timeframe: 4H
Performance: 475% Return / 11% MDD
"""

from datetime import datetime
from typing import Optional, Union
import logging

from freqtrade.strategy import IStrategy, Trade, informative
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
)
from pandas import DataFrame
import talib.abstract as ta

logger = logging.getLogger(__name__)


class ADXSMAChannelStrategy(IStrategy):
    """
    ADX-SMA High/Low Channel Engine

    Entry Long: Close > High SMA + Close > 100 SMA + ADX > 25 + 1D ATR > 3%
    Entry Short: Close < Low SMA + Close < 100 SMA + ADX > 25 + 1D ATR > 3%
    Exit: Channel boundary + ATR buffer
    """

    INTERFACE_VERSION = 3
    can_short = True

    # ROI disabled - use indicator exits
    minimal_roi = {"0": 100}

    # Wide stoploss - handled by indicator exits
    stoploss = -0.99

    # Timeframe
    timeframe = "4h"

    # Process only new candles
    process_only_new_candles = True

    # Use exit signals
    use_exit_signal = True

    # Startup candle count
    startup_candle_count: int = 120

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # Channel Parameters
    channel_period = IntParameter(15, 30, default=20, space="buy", optimize=True)

    # Trend Filter
    sma_trend_period = IntParameter(80, 120, default=100, space="buy", optimize=False)

    # ADX Threshold
    adx_threshold = IntParameter(15, 30, default=25, space="buy", optimize=True)

    # ATR Volatility Filter
    atr_volatility_pct = DecimalParameter(
        2.0, 5.0, default=3.0, decimals=1, space="buy", optimize=True
    )

    # Exit Buffer
    atr_exit_multiplier = DecimalParameter(
        0.5, 1.5, default=0.7, decimals=1, space="sell", optimize=True
    )

    # ==================== INFORMATIVE TIMEFRAME ====================

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate 1D ATR for volatility filter."""
        dataframe["atr_1d"] = ta.ATR(dataframe, timeperiod=14)
        return dataframe

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate Channel SMAs, 100 SMA, and ADX."""

        # High/Low Channel SMAs
        dataframe["sma_high"] = ta.SMA(
            dataframe["high"], timeperiod=self.channel_period.value
        )
        dataframe["sma_low"] = ta.SMA(
            dataframe["low"], timeperiod=self.channel_period.value
        )

        # 100 SMA Trend Filter
        dataframe["sma_100"] = ta.SMA(dataframe, timeperiod=self.sma_trend_period.value)

        # ADX (Market Strength)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # ATR Volatility Check (1D ATR > 3% of current price)
        dataframe["atr_volatility_ok"] = dataframe["atr_1d"] > (
            dataframe["close"] * (self.atr_volatility_pct.value / 100)
        )

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long: Close > High SMA + Close > 100 SMA + ADX > 25 + ATR > 3%
        Short: Close < Low SMA + Close < 100 SMA + ADX > 25 + ATR > 3%
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Long Entry (Channel Breakout Up)
        long_conditions = (
            (dataframe["close"] > dataframe["sma_high"])
            & (dataframe["close"] > dataframe["sma_100"])
            & (dataframe["adx"] > self.adx_threshold.value)
            & (dataframe["atr_volatility_ok"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "channel_breakout_long"

        # Short Entry (Channel Breakout Down)
        short_conditions = (
            (dataframe["close"] < dataframe["sma_low"])
            & (dataframe["close"] < dataframe["sma_100"])
            & (dataframe["adx"] > self.adx_threshold.value)
            & (dataframe["atr_volatility_ok"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[short_conditions, "enter_short"] = 1
        dataframe.loc[short_conditions, "enter_tag"] = "channel_breakout_short"

        return dataframe

    # ==================== EXIT LOGIC ====================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit Long: Price < Low SMA - (ATR × 0.7)
        Exit Short: Price > High SMA + (ATR × 0.7)
        """
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        # Exit Long (with ATR buffer)
        exit_long = dataframe["close"] < (
            dataframe["sma_low"]
            - (dataframe["atr_1d"] * self.atr_exit_multiplier.value)
        )
        dataframe.loc[exit_long, "exit_long"] = 1

        # Exit Short (with ATR buffer)
        exit_short = dataframe["close"] > (
            dataframe["sma_high"]
            + (dataframe["atr_1d"] * self.atr_exit_multiplier.value)
        )
        dataframe.loc[exit_short, "exit_short"] = 1

        return dataframe

    # ==================== PLOT CONFIG ====================

    plot_config = {
        "main_plot": {
            "sma_high": {"color": "red"},
            "sma_low": {"color": "green"},
            "sma_100": {"color": "purple"},
        },
        "subplots": {
            "ADX": {
                "adx": {"color": "blue"},
            },
        },
    }
