"""
Momentum Breakout Engine (968% APR)
====================================
Breakout / Momentum / Trend Strength Confluence

Identifies high-probability entry points by confirming price breakouts
with positive momentum, institutional trend strength (ADX), and volume
validation.

Source: Quant Tactics
Timeframe: 15m
Performance: 968% @ 4x Leverage (1yr) / 31.5% MDD
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

logger = logging.getLogger(__name__)


class MomentumBreakoutStrategy(IStrategy):
    """
    Momentum Breakout Engine

    Entry Long: Price > Resistance + Momentum > 0 + ADX > 20 + Volume > Avg
    Exit: Fixed SL/TP OR Dynamic (Price < Support + Momentum < 0)
    """

    INTERFACE_VERSION = 3
    can_short = False  # Long-only breakout strategy

    # ROI handled by custom exit
    minimal_roi = {"0": 100}

    # Stoploss
    stoploss = -0.05  # Default -5%

    # Timeframe
    timeframe = "15m"

    # Process only new candles
    process_only_new_candles = True

    # Use exit signals
    use_exit_signal = True

    # Startup candle count
    startup_candle_count: int = 150

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # Structural Levels (Rolling Windows)
    resistance_window = IntParameter(60, 120, default=80, space="buy", optimize=True)
    support_window = IntParameter(60, 120, default=80, space="buy", optimize=True)

    # ADX Threshold
    adx_threshold = IntParameter(15, 30, default=20, space="buy", optimize=True)

    # Volume Filter
    volume_window = IntParameter(20, 30, default=25, space="buy", optimize=True)

    # Risk Management
    stop_loss_pct = DecimalParameter(
        1.0, 15.0, default=5.0, decimals=1, space="sell", optimize=True
    )
    risk_reward_ratio = DecimalParameter(
        1.0, 2.5, default=1.5, decimals=1, space="sell", optimize=True
    )

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate Resistance, Support, Momentum, ADX, and Volume Average."""

        # Rolling Resistance (Max High)
        dataframe["resistance"] = (
            dataframe["high"].rolling(window=self.resistance_window.value).max()
        )

        # Rolling Support (Min Low)
        dataframe["support"] = (
            dataframe["low"].rolling(window=self.support_window.value).min()
        )

        # Momentum Indicator (Rate of Change)
        dataframe["momentum"] = ta.MOM(dataframe, timeperiod=10)

        # ADX (Trend Strength)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # Average Volume
        dataframe["avg_volume"] = (
            dataframe["volume"].rolling(window=self.volume_window.value).mean()
        )

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long Entry: Breakout above resistance + Momentum > 0 + ADX > 20 + Volume > Avg
        """
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""

        # Breakout Confluence
        long_conditions = (
            (dataframe["close"] > dataframe["resistance"])
            & (dataframe["momentum"] > 0)
            & (dataframe["adx"] > self.adx_threshold.value)
            & (dataframe["volume"] > dataframe["avg_volume"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "momentum_breakout"

        return dataframe

    # ==================== EXIT LOGIC ====================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Dynamic Exit: Price breaks below support + Momentum < 0
        """
        dataframe["exit_long"] = 0

        # Dynamic Exit (Trend Reversal)
        exit_conditions = (dataframe["close"] < dataframe["support"]) & (
            dataframe["momentum"] < 0
        )

        dataframe.loc[exit_conditions, "exit_long"] = 1

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
        Fixed SL/TP Exit (RR Ratio).
        """

        # Take Profit
        tp_pct = (self.stop_loss_pct.value / 100) * self.risk_reward_ratio.value
        if current_profit >= tp_pct:
            return f"tp_rr_{self.risk_reward_ratio.value}"

        return None

    # ==================== PLOT CONFIG ====================

    plot_config = {
        "main_plot": {
            "resistance": {"color": "red"},
            "support": {"color": "green"},
        },
        "subplots": {
            "Momentum": {
                "momentum": {"color": "blue"},
            },
            "ADX": {
                "adx": {"color": "purple"},
            },
        },
    }
