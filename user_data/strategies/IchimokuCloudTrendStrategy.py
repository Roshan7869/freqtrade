"""
Ichimoku Cloud Trend Engine (2944% Profit)
===========================================
Trend-Following / Momentum / ATR-Volatility Exit

Captures sustained large-cap trends by aligning short-term momentum (Tenkan)
and medium-term trend (Kijun) with the leading volatility cloud (Kumo).

Source: Quant Tactics
Timeframe: 4H
Performance: 2944% Return / 26% MDD / 51% Win Rate
"""

from datetime import datetime
from typing import Optional, Union
import logging

from freqtrade.strategy import IStrategy, Trade
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
)
from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib

logger = logging.getLogger(__name__)


class IchimokuCloudTrendStrategy(IStrategy):
    """
    Ichimoku Cloud Trend Engine

    Entry Long: Tenkan crosses above Kijun + Price > Cloud + Both lines sloping up
    Entry Short: Tenkan crosses below Kijun + Price < Cloud + Both lines sloping down
    Exit: ATR-based distance from Kijun (Price < Kijun - 2×ATR for longs)
    """

    INTERFACE_VERSION = 3
    can_short = True

    # ROI disabled - use indicator exits
    minimal_roi = {"0": 100}

    # Wide stoploss - handled by custom exit
    stoploss = -0.99

    # Timeframe
    timeframe = "4h"

    # Process only new candles
    process_only_new_candles = True

    # Use exit signals
    use_exit_signal = True

    # Startup candle count
    startup_candle_count: int = 100

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # Ichimoku Parameters
    tenkan_period = IntParameter(7, 15, default=9, space="buy", optimize=True)
    kijun_period = IntParameter(20, 35, default=26, space="buy", optimize=True)
    senkou_b_period = IntParameter(40, 60, default=52, space="buy", optimize=True)

    # ATR Exit
    atr_period = IntParameter(10, 20, default=14, space="sell", optimize=False)
    atr_exit_multiplier = DecimalParameter(
        1.0, 3.0, default=2.0, decimals=1, space="sell", optimize=True
    )

    # Slope lookback
    slope_period = IntParameter(2, 5, default=3, space="buy", optimize=False)

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate Ichimoku components and ATR."""

        # Tenkan-sen (Conversion Line): (9-period high + 9-period low) / 2
        period_high = dataframe["high"].rolling(window=self.tenkan_period.value).max()
        period_low = dataframe["low"].rolling(window=self.tenkan_period.value).min()
        dataframe["tenkan"] = (period_high + period_low) / 2

        # Kijun-sen (Base Line): (26-period high + 26-period low) / 2
        period_high = dataframe["high"].rolling(window=self.kijun_period.value).max()
        period_low = dataframe["low"].rolling(window=self.kijun_period.value).min()
        dataframe["kijun"] = (period_high + period_low) / 2

        # Senkou Span A (Leading Span A): (Tenkan + Kijun) / 2, shifted forward
        dataframe["senkou_a"] = ((dataframe["tenkan"] + dataframe["kijun"]) / 2).shift(
            self.kijun_period.value
        )

        # Senkou Span B (Leading Span B): (52-period high + 52-period low) / 2, shifted forward
        period_high = dataframe["high"].rolling(window=self.senkou_b_period.value).max()
        period_low = dataframe["low"].rolling(window=self.senkou_b_period.value).min()
        dataframe["senkou_b"] = ((period_high + period_low) / 2).shift(
            self.kijun_period.value
        )

        # Cloud top/bottom (for easier comparison)
        dataframe["cloud_top"] = dataframe[["senkou_a", "senkou_b"]].max(axis=1)
        dataframe["cloud_bottom"] = dataframe[["senkou_a", "senkou_b"]].min(axis=1)

        # Slopes (for trend direction confirmation)
        sp = self.slope_period.value
        dataframe["tenkan_slope"] = dataframe["tenkan"] - dataframe["tenkan"].shift(sp)
        dataframe["kijun_slope"] = dataframe["kijun"] - dataframe["kijun"].shift(sp)

        # ATR for exit
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=self.atr_period.value)

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long: Tenkan crosses above Kijun + Price > Cloud + Both sloping up
        Short: Tenkan crosses below Kijun + Price < Cloud + Both sloping down
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Long Entry
        long_conditions = (
            qtpylib.crossed_above(dataframe["tenkan"], dataframe["kijun"])
            & (dataframe["close"] > dataframe["cloud_top"])
            & (dataframe["tenkan_slope"] >= 0)
            & (dataframe["kijun_slope"] >= 0)
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "ichimoku_bullish"

        # Short Entry
        short_conditions = (
            qtpylib.crossed_below(dataframe["tenkan"], dataframe["kijun"])
            & (dataframe["close"] < dataframe["cloud_bottom"])
            & (dataframe["tenkan_slope"] <= 0)
            & (dataframe["kijun_slope"] <= 0)
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[short_conditions, "enter_short"] = 1
        dataframe.loc[short_conditions, "enter_tag"] = "ichimoku_bearish"

        return dataframe

    # ==================== EXIT LOGIC ====================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit Long: Price < Kijun - (2 × ATR)
        Exit Short: Price > Kijun + (2 × ATR)
        """
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        # Exit Long
        exit_long = dataframe["close"] < (
            dataframe["kijun"] - (self.atr_exit_multiplier.value * dataframe["atr"])
        )
        dataframe.loc[exit_long, "exit_long"] = 1

        # Exit Short
        exit_short = dataframe["close"] > (
            dataframe["kijun"] + (self.atr_exit_multiplier.value * dataframe["atr"])
        )
        dataframe.loc[exit_short, "exit_short"] = 1

        return dataframe

    # ==================== PLOT CONFIG ====================

    plot_config = {
        "main_plot": {
            "tenkan": {"color": "red"},
            "kijun": {"color": "blue"},
            "senkou_a": {
                "color": "green",
                "fill_to": "senkou_b",
                "fill_color": "rgba(0,255,0,0.2)",
            },
            "senkou_b": {"color": "red"},
        },
    }
