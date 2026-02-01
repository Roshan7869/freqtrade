"""
RSI-SMA Momentum Engine
========================
Trend-Following / Momentum Divergence Filter

Captures high-probability momentum bursts by aligning RSI-smoothed signals
with the 200 SMA long-term trend while filtering for overextended price action.

Source: Quant Tactics
Timeframe: 30m
Performance: 246% Return / 11% MDD / 10.66 Sharpe
"""

from datetime import datetime, timedelta
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


class RSISMAMomentumStrategy(IStrategy):
    """
    RSI-SMA Momentum Engine

    Entry Long: Close > 200 SMA + Smoothed RSI crosses above 55 + Candle not exhausted
    Entry Short: Close < 200 SMA + Smoothed RSI crosses below 45 + Candle not exhausted
    Exit: Fixed SL/TP + Max Holding Period
    """

    INTERFACE_VERSION = 3
    can_short = True

    # ROI handled by custom exit
    minimal_roi = {"0": 100}

    # Stoploss handled by parameter
    stoploss = -0.12  # Default -12%, overridden by custom_stoploss if needed

    # Timeframe
    timeframe = "30m"

    # Process only new candles
    process_only_new_candles = True

    # Startup candle count (need 200 for SMA)
    startup_candle_count: int = 220

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # Trend Filter
    sma_trend_period = IntParameter(150, 250, default=200, space="buy", optimize=False)

    # RSI Parameters
    rsi_period = IntParameter(10, 20, default=14, space="buy", optimize=True)
    rsi_smooth_period = IntParameter(10, 20, default=14, space="buy", optimize=True)
    rsi_long_threshold = IntParameter(50, 60, default=55, space="buy", optimize=True)
    rsi_short_threshold = IntParameter(40, 50, default=45, space="buy", optimize=True)

    # Candle Exhaustion Filter
    max_candle_size_pct = DecimalParameter(
        2.0, 8.0, default=4.5, decimals=1, space="buy", optimize=True
    )

    # Risk Management
    stop_loss_pct = DecimalParameter(
        5.0, 20.0, default=12.0, decimals=0, space="sell", optimize=True
    )
    take_profit_pct = DecimalParameter(
        10.0, 30.0, default=22.0, decimals=0, space="sell", optimize=True
    )

    # Max Holding Period (in candles, 48 candles @ 30m = 1 day)
    max_holding_candles = IntParameter(
        48, 240, default=144, space="sell", optimize=True
    )  # 1-5 days

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate 200 SMA, Smoothed RSI, and Candle Size."""

        # 200 SMA Trend Filter
        dataframe["sma_200"] = ta.SMA(dataframe, timeperiod=self.sma_trend_period.value)

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)

        # Smoothed RSI (SMA of RSI)
        dataframe["rsi_smooth"] = ta.SMA(
            dataframe["rsi"], timeperiod=self.rsi_smooth_period.value
        )

        # Candle Size Percentage (Body size relative to open)
        dataframe["candle_size_pct"] = (
            abs(dataframe["close"] - dataframe["open"]) / dataframe["open"]
        ) * 100

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long Entry: Close > 200 SMA + RSI_Smooth crosses above 55 + Small candle
        Short Entry: Close < 200 SMA + RSI_Smooth crosses below 45 + Small candle
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Candle not exhausted (not overextended)
        candle_not_exhausted = (
            dataframe["candle_size_pct"] < self.max_candle_size_pct.value
        )

        # Long Entry
        long_conditions = (
            (dataframe["close"] > dataframe["sma_200"])
            & qtpylib.crossed_above(
                dataframe["rsi_smooth"], self.rsi_long_threshold.value
            )
            & candle_not_exhausted
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "rsi_sma_momentum_long"

        # Short Entry
        short_conditions = (
            (dataframe["close"] < dataframe["sma_200"])
            & qtpylib.crossed_below(
                dataframe["rsi_smooth"], self.rsi_short_threshold.value
            )
            & candle_not_exhausted
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[short_conditions, "enter_short"] = 1
        dataframe.loc[short_conditions, "enter_tag"] = "rsi_sma_momentum_short"

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
        Exit Logic:
        1. Take Profit at target %
        2. Stop Loss at target %
        3. Max Holding Period exceeded with minimal profit
        """

        # Take Profit
        if current_profit >= (self.take_profit_pct.value / 100):
            return f"tp_{self.take_profit_pct.value}pct"

        # Stop Loss
        if current_profit <= -(self.stop_loss_pct.value / 100):
            return f"sl_{self.stop_loss_pct.value}pct"

        # Max Holding Period
        trade_duration = (
            current_time - trade.open_date_utc
        ).total_seconds() / 60  # in minutes
        max_duration_minutes = self.max_holding_candles.value * 30  # 30m candles

        if trade_duration >= max_duration_minutes:
            # Exit if profit is less than 0.5% after holding period
            if current_profit < 0.005:
                return "holding_period_exceeded"

        return None

    # ==================== PLOT CONFIG ====================

    plot_config = {
        "main_plot": {
            "sma_200": {"color": "purple"},
        },
        "subplots": {
            "RSI": {
                "rsi_smooth": {"color": "blue"},
            },
        },
    }
