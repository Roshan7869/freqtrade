"""
8-13-21 EMA + MACD Trend Engine
================================
Trend-Following / Fibonacci EMA / Momentum Confirmation

Captures sustained crypto momentum by requiring a hierarchical alignment
of Fibonacci EMAs confirmed by MACD momentum, utilizing market structure
for dynamic risk management.

Source: Quant Tactics
Timeframe: 1H
Performance: 500% Return / 18% MDD
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


class EMA8_13_21_MACDStrategy(IStrategy):
    """
    8-13-21 EMA + MACD Trend Engine

    Entry Long: 8>13>21 EMA stack + MACD crosses above Signal
    Entry Short: 8<13<21 EMA stack + MACD crosses below Signal
    Exit: Swing Low/High SL + 2.5:1 RR TP
    """

    INTERFACE_VERSION = 3
    can_short = True

    # ROI handled by custom exit
    minimal_roi = {"0": 100}

    # Wide stoploss - handled by custom_exit
    stoploss = -0.99

    # Timeframe
    timeframe = "1h"

    # Process only new candles
    process_only_new_candles = True

    # Startup candle count
    startup_candle_count: int = 50

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # Fibonacci EMA Lengths
    ema_fast = IntParameter(5, 13, default=8, space="buy", optimize=True)
    ema_mid = IntParameter(8, 21, default=13, space="buy", optimize=True)
    ema_slow = IntParameter(13, 34, default=21, space="buy", optimize=True)

    # MACD Parameters
    macd_fast = IntParameter(10, 14, default=12, space="buy", optimize=False)
    macd_slow = IntParameter(24, 28, default=26, space="buy", optimize=False)
    macd_signal = IntParameter(7, 11, default=9, space="buy", optimize=False)

    # Swing Point Lookback
    swing_lookback = IntParameter(2, 5, default=3, space="sell", optimize=True)

    # Stop Loss Buffer
    sl_buffer_pct = DecimalParameter(
        0.1, 0.8, default=0.3, decimals=1, space="sell", optimize=True
    )

    # Risk Reward Ratio
    risk_reward_ratio = DecimalParameter(
        2.0, 3.5, default=2.5, decimals=1, space="sell", optimize=True
    )

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate EMAs, MACD, and Swing Levels."""

        # Fibonacci EMAs
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe["ema_mid"] = ta.EMA(dataframe, timeperiod=self.ema_mid.value)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow.value)

        # MACD
        macd = ta.MACD(
            dataframe,
            fastperiod=self.macd_fast.value,
            slowperiod=self.macd_slow.value,
            signalperiod=self.macd_signal.value,
        )
        dataframe["macd"] = macd["macd"]
        dataframe["macd_signal"] = macd["macdsignal"]

        # Swing High/Low (for stop loss)
        dataframe["swing_high"] = (
            dataframe["high"].rolling(window=self.swing_lookback.value).max()
        )
        dataframe["swing_low"] = (
            dataframe["low"].rolling(window=self.swing_lookback.value).min()
        )

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long: 8>13>21 EMA stack + MACD crosses above Signal
        Short: 8<13<21 EMA stack + MACD crosses below Signal
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Bullish EMA Stack
        stack_bull = (dataframe["ema_fast"] > dataframe["ema_mid"]) & (
            dataframe["ema_mid"] > dataframe["ema_slow"]
        )

        # Long Entry
        long_conditions = (
            stack_bull
            & qtpylib.crossed_above(dataframe["macd"], dataframe["macd_signal"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "ema_macd_long"

        # Bearish EMA Stack
        stack_bear = (dataframe["ema_fast"] < dataframe["ema_mid"]) & (
            dataframe["ema_mid"] < dataframe["ema_slow"]
        )

        # Short Entry
        short_conditions = (
            stack_bear
            & qtpylib.crossed_below(dataframe["macd"], dataframe["macd_signal"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[short_conditions, "enter_short"] = 1
        dataframe.loc[short_conditions, "enter_tag"] = "ema_macd_short"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """No indicator-based exit - handled by custom_exit."""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    # ==================== RISK MANAGEMENT ====================

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
        Swing-based SL + 2.5:1 RR TP
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None

        # Get entry candle data
        entry_candle = dataframe[dataframe["date"] <= trade.open_date_utc].iloc[-1]

        if not trade.is_short:
            # Long: SL = Swing Low - Buffer
            sl_price = entry_candle["swing_low"] * (1 - self.sl_buffer_pct.value / 100)
            risk = trade.open_rate - sl_price
            tp_price = trade.open_rate + (risk * self.risk_reward_ratio.value)

            if current_rate >= tp_price:
                return f"tp_rr_{self.risk_reward_ratio.value}"
            if current_rate <= sl_price:
                return "sl_swing_low"
        else:
            # Short: SL = Swing High + Buffer
            sl_price = entry_candle["swing_high"] * (1 + self.sl_buffer_pct.value / 100)
            risk = sl_price - trade.open_rate
            tp_price = trade.open_rate - (risk * self.risk_reward_ratio.value)

            if current_rate <= tp_price:
                return f"tp_rr_{self.risk_reward_ratio.value}"
            if current_rate >= sl_price:
                return "sl_swing_high"

        return None

    # ==================== PLOT CONFIG ====================

    plot_config = {
        "main_plot": {
            "ema_fast": {"color": "green"},
            "ema_mid": {"color": "blue"},
            "ema_slow": {"color": "red"},
        },
        "subplots": {
            "MACD": {
                "macd": {"color": "blue"},
                "macd_signal": {"color": "orange"},
            },
        },
    }
