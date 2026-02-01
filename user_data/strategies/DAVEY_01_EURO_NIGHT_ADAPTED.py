# pragma pylint: disable=missing-docstring, invalid-name, (pointless-string-statement)
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import datetime
from typing import Optional, Union

from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    CategoricalParameter,
)
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


class DAVEY_01_EURO_NIGHT_ADAPTED(IStrategy):
    """
    DAVEY_01_EURO_NIGHT_ADAPTED

    Source: Building Winning Algorithmic Trading Systems - Kevin J. Davey
    Type: Mean Reversion
    Regime: Low Volatility / Ranging (Asian Session)

    Logic:
      Timeframe: 120m
      Window: 18:00 EST - 07:00 EST (Approx 23:00 UTC - 12:00 UTC)
      Entry Long: Price < Avg(High, 10) - (2.5 * ATR(60))  (Limit Order logic simulated)
      Entry Short: Price > Avg(Low, 10) + (2.5 * ATR(60))
    """

    # Strategy interface version - allow new iterations of the strategy core without requiring major updates
    INTERFACE_VERSION = 3

    # Optimal timeframe for the strategy
    timeframe = "2h"

    # Can this strategy go short?
    can_short = True

    # Minimal ROI designed for the strategy.
    # We use a dynamic exit, but minimal_roi can be a safeguard.
    # Setting high to rely on custom exit logic or stoploss.
    minimal_roi = {"0": 100}

    # Stoploss: 0.5% (~35 ticks on Euro, adapted for crypto)
    stoploss = -0.005

    # Trailing stop: False (Strategy uses fixed stop and dynamic profit target)
    trailing_stop = False

    # Process indicators
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ATR 60 for limit calculations
        dataframe["atr_60"] = ta.ATR(dataframe, timeperiod=60)

        # Avg High 10 and Avg Low 10
        dataframe["avg_high_10"] = ta.SMA(dataframe["high"], timeperiod=10)
        dataframe["avg_low_10"] = ta.SMA(dataframe["low"], timeperiod=10)

        # Entry Prices (Limit levels)
        dataframe["long_limit_price"] = dataframe["avg_high_10"] - (
            2.5 * dataframe["atr_60"]
        )
        dataframe["short_limit_price"] = dataframe["avg_low_10"] + (
            2.5 * dataframe["atr_60"]
        )

        # Exit Logic: Reversion to Mean (10-period SMA)
        dataframe["sma_10"] = ta.SMA(dataframe["close"], timeperiod=10)

        # Filters
        # Volatility Filter: ATR(14) > 2 * Avg(ATR(14), 100)
        dataframe["atr_14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["avg_atr_14_100"] = ta.SMA(dataframe["atr_14"], timeperiod=100)

        # Mark volatile bars
        dataframe["is_volatile"] = dataframe["atr_14"] > (
            2 * dataframe["avg_atr_14_100"]
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Time Filter: 18:00 EST to 07:00 EST
        # Assuming Data is UTC. EST is UTC-5.
        # 18:00 EST = 23:00 UTC
        # 07:00 EST = 12:00 UTC
        # We trade IF current time is >= 23:00 OR <= 12:00 (Asian/Euro Night)

        # Check current hour
        dataframe["hour"] = dataframe["date"].dt.hour

        # Logic:
        # (hour >= 23) OR (hour < 12)

        in_trading_window = (dataframe["hour"] >= 23) | (dataframe["hour"] < 12)

        # Entry Rules
        # Long: Price hits limit order. In backtesting, we check if LOW <= limit_price
        # Short: Price hits limit order. In backtesting, we check if HIGH >= limit_price

        dataframe.loc[
            (
                in_trading_window
                & (dataframe["low"] < dataframe["long_limit_price"])
                & (dataframe["is_volatile"] == False)
            ),
            "enter_long",
        ] = 1

        dataframe.loc[
            (
                in_trading_window
                & (dataframe["high"] > dataframe["short_limit_price"])
                & (dataframe["is_volatile"] == False)
            ),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Initialize exit columns
        dataframe.loc[:, "exit_long"] = 0
        dataframe.loc[:, "exit_short"] = 0

        # Exit Rules
        # Profit Target: Reversion to Mean (SMA 10)

        # Long Exit: Close > SMA 10 (Reverted to mean from below)
        dataframe.loc[(dataframe["close"] > dataframe["sma_10"]), "exit_long"] = 1

        # Short Exit: Close < SMA 10 (Reverted to mean from above)
        dataframe.loc[(dataframe["close"] < dataframe["sma_10"]), "exit_short"] = 1

        # FORCE EXIT at end of trading window (07:00 EST / 12:00 UTC)
        dataframe.loc[(dataframe["hour"] == 12), ["exit_long", "exit_short"]] = 1

        return dataframe

    # Optional: Custom entry price to simulate LIMIT order exactly if using live/dry-run
    def custom_entry_price(
        self,
        pair: str,
        current_time: datetime,
        proposed_rate: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        # We need the dataframe to look up the calculated limit price.
        # This is expensive in backtesting if done every tick, so usually reliance on signal price is enough.
        # However, for correctness:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        if side == "long":
            return last_candle["long_limit_price"]
        else:
            return last_candle["short_limit_price"]
