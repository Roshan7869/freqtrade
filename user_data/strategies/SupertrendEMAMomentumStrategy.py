"""
Supertrend EMA Momentum Engine (Advanced MTF)
==============================================
Trend-Following / Volatility-Adjusted Momentum

Captures sustained crypto trends by aligning a volatility-adjusted Supertrend
with a hierarchical EMA filter, utilizing multi-timeframe ATR quantiles to
programmatically exit or avoid sideways regimes.

Source: Quant Tactics
Timeframe: 1H (with 4H ATR volatility filter)
Performance: 212% Return / 12% MDD
"""

from datetime import datetime
from typing import Optional, Union
import logging
import numpy as np

from freqtrade.strategy import IStrategy, Trade, informative
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
)
from pandas import DataFrame
import talib.abstract as ta

logger = logging.getLogger(__name__)


def supertrend(dataframe: DataFrame, length: int = 10, multiplier: float = 4.0):
    """Calculate Supertrend indicator."""
    atr = ta.ATR(dataframe, timeperiod=length)
    hl2 = (dataframe["high"] + dataframe["low"]) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)

    supertrend_values = [0.0] * len(dataframe)
    direction = [1] * len(dataframe)

    for i in range(1, len(dataframe)):
        if dataframe["close"].iloc[i] > upper_band.iloc[i - 1]:
            direction[i] = 1
        elif dataframe["close"].iloc[i] < lower_band.iloc[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
            if direction[i] == 1 and lower_band.iloc[i] < lower_band.iloc[i - 1]:
                lower_band.iloc[i] = lower_band.iloc[i - 1]
            if direction[i] == -1 and upper_band.iloc[i] > upper_band.iloc[i - 1]:
                upper_band.iloc[i] = upper_band.iloc[i - 1]

        supertrend_values[i] = (
            lower_band.iloc[i] if direction[i] == 1 else upper_band.iloc[i]
        )

    return supertrend_values, direction


class SupertrendEMAMomentumStrategy(IStrategy):
    """
    Supertrend EMA Momentum Engine (Advanced MTF)

    Entry: Close vs Supertrend + Close vs 100 EMA + 4H ATR > quantile + ADX > dynamic threshold
    Exit: Supertrend reversal
    """

    INTERFACE_VERSION = 3
    can_short = True

    minimal_roi = {"0": 100}
    stoploss = -0.99
    timeframe = "1h"
    process_only_new_candles = True
    use_exit_signal = True
    startup_candle_count: int = 120

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # Supertrend
    supertrend_length = IntParameter(8, 16, default=10, space="buy", optimize=True)
    supertrend_multiplier = DecimalParameter(
        2.0, 5.0, default=3.0, decimals=1, space="buy", optimize=True
    )

    # ATR Quantile Filter
    atr_quantile = DecimalParameter(
        0.3, 0.6, default=0.4, decimals=1, space="buy", optimize=True
    )
    atr_lookback = IntParameter(20, 50, default=30, space="buy", optimize=False)

    # Dynamic ADX Threshold (base + ATR adjustment)
    adx_base_threshold = IntParameter(15, 30, default=20, space="buy", optimize=True)
    adx_atr_coupling = DecimalParameter(
        0.0, 2.0, default=1.0, decimals=1, space="buy", optimize=True
    )

    # ==================== INFORMATIVE TIMEFRAME ====================

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate 4H ATR for volatility regime filter."""
        dataframe["atr_4h"] = ta.ATR(dataframe, timeperiod=14)
        return dataframe

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate Supertrend, 100 EMA, ADX, and ATR quantile."""

        # 100 EMA Trend Bias
        dataframe["ema_100"] = ta.EMA(dataframe, timeperiod=100)

        # Supertrend
        st_values, st_direction = supertrend(
            dataframe,
            length=self.supertrend_length.value,
            multiplier=self.supertrend_multiplier.value,
        )
        dataframe["supertrend"] = st_values
        dataframe["st_direction"] = st_direction

        # ADX
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # ATR Quantile Threshold (4H)
        dataframe["atr_threshold"] = (
            dataframe["atr_4h"]
            .rolling(window=self.atr_lookback.value)
            .quantile(self.atr_quantile.value)
        )

        # Dynamic ADX Threshold (higher ATR = higher ADX requirement)
        # Normalize ATR to 0-1 range for coupling
        atr_normalized = (
            dataframe["atr_4h"] - dataframe["atr_4h"].rolling(50).min()
        ) / (
            dataframe["atr_4h"].rolling(50).max()
            - dataframe["atr_4h"].rolling(50).min()
        )
        dataframe["adx_dynamic_threshold"] = self.adx_base_threshold.value + (
            atr_normalized * self.adx_atr_coupling.value * 10
        )

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long: Close > Supertrend + Close > 100 EMA + 4H ATR > quantile + ADX > dynamic
        Short: Close < Supertrend + Close < 100 EMA + 4H ATR > quantile + ADX > dynamic
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Volatility regime filter
        volatility_ok = dataframe["atr_4h"] > dataframe["atr_threshold"]

        # Long Entry
        long_conditions = (
            (dataframe["close"] > dataframe["supertrend"])
            & (dataframe["close"] > dataframe["ema_100"])
            & volatility_ok
            & (dataframe["adx"] > dataframe["adx_dynamic_threshold"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "supertrend_mtf_long"

        # Short Entry
        short_conditions = (
            (dataframe["close"] < dataframe["supertrend"])
            & (dataframe["close"] < dataframe["ema_100"])
            & volatility_ok
            & (dataframe["adx"] > dataframe["adx_dynamic_threshold"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[short_conditions, "enter_short"] = 1
        dataframe.loc[short_conditions, "enter_tag"] = "supertrend_mtf_short"

        return dataframe

    # ==================== EXIT LOGIC ====================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit when Supertrend reverses."""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        dataframe.loc[dataframe["st_direction"] == -1, "exit_long"] = 1
        dataframe.loc[dataframe["st_direction"] == 1, "exit_short"] = 1

        return dataframe

    # ==================== PLOT CONFIG ====================

    plot_config = {
        "main_plot": {
            "ema_100": {"color": "purple"},
            "supertrend": {"color": "orange"},
        },
        "subplots": {
            "ADX": {
                "adx": {"color": "blue"},
                "adx_dynamic_threshold": {"color": "red"},
            },
        },
    }
