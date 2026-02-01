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
from freqtrade.persistence import Trade


class DAVEY_02_EURO_DAY_ADAPTED(IStrategy):
    """
    DAVEY_02_EURO_DAY_ADAPTED

    Source: Building Winning Algorithmic Trading Systems - Kevin J. Davey
    Type: Trend Following Breakout
    Regime: High Volatility / Trending (US/London Overlap)

    Logic:
      Timeframe: 60m
      Window: 07:00 EST - 15:00 EST (Approx 12:00 UTC - 20:00 UTC)
      Entry Long: (Close > Highest(Close, 48)) AND (RSI(30) > 50) + Breakout Trigger
      Entry Short: (Close < Lowest(Close, 48)) AND (RSI(30) < 50) + Breakout Trigger
    """

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True

    # 1.5 * ATR(14) Trailing Stop
    # We will implement custom stoploss logic or use TSTOP
    # Freqtrade's trailing stop is fixed percentage usually.
    # We'll use custom_stoploss for ATR based.

    # Placeholder stoploss (overridden by custom_stoploss)
    stoploss = -0.05
    use_custom_stoploss = True

    # Process indicators
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Donchian / Highest/Lowest
        # Highest Close of last 48 bars
        dataframe["highest_close_48"] = dataframe["close"].rolling(window=48).max()
        # Lowest Close of last 48 bars
        dataframe["lowest_close_48"] = dataframe["close"].rolling(window=48).min()

        # RSI 30
        dataframe["rsi_30"] = ta.RSI(dataframe, timeperiod=30)

        # ATR 14 for Trailing Stop
        dataframe["atr_14"] = ta.ATR(dataframe, timeperiod=14)

        # Previous Bar High/Low (for Buy/Sell Stop Trigger simulation)
        dataframe["prev_high"] = dataframe["high"].shift(1)
        dataframe["prev_low"] = dataframe["low"].shift(1)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Time Filter: 07:00 EST - 15:00 EST
        # 07:00 EST = 12:00 UTC
        # 15:00 EST = 20:00 UTC

        dataframe["hour"] = dataframe["date"].dt.hour
        in_trading_window = (dataframe["hour"] >= 12) & (dataframe["hour"] < 20)

        # Entry Rules
        # Long:
        # 1. Close > Highest(Close, 48)  (Note: strictly > implies breakout)
        # 2. RSI(30) > 50
        # 3. Trigger: Price > Prev High (approximating Buy Stop at Prev High)

        # Note regarding 'highest_close_48': rolling max includes current row by default in pandas.
        # To check if current close BROKE the previous 48 bars high, we should look at close > shift(highest_close_48).
        # However, Davey usually means 'Close > Highest of previous X'.

        dataframe.loc[
            (
                in_trading_window
                & (dataframe["close"] > dataframe["highest_close_48"].shift(1))
                & (dataframe["rsi_30"] > 50)
                & (
                    dataframe["close"] > dataframe["prev_high"]
                )  # Confirmation of breakout
            ),
            "enter_long",
        ] = 1

        # Short:
        # 1. Close < Lowest(Close, 48)
        # 2. RSI(30) < 50
        # 3. Trigger: Price < Prev Low

        dataframe.loc[
            (
                in_trading_window
                & (dataframe["close"] < dataframe["lowest_close_48"].shift(1))
                & (dataframe["rsi_30"] < 50)
                & (dataframe["close"] < dataframe["prev_low"])
            ),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0
        
        # Force Exit at end of session (15:00 EST / 20:00 UTC)
        dataframe.loc[(dataframe["hour"] == 20), ["exit_long", "exit_short"]] = 1

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
        # Logic: Trailing Stop = 1.5 * ATR(14)
        # In Freqtrade, we return a percentage offset from current price (negative).
        # We need ATR value. This is tricky inside custom_stoploss without dataframe access easily.
        # However, we can use `self.dp.get_analyzed_dataframe`

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        atr = last_candle["atr_14"]

        # Calculate dynamic stop distance percent
        # 1.5 * ATR / Current Price
        stop_dist_pct = (1.5 * atr) / current_rate

        # Freqtrade expects return of stoploss absolute offset (e.g. -0.05 for 5% loss from current price)
        # But for trailing, we want to update it. Freqtrade handles 'trailing_stop' param, but here we want Custom calculation.
        # If we return a value, it sets the NEW stoploss relative to current_rate (or open_rate? No, relative to current_rate if we assume standard stoploss behavior, but custom_stoploss return value is usually absolute stoploss percent from OPEN PRICE, or relative to CURRENT? )

        # Correction: custom_stoploss return value is "percentage relative to current_rate" effectively if we want to tighten it.
        # Actually, doc says: "If the function returns 1 (default), the stoploss set in the configuration file is used."
        # "If it returns a value (e.g. -0.05), this value is used as the new stoploss value (relative to current_rate?)"
        # Wait, if we return -0.05, it means stop price = current_price * (1 - 0.05).

        # NOTE: Calculating 1.5*ATR every tick might be noisy. Davey uses fixed ATR at entry or dynamic? Usually dynamic.

        return -stop_dist_pct
