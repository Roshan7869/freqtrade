"""
Stochastic Momentum Dip-Buyer
==============================
Trend-Following / Mean-Reversion Hybrid

Captures high-probability reversal points within an established trend by
combining long-term structural bias (100 EMA), medium-term momentum (MACD),
and sensitive oversold detection (Stochastic).

Source: Quant Tactics
Timeframe: 15m
Performance: 633% Return (1yr) / 29% MDD / 0.88 Sharpe
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


class StochasticMomentumDipBuyerStrategy(IStrategy):
    """
    Stochastic Momentum Dip-Buyer

    Entry Long: Close > 100 EMA + MACD > Signal + Stochastic crosses above 30
    Entry Short: Close < 100 EMA + MACD < Signal + Stochastic crosses below 75
    Exit: Fixed SL/TP (1:1 RR) + Max Holding Period
    """

    INTERFACE_VERSION = 3
    can_short = True

    # ROI handled by custom exit
    minimal_roi = {"0": 100}

    # Stoploss
    stoploss = -0.10  # Default -10%

    # Timeframe
    timeframe = "15m"

    # Process only new candles
    process_only_new_candles = True

    # Startup candle count
    startup_candle_count: int = 120

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # EMA Trend Bias
    ema_period = IntParameter(50, 200, default=100, space="buy", optimize=True)

    # MACD Parameters (Standard)
    macd_fast = IntParameter(10, 14, default=12, space="buy", optimize=False)
    macd_slow = IntParameter(24, 28, default=26, space="buy", optimize=False)
    macd_signal = IntParameter(7, 11, default=9, space="buy", optimize=False)

    # Stochastic Parameters
    stoch_k = IntParameter(3, 7, default=5, space="buy", optimize=True)
    stoch_d = IntParameter(2, 5, default=3, space="buy", optimize=True)
    stoch_smooth = IntParameter(2, 5, default=3, space="buy", optimize=True)

    # Stochastic Thresholds
    oversold_threshold = IntParameter(20, 30, default=30, space="buy", optimize=True)
    overbought_threshold = IntParameter(70, 80, default=75, space="buy", optimize=True)

    # Risk Management
    stop_loss_pct = DecimalParameter(
        5.0, 15.0, default=10.0, decimals=0, space="sell", optimize=True
    )
    risk_reward_ratio = DecimalParameter(
        1.0, 3.0, default=1.0, decimals=1, space="sell", optimize=True
    )

    # Max Holding Period (in candles, 672 candles @ 15m = 7 days)
    max_holding_candles = IntParameter(
        336, 1008, default=672, space="sell", optimize=True
    )

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate 100 EMA, MACD, and Stochastic."""

        # EMA Trend Bias
        dataframe["ema_100"] = ta.EMA(dataframe, timeperiod=self.ema_period.value)

        # MACD
        macd = ta.MACD(
            dataframe,
            fastperiod=self.macd_fast.value,
            slowperiod=self.macd_slow.value,
            signalperiod=self.macd_signal.value,
        )
        dataframe["macd"] = macd["macd"]
        dataframe["macd_signal"] = macd["macdsignal"]

        # Stochastic
        stoch = ta.STOCH(
            dataframe,
            fastk_period=self.stoch_k.value,
            slowk_period=self.stoch_d.value,
            slowk_matype=0,
            slowd_period=self.stoch_smooth.value,
            slowd_matype=0,
        )
        dataframe["stoch_k"] = stoch["slowk"]
        dataframe["stoch_d"] = stoch["slowd"]

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long Entry: Close > EMA + MACD > Signal + Stochastic crosses above oversold
        Short Entry: Close < EMA + MACD < Signal + Stochastic crosses below overbought
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Long Entry (Dip-Buy in Uptrend)
        long_conditions = (
            (dataframe["close"] > dataframe["ema_100"])
            & (dataframe["macd"] > dataframe["macd_signal"])
            & qtpylib.crossed_above(dataframe["stoch_k"], self.oversold_threshold.value)
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "stoch_dip_buy_long"

        # Short Entry (Bounce-Sell in Downtrend)
        short_conditions = (
            (dataframe["close"] < dataframe["ema_100"])
            & (dataframe["macd"] < dataframe["macd_signal"])
            & qtpylib.crossed_below(
                dataframe["stoch_k"], self.overbought_threshold.value
            )
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[short_conditions, "enter_short"] = 1
        dataframe.loc[short_conditions, "enter_tag"] = "stoch_bounce_sell_short"

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
        1. Take Profit at RR ratio (e.g., 1:1 means TP = SL%)
        2. Max Holding Period
        """

        # Take Profit (RR Ratio)
        tp_pct = (self.stop_loss_pct.value / 100) * self.risk_reward_ratio.value
        if current_profit >= tp_pct:
            return f"tp_rr_{self.risk_reward_ratio.value}"

        # Max Holding Period
        trade_duration = (
            current_time - trade.open_date_utc
        ).total_seconds() / 60  # in minutes
        max_duration_minutes = self.max_holding_candles.value * 15  # 15m candles

        if trade_duration >= max_duration_minutes:
            return "max_hold_7days"

        return None

    # ==================== PLOT CONFIG ====================

    plot_config = {
        "main_plot": {
            "ema_100": {"color": "purple"},
        },
        "subplots": {
            "MACD": {
                "macd": {"color": "blue"},
                "macd_signal": {"color": "red"},
            },
            "Stochastic": {
                "stoch_k": {"color": "blue"},
                "stoch_d": {"color": "orange"},
            },
        },
    }
