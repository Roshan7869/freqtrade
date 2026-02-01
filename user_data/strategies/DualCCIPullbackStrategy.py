"""
Dual CCI Pullback Engine
=========================
Trend-Following / Mean-Reversion Pullback Hybrid

Captures high-probability entries within a strong trend by using a long-term
CCI to confirm directional bias and a hyper-sensitive short-term CCI to
'snipe' oversold pullbacks.

Source: Quant Tactics
Timeframe: 1H
Performance: 276.5% Return / 14.9% MDD / 2.21 Sharpe
"""

from datetime import datetime
from typing import Optional, Union
import logging

from freqtrade.strategy import IStrategy, Trade
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
    stoploss_from_absolute,
    timeframe_to_prev_date,
)
from pandas import DataFrame
import talib.abstract as ta

logger = logging.getLogger(__name__)


class DualCCIPullbackStrategy(IStrategy):
    """
    Dual CCI Pullback Engine

    Entry Long: Long CCI(110) > 80 + Short CCI(5) crosses above -100 (from below)
    Exit: ATR-based SL + 2:1 RR Take Profit
    """

    INTERFACE_VERSION = 3
    can_short = False  # Long-only pullback strategy

    # ROI handled by custom exit
    minimal_roi = {"0": 100}

    # Wide stoploss - handled by custom_stoploss
    stoploss = -0.99

    # Timeframe
    timeframe = "1h"

    # Process only new candles
    process_only_new_candles = True

    # Startup candle count
    startup_candle_count: int = 120

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # Long-Term CCI (Trend Bias)
    cci_long_length = IntParameter(80, 150, default=110, space="buy", optimize=True)
    cci_long_threshold = IntParameter(50, 120, default=80, space="buy", optimize=True)

    # Short-Term CCI (Entry Trigger)
    cci_short_length = IntParameter(3, 15, default=5, space="buy", optimize=True)
    cci_short_oversold = IntParameter(
        -150, -50, default=-100, space="buy", optimize=True
    )

    # ATR Risk Management
    atr_period = IntParameter(10, 20, default=14, space="sell", optimize=False)
    atr_multiplier = DecimalParameter(
        1.0, 3.0, default=2.0, decimals=1, space="sell", optimize=True
    )
    risk_reward_ratio = DecimalParameter(
        1.5, 3.0, default=2.0, decimals=1, space="sell", optimize=True
    )

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate Long CCI, Short CCI, and ATR."""

        # HLC3 (Typical Price)
        dataframe["hlc3"] = (
            dataframe["high"] + dataframe["low"] + dataframe["close"]
        ) / 3

        # Long-Term CCI (Trend Bias)
        dataframe["cci_long"] = ta.CCI(dataframe, timeperiod=self.cci_long_length.value)

        # Short-Term CCI (Entry Trigger)
        dataframe["cci_short"] = ta.CCI(
            dataframe, timeperiod=self.cci_short_length.value
        )

        # ATR for dynamic stop-loss
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=self.atr_period.value)

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long Entry: Long CCI > 80 + Short CCI crosses above -100 (from below)
        """
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""

        # CCI Short crossed above oversold level (from below)
        cci_recovery = (dataframe["cci_short"] > self.cci_short_oversold.value) & (
            dataframe["cci_short"].shift(1) <= self.cci_short_oversold.value
        )

        # Long Entry Confluence
        long_conditions = (
            (dataframe["cci_long"] > self.cci_long_threshold.value)
            & cci_recovery
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "dual_cci_pullback"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """No indicator-based exit - handled by custom_exit and custom_stoploss."""
        dataframe["exit_long"] = 0
        return dataframe

    # ==================== RISK MANAGEMENT ====================

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float:
        """
        ATR-based dynamic stop-loss.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return -1

        # Get signal candle
        candle_date = timeframe_to_prev_date(self.timeframe, trade.open_date_utc)
        candles = dataframe.loc[dataframe["date"] == candle_date]
        if candles.empty:
            return -1

        candle = candles.iloc[0]
        atr = candle["atr"]

        # SL = Entry - (ATR * Multiplier)
        sl_abs = trade.open_rate - (atr * self.atr_multiplier.value)
        sl_rel = stoploss_from_absolute(sl_abs, current_rate, is_short=False)

        return sl_rel

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
        Take Profit: 2:1 RR (TP = Entry + (Risk * 2))
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None

        # Get signal candle
        candle_date = timeframe_to_prev_date(self.timeframe, trade.open_date_utc)
        candles = dataframe.loc[dataframe["date"] == candle_date]
        if candles.empty:
            return None

        candle = candles.iloc[0]
        atr = candle["atr"]

        # Calculate risk and reward
        risk = atr * self.atr_multiplier.value
        reward = risk * self.risk_reward_ratio.value
        tp_price = trade.open_rate + reward

        if current_rate >= tp_price:
            return f"tp_rr_{self.risk_reward_ratio.value}"

        return None

    # ==================== PLOT CONFIG ====================

    plot_config = {
        "subplots": {
            "CCI Long": {
                "cci_long": {"color": "blue"},
            },
            "CCI Short": {
                "cci_short": {"color": "orange"},
            },
        },
    }
