"""
Parabolic SAR Momentum Engine
==============================
Trend-Following / Reversal Confirmation

Utilizes Parabolic SAR for reversal detection, confirmed by 200 EMA
structural bias and RSI momentum thresholds to maximize win-rate in
trending markets.

Source: Quant Tactics
Timeframe: 30m
Performance: 421% Return (1yr) / 9% MDD / 1.76 Sharpe
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


class ParabolicSARMomentumStrategy(IStrategy):
    """
    Parabolic SAR Momentum Engine

    Entry Long: Close > 200 EMA + Close > PSAR + RSI crosses above 65
    Entry Short: Close < 200 EMA + Close < PSAR + RSI crosses below 45
    Exit: Fixed SL (3%) / TP (6%) - 1:2 RR
    """

    INTERFACE_VERSION = 3
    can_short = True

    # ROI handled by custom exit
    minimal_roi = {"0": 100}

    # Stoploss
    stoploss = -0.03  # Default -3%

    # Timeframe
    timeframe = "30m"

    # Process only new candles
    process_only_new_candles = True

    # Startup candle count
    startup_candle_count: int = 220

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # EMA Trend Guard
    ema_period = IntParameter(150, 250, default=200, space="buy", optimize=False)

    # Parabolic SAR
    psar_af = DecimalParameter(
        0.01, 0.05, default=0.02, decimals=2, space="buy", optimize=True
    )
    psar_max_af = DecimalParameter(
        0.1, 0.3, default=0.2, decimals=1, space="buy", optimize=True
    )

    # RSI Parameters
    rsi_period = IntParameter(7, 28, default=14, space="buy", optimize=True)
    rsi_upper_threshold = IntParameter(55, 70, default=65, space="buy", optimize=True)
    rsi_lower_threshold = IntParameter(30, 50, default=45, space="buy", optimize=True)

    # Risk Management
    stop_loss_pct = DecimalParameter(
        1.0, 5.0, default=3.0, decimals=1, space="sell", optimize=True
    )
    take_profit_pct = DecimalParameter(
        3.0, 10.0, default=6.0, decimals=1, space="sell", optimize=True
    )

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate 200 EMA, Parabolic SAR, and RSI."""

        # EMA Trend Guard
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=self.ema_period.value)

        # Parabolic SAR
        dataframe["sar"] = ta.SAR(
            dataframe, acceleration=self.psar_af.value, maximum=self.psar_max_af.value
        )

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long Entry: Close > 200 EMA + Close > PSAR + RSI crosses above 65
        Short Entry: Close < 200 EMA + Close < PSAR + RSI crosses below 45
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Long Entry (PSAR below price = uptrend)
        long_conditions = (
            (dataframe["close"] > dataframe["ema_200"])
            & (dataframe["close"] > dataframe["sar"])
            & qtpylib.crossed_above(dataframe["rsi"], self.rsi_upper_threshold.value)
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "psar_momentum_long"

        # Short Entry (PSAR above price = downtrend)
        short_conditions = (
            (dataframe["close"] < dataframe["ema_200"])
            & (dataframe["close"] < dataframe["sar"])
            & qtpylib.crossed_below(dataframe["rsi"], self.rsi_lower_threshold.value)
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[short_conditions, "enter_short"] = 1
        dataframe.loc[short_conditions, "enter_tag"] = "psar_momentum_short"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """No indicator-based exit - handled by custom_exit."""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    # ==================== EXIT MANAGEMENT ====================

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
        Fixed SL/TP Exit (1:2 RR).
        """

        # Take Profit
        if current_profit >= (self.take_profit_pct.value / 100):
            return f"tp_{self.take_profit_pct.value}pct"

        # Stop Loss (redundant with stoploss, but explicit)
        if current_profit <= -(self.stop_loss_pct.value / 100):
            return f"sl_{self.stop_loss_pct.value}pct"

        return None

    # ==================== PLOT CONFIG ====================

    plot_config = {
        "main_plot": {
            "ema_200": {"color": "purple"},
            "sar": {"color": "orange"},
        },
        "subplots": {
            "RSI": {
                "rsi": {"color": "blue"},
            },
        },
    }
