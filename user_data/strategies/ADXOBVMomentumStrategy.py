"""
ADX-OBV Momentum Engine (336% Profit)
======================================
Trend-Following / Volume-Flow Confirmation

Utilizes a confluence of trend strength (ADX), directional momentum (DI),
and volume flow (OBV) to capture high-probability crypto trends while
avoiding ranging markets.

Source: Quant Tactics
Timeframe: 1H
Performance: 336% Return / 23% MDD
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
from technical import qtpylib

logger = logging.getLogger(__name__)


class ADXOBVMomentumStrategy(IStrategy):
    """
    ADX-OBV Momentum Engine

    Entry Long: ADX > 25 + +DI crosses above -DI + OBV > OBV SMA
    Entry Short: ADX > 25 + -DI crosses above +DI + OBV < OBV SMA
    Exit: ATR-based SL + 1.5:1 RR TP
    """

    INTERFACE_VERSION = 3
    can_short = True

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

    # ADX Threshold
    adx_threshold = IntParameter(20, 30, default=25, space="buy", optimize=True)

    # OBV SMA Period
    obv_sma_period = IntParameter(50, 200, default=100, space="buy", optimize=True)

    # ATR Risk Management
    atr_period = IntParameter(10, 20, default=14, space="sell", optimize=False)
    atr_multiplier = DecimalParameter(
        1.5, 3.0, default=2.0, decimals=1, space="sell", optimize=True
    )
    risk_reward_ratio = DecimalParameter(
        1.0, 2.5, default=1.5, decimals=1, space="sell", optimize=True
    )

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate ADX, DI+/-, OBV, and ATR."""

        # ADX and Directional Indicators
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["di_plus"] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe["di_minus"] = ta.MINUS_DI(dataframe, timeperiod=14)

        # On-Balance Volume
        dataframe["obv"] = ta.OBV(dataframe)
        dataframe["obv_sma"] = ta.SMA(
            dataframe["obv"], timeperiod=self.obv_sma_period.value
        )

        # ATR for risk management
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=self.atr_period.value)

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long: ADX > 25 + +DI crosses above -DI + OBV > OBV SMA
        Short: ADX > 25 + -DI crosses above +DI + OBV < OBV SMA
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Long Entry
        long_conditions = (
            (dataframe["adx"] > self.adx_threshold.value)
            & qtpylib.crossed_above(dataframe["di_plus"], dataframe["di_minus"])
            & (dataframe["obv"] > dataframe["obv_sma"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "adx_obv_long"

        # Short Entry
        short_conditions = (
            (dataframe["adx"] > self.adx_threshold.value)
            & qtpylib.crossed_above(dataframe["di_minus"], dataframe["di_plus"])
            & (dataframe["obv"] < dataframe["obv_sma"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[short_conditions, "enter_short"] = 1
        dataframe.loc[short_conditions, "enter_tag"] = "adx_obv_short"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """No indicator-based exit - handled by custom_exit."""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
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
        ATR-based stop loss: Entry ± (2.0 × ATR)
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

        if not trade.is_short:
            sl_abs = trade.open_rate - (atr * self.atr_multiplier.value)
        else:
            sl_abs = trade.open_rate + (atr * self.atr_multiplier.value)

        sl_rel = stoploss_from_absolute(sl_abs, current_rate, is_short=trade.is_short)
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
        Take Profit: 1.5:1 RR
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

        if not trade.is_short:
            tp_price = trade.open_rate + reward
            if current_rate >= tp_price:
                return f"tp_rr_{self.risk_reward_ratio.value}"
        else:
            tp_price = trade.open_rate - reward
            if current_rate <= tp_price:
                return f"tp_rr_{self.risk_reward_ratio.value}"

        return None

    # ==================== PLOT CONFIG ====================

    plot_config = {
        "subplots": {
            "ADX": {
                "adx": {"color": "blue"},
            },
            "DI": {
                "di_plus": {"color": "green"},
                "di_minus": {"color": "red"},
            },
            "OBV": {
                "obv": {"color": "purple"},
                "obv_sma": {"color": "orange"},
            },
        },
    }
