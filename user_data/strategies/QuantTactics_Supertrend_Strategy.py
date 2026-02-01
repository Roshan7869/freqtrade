# pragma pylint: disable=missing-docstring, invalid-name, (pointless-string-statement)
# flake8: noqa: F401
# isort: skip_file
import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import datetime
from typing import Optional

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
import talib.abstract as ta

# Intelligent & Decision Layers (with mock fallback for backtesting)
try:
    from signal_layer.src.providers.whale_signal_provider import get_whale_signal_provider
    from analysis_layer.src.regime.llm_market_analyst import get_llm_market_analyst
    from decision_layer.src.engine.decision_engine import get_decision_engine
    from decision_layer.src.protocol.models import TechnicalSignal, TradeAction
except ImportError:
    # Mock providers for standalone backtesting
    class MockProvider:
        def get_signal(self, pair):
            return None
    class MockAnalyst:
        is_enabled = False
        def get_market_regime(self, *args):
            return None
    class MockDecisionEngine:
        def analyze_entry(self, **kwargs):
            class Decision:
                action = None
                position_size_usd = 999999
                leverage = 18.0
                entry_tag = "mock"
            return Decision()
    def get_whale_signal_provider():
        return MockProvider()
    def get_llm_market_analyst():
        return MockAnalyst()
    def get_decision_engine():
        return MockDecisionEngine()
    class TechnicalSignal:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    class TradeAction:
        HOLD = "HOLD"
        BUY = "BUY"
        SELL = "SELL"

import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.persistence import Trade


class QuantTactics_Supertrend_Strategy(IStrategy):
    """
    Quant Tactics - Supertrend Momentum Strategy
    ============================================
    Source: Quant Tactics (Freqtrade optimization expert)

    Objective: Isolate high-probability trending moves while neutralizing chop losses.

    Core Indicators:
    - Supertrend (11, 4): ATR-based trend bias
    - Momentum: Zero-lag velocity measurement
    - Choppiness Index: Market efficiency filter (< 50 = trending)
    - ATR: Volatility-based stops

    Risk Management: 2.5 ATR stop, 2.5 R:R target
    """

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True

    # Fixed ROI (rely on TP/SL from custom logic)
    minimal_roi = {"0": 100}

    # Stop loss (handled by custom_stoploss with ATR)
    stoploss = -0.10  # Safety net
    use_custom_stoploss = True

    # Hyperopt parameters
    supertrend_length = IntParameter(8, 14, default=11, space="buy")
    supertrend_multiplier = DecimalParameter(
        2.0, 6.0, default=4.0, decimals=1, space="buy"
    )
    chop_threshold = DecimalParameter(40, 60, default=50, decimals=0, space="buy")

    # For tracking entry price and targets
    custom_info = {}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 1. Supertrend
        dataframe["supertrend"] = self.supertrend(
            dataframe,
            length=int(self.supertrend_length.value),
            multiplier=self.supertrend_multiplier.value,
        )

        # 2. Momentum (Rate of Change)
        dataframe["momentum"] = ta.MOM(dataframe, timeperiod=14)

        # 3. Choppiness Index
        dataframe["chop"] = self.choppiness_index(dataframe, period=14)

        # 4. ATR for stops
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    def supertrend(
        self, dataframe: DataFrame, length: int = 11, multiplier: float = 4.0
    ) -> pd.Series:
        """
        Calculate Supertrend indicator
        Returns the trend line (support/resistance)
        """
        high = dataframe["high"]
        low = dataframe["low"]
        close = dataframe["close"]

        # ATR
        atr = ta.ATR(dataframe, timeperiod=length)

        # Basic Upper/Lower Bands
        hl_avg = (high + low) / 2
        upper_band = hl_avg + (multiplier * atr)
        lower_band = hl_avg - (multiplier * atr)

        # Supertrend calculation
        supertrend = pd.Series(index=dataframe.index, dtype="float64")
        direction = pd.Series(index=dataframe.index, dtype="int64")

        for i in range(1, len(dataframe)):
            if pd.isna(atr.iloc[i]):
                continue

            # Initial values
            if i == 1:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
                continue

            # Update bands based on previous supertrend
            curr_upper = upper_band.iloc[i]
            curr_lower = lower_band.iloc[i]
            prev_supertrend = supertrend.iloc[i - 1]

            if curr_lower > prev_supertrend or close.iloc[i - 1] < prev_supertrend:
                curr_lower = curr_lower
            else:
                curr_lower = prev_supertrend

            if curr_upper < prev_supertrend or close.iloc[i - 1] > prev_supertrend:
                curr_upper = curr_upper
            else:
                curr_upper = prev_supertrend

            # Determine direction and supertrend value
            if close.iloc[i] <= curr_upper:
                supertrend.iloc[i] = curr_upper
                direction.iloc[i] = -1
            else:
                supertrend.iloc[i] = curr_lower
                direction.iloc[i] = 1

        return supertrend

    def choppiness_index(self, dataframe: DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Choppiness Index
        < 50 = Trending
        > 50 = Choppy/Ranging
        """
        high = dataframe["high"]
        low = dataframe["low"]
        close = dataframe["close"]

        tr = ta.TRANGE(dataframe)
        atr_sum = tr.rolling(window=period).sum()

        high_max = high.rolling(window=period).max()
        low_min = low.rolling(window=period).min()

        chop = 100 * np.log10(atr_sum / (high_max - low_min)) / np.log10(period)

        return chop

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long Entry: Close > Supertrend AND Momentum > 0 AND Chop < 50
        long_condition = (
            (dataframe["close"] > dataframe["supertrend"])
            & (dataframe["momentum"] > 0)
            & (dataframe["chop"] < self.chop_threshold.value)
        )

        dataframe.loc[long_condition, "enter_long"] = 1
        dataframe.loc[long_condition, "enter_tag"] = "st_mom_long"

        # Short Entry: Close < Supertrend AND Momentum < 0 AND Chop < 50
        short_condition = (
            (dataframe["close"] < dataframe["supertrend"])
            & (dataframe["momentum"] < 0)
            & (dataframe["chop"] < self.chop_threshold.value)
        )

        dataframe.loc[short_condition, "enter_short"] = 1
        dataframe.loc[short_condition, "enter_tag"] = "st_mom_short"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0
        
        # Exits handled by custom_stoploss/custom_exit (TP/SL logic)
        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade: "Trade",
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        # Calculate ATR-based stop
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        atr = last_candle.get("atr", 0)

        if atr == 0:
            return self.stoploss

        # 2.5 ATR stop distance
        stop_distance = (2.5 * atr) / trade.open_rate

        return -stop_distance

    def custom_exit(
        self,
        pair: str,
        trade: "Trade",
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        # Take Profit: 2.5 R:R
        # R = 2.5 ATR (stop distance)
        # TP = Entry + (2.5 * R) for longs, Entry - (2.5 * R) for shorts

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        # Get entry candle ATR (approximate with current)
        last_candle = dataframe.iloc[-1].squeeze()
        atr = last_candle.get("atr", 0)

        if atr == 0:
            return None

        entry_price = trade.open_rate
        is_long = trade.is_short == False

        # Calculate TP
        r = 2.5 * atr

        if is_long:
            tp_price = entry_price + (2.5 * r)
            if current_rate >= tp_price:
                return "st_mom_tp_long"
        else:
            tp_price = entry_price - (2.5 * r)
            if current_rate <= tp_price:
                return "st_mom_tp_short"

        return None
