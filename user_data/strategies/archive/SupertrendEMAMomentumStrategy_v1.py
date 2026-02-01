"""
Supertrend EMA Momentum Engine
===============================
Trend-Following / Volatility-Adjusted Momentum

Captures explosive trends by aligning a volatility-based Supertrend with
a hierarchical EMA filter to maintain a high profit-to-drawdown ratio.

Source: Quant Tactics
Timeframe: 30m
Performance: 738% Return (1yr) / 12% MDD / 1.76 Sharpe
"""

from datetime import datetime
from typing import Optional, Union
import logging
import numpy as np

from freqtrade.strategy import IStrategy, Trade
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
)
from pandas import DataFrame
import talib.abstract as ta

logger = logging.getLogger(__name__)


def supertrend(dataframe: DataFrame, length: int = 10, multiplier: float = 4.0):
    """
    Calculate Supertrend indicator.

    Returns:
    - supertrend: The Supertrend line value
    - direction: 1 for uptrend, -1 for downtrend
    """
    # Calculate ATR
    atr = ta.ATR(dataframe, timeperiod=length)

    # Calculate basic bands
    hl2 = (dataframe["high"] + dataframe["low"]) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)

    # Initialize
    supertrend_values = [0.0] * len(dataframe)
    direction = [1] * len(dataframe)

    for i in range(1, len(dataframe)):
        # Update bands
        if dataframe["close"].iloc[i] > upper_band.iloc[i - 1]:
            direction[i] = 1
        elif dataframe["close"].iloc[i] < lower_band.iloc[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]

            # Adjust bands
            if direction[i] == 1 and lower_band.iloc[i] < lower_band.iloc[i - 1]:
                lower_band.iloc[i] = lower_band.iloc[i - 1]
            if direction[i] == -1 and upper_band.iloc[i] > upper_band.iloc[i - 1]:
                upper_band.iloc[i] = upper_band.iloc[i - 1]

        # Set supertrend value
        if direction[i] == 1:
            supertrend_values[i] = lower_band.iloc[i]
        else:
            supertrend_values[i] = upper_band.iloc[i]

    return supertrend_values, direction


class SupertrendEMAMomentumStrategy(IStrategy):
    """
    Supertrend EMA Momentum Engine

    Entry Long: Close > EMA + Supertrend flips to Buy + Distance > threshold
    Entry Short: Close < EMA + Supertrend flips to Sell + Distance > threshold
    Exit: Supertrend reversal OR Fixed TP
    """

    INTERFACE_VERSION = 3
    can_short = True

    # ROI handled by custom exit
    minimal_roi = {"0": 100}

    # Wide stoploss - Supertrend handles exits
    stoploss = -0.99

    # Timeframe
    timeframe = "30m"

    # Process only new candles
    process_only_new_candles = True

    # Use exit signals
    use_exit_signal = True

    # Startup candle count
    startup_candle_count: int = 100

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # EMA Trend Filter
    ema_period = IntParameter(30, 200, default=50, space="buy", optimize=True)

    # Supertrend Parameters
    supertrend_length = IntParameter(10, 16, default=10, space="buy", optimize=True)
    supertrend_multiplier = DecimalParameter(
        2.0, 5.0, default=4.0, decimals=1, space="buy", optimize=True
    )

    # Breakout Filter (Max Distance from EMA)
    max_distance_pct = DecimalParameter(
        1.0, 6.0, default=2.0, decimals=1, space="buy", optimize=True
    )

    # Take Profit
    take_profit_pct = DecimalParameter(
        5.0, 20.0, default=15.0, decimals=0, space="sell", optimize=True
    )

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate EMA, Supertrend, and Distance."""

        # EMA Trend Filter
        dataframe["ema"] = ta.EMA(dataframe, timeperiod=self.ema_period.value)

        # Supertrend
        st_values, st_direction = supertrend(
            dataframe,
            length=self.supertrend_length.value,
            multiplier=self.supertrend_multiplier.value,
        )
        dataframe["supertrend"] = st_values
        dataframe["st_direction"] = st_direction

        # Distance from EMA (percentage)
        dataframe["distance_pct"] = (
            abs(dataframe["close"] - dataframe["ema"]) / dataframe["ema"]
        ) * 100

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long Entry: Close > EMA + Supertrend flips to Buy + Distance > threshold
        Short Entry: Close < EMA + Supertrend flips to Sell + Distance > threshold
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Supertrend flip detection
        st_flip_up = (dataframe["st_direction"] == 1) & (
            dataframe["st_direction"].shift(1) == -1
        )
        st_flip_down = (dataframe["st_direction"] == -1) & (
            dataframe["st_direction"].shift(1) == 1
        )

        # Long Entry
        long_conditions = (
            (dataframe["close"] > dataframe["ema"])
            & st_flip_up
            & (dataframe["distance_pct"] > self.max_distance_pct.value)
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "supertrend_ema_long"

        # Short Entry
        short_conditions = (
            (dataframe["close"] < dataframe["ema"])
            & st_flip_down
            & (dataframe["distance_pct"] > self.max_distance_pct.value)
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[short_conditions, "enter_short"] = 1
        dataframe.loc[short_conditions, "enter_tag"] = "supertrend_ema_short"

        return dataframe

    # ==================== EXIT LOGIC ====================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit when Supertrend reverses direction.
        """
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        # Exit Long: Supertrend flips to Sell
        exit_long = dataframe["st_direction"] == -1
        dataframe.loc[exit_long, "exit_long"] = 1

        # Exit Short: Supertrend flips to Buy
        exit_short = dataframe["st_direction"] == 1
        dataframe.loc[exit_short, "exit_short"] = 1

        return dataframe

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[Union[str, bool]]:
        """
        Fixed Take Profit at target %.
        """
        if current_profit >= (self.take_profit_pct.value / 100):
            return f"tp_{self.take_profit_pct.value}pct"

        return None

    # ==================== PLOT CONFIG ====================

    plot_config = {
        "main_plot": {
            "ema": {"color": "blue"},
            "supertrend": {"color": "green"},
        },
    }
