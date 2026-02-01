"""
ALMA + MACD Momentum Cross Strategy
====================================
Trend-Following / Momentum Confirmation

Utilizes the low-latency, smooth response of ALMA for trend detection
and MACD for momentum verification to capture major crypto trends
while minimizing whipsaws.

Source: Quant Tactics
Timeframe: 1H
"""

from datetime import datetime
from typing import Optional, Union
import logging
import numpy as np

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


def alma(series, length=9, sigma=6.0, offset=0.85):
    """
    Arnaud Legoux Moving Average (ALMA)

    A Gaussian-weighted moving average that balances smoothness and responsiveness.

    Parameters:
    - length: Lookback window
    - sigma: Controls smoothness (smaller = more reactive)
    - offset: Controls timing (closer to 1 = prioritize recent prices)
    """
    m = offset * (length - 1)
    s = length / sigma

    weights = np.array([np.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(length)])
    weights = weights / weights.sum()

    result = series.rolling(window=length).apply(
        lambda x: np.sum(x * weights), raw=True
    )
    return result


class ALMAMACDMomentumCrossStrategy(IStrategy):
    """
    ALMA + MACD Momentum Cross

    Entry: Price > ALMA AND MACD crosses above Signal
    Exit: ATR-based Stop Loss (3x ATR) and Take Profit (2.5x Risk)

    The Golden Rule: Never trade ALMA in isolation; MACD filter prevents fake moves.
    """

    INTERFACE_VERSION = 3
    can_short = True

    # ROI disabled - we use custom TP
    minimal_roi = {"0": 100}

    # Wide stoploss - handled by custom_stoploss
    stoploss = -0.99

    # Timeframe
    timeframe = "1h"

    # Process only new candles
    process_only_new_candles = True

    # Startup candle count
    startup_candle_count: int = 100

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # ALMA Parameters
    alma_length = IntParameter(5, 50, default=21, space="buy", optimize=True)
    alma_sigma = DecimalParameter(
        2.0, 10.0, default=6.0, decimals=1, space="buy", optimize=True
    )
    alma_offset = DecimalParameter(
        0.5, 1.0, default=0.85, decimals=2, space="buy", optimize=True
    )

    # MACD Parameters (Standard 12, 26, 9)
    macd_fast = IntParameter(8, 16, default=12, space="buy", optimize=True)
    macd_slow = IntParameter(20, 30, default=26, space="buy", optimize=True)
    macd_signal = IntParameter(7, 12, default=9, space="buy", optimize=True)

    # ATR Risk Management
    atr_period = IntParameter(10, 20, default=14, space="sell", optimize=False)
    atr_sl_multiplier = DecimalParameter(
        2.0, 4.0, default=3.0, decimals=1, space="sell", optimize=True
    )
    risk_reward_ratio = DecimalParameter(
        1.5, 3.5, default=2.5, decimals=1, space="sell", optimize=True
    )

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate ALMA, MACD, and ATR indicators."""

        # ALMA
        dataframe["alma"] = alma(
            dataframe["close"],
            length=self.alma_length.value,
            sigma=self.alma_sigma.value,
            offset=self.alma_offset.value,
        )

        # MACD
        macd = ta.MACD(
            dataframe,
            fastperiod=self.macd_fast.value,
            slowperiod=self.macd_slow.value,
            signalperiod=self.macd_signal.value,
        )
        dataframe["macd"] = macd["macd"]
        dataframe["macd_signal"] = macd["macdsignal"]
        dataframe["macd_hist"] = macd["macdhist"]

        # ATR for risk management
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=self.atr_period.value)

        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Long Entry: Close > ALMA AND MACD crosses above Signal
        Short Entry: Close < ALMA AND MACD crosses below Signal
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Long conditions
        long_conditions = (
            (dataframe["close"] > dataframe["alma"])
            & qtpylib.crossed_above(dataframe["macd"], dataframe["macd_signal"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "alma_macd_bull"

        # Short conditions
        short_conditions = (
            (dataframe["close"] < dataframe["alma"])
            & qtpylib.crossed_below(dataframe["macd"], dataframe["macd_signal"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[short_conditions, "enter_short"] = 1
        dataframe.loc[short_conditions, "enter_tag"] = "alma_macd_bear"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """No indicator-based exit - handled by custom_exit and custom_stoploss."""
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
        ATR-based Stop Loss: 3x ATR from entry.
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
        risk = self.atr_sl_multiplier.value * atr

        if not trade.is_short:
            sl_abs = trade.open_rate - risk
        else:
            sl_abs = trade.open_rate + risk

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
        Take Profit: 2.5x Risk (Risk-Reward Ratio)
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
        risk = self.atr_sl_multiplier.value * atr
        reward = self.risk_reward_ratio.value * risk

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
        "main_plot": {
            "alma": {"color": "orange"},
        },
        "subplots": {
            "MACD": {
                "macd": {"color": "blue"},
                "macd_signal": {"color": "red"},
            },
        },
    }
