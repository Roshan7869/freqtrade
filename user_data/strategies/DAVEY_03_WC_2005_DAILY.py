# pragma pylint: disable=missing-docstring, invalid-name, (pointless-string-statement)
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import datetime, timedelta
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


class DAVEY_03_WC_2005_DAILY(IStrategy):
    """
    DAVEY_03_WC_2005_DAILY

    Source: Building Winning Algorithmic Trading Systems - Kevin J. Davey
    Type: Long Term Trend
    Regime: Major Macro Trend
    Logic:
      Timeframe: 1d
      Entry Long: Close > Highest(Close, 48) AND RSI(30) > 50 (Buy Next Open)
      Entry Short: Close < Lowest(Close, 48) AND RSI(30) < 50 (Sell Next Open)
      Exit: Trailing Stop (3 * ATR) OR Hard Stop ($1500 equiv)
      Filters: Psychological Cooldown
    """

    INTERFACE_VERSION = 3
    timeframe = "1d"
    can_short = True

    # Hard stop ($1500 equiv).
    # Since we work in percentages/crypto, we'll map this to a risk percentage.
    # Assuming $1500 on a $100k account = 1.5%. On a $10k account = 15%.
    # For a generic bot, we'll use a fixed conservative % stoploss if wallet unknown,
    # but let's default to 5% hard stop as a placeholder for "$1500".
    stoploss = -0.05

    use_custom_stoploss = True

    # Process indicators
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Highest/Lowest Close 48
        dataframe["highest_close_48"] = dataframe["close"].rolling(window=48).max()
        dataframe["lowest_close_48"] = dataframe["close"].rolling(window=48).min()

        # RSI 30
        dataframe["rsi_30"] = ta.RSI(dataframe, timeperiod=30)

        # ATR 14 for Trailing Stop
        # Note: Prompt said "Trailing Stop (3 * ATR)" - standard ATR length usually 14 or 20.
        dataframe["atr_14"] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Logic:
        # Long: Close > Highest(Close, 48) AND RSI(30) > 50
        # This checks if CURRENT close is higher than PREVIOUS 48 highs?
        # Or including current? Usually breakout means > max(prev 48).

        check_highest = dataframe["highest_close_48"].shift(1)
        check_lowest = dataframe["lowest_close_48"].shift(1)

        dataframe.loc[
            ((dataframe["close"] > check_highest) & (dataframe["rsi_30"] > 50)),
            "enter_long",
        ] = 1

        dataframe.loc[
            ((dataframe["close"] < check_lowest) & (dataframe["rsi_30"] < 50)),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0
        
        # No profit target (Trend Following)
        return dataframe

    def check_entry_timeout(
        self,
        pair: str,
        trade: "Trade",
        order: "Order",
        current_time: datetime,
        **kwargs,
    ) -> bool:
        # No timeout logic specified
        return False

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        # Psychological Filters: Cooldown
        # Loss Cooldown: IF Last_Trade == LOSS, Wait 5 bars (days).
        # Win Cooldown: IF Last_Trade == WIN, Wait 20 bars (days).

        trades = Trade.get_trades_proxy(pair=pair, is_open=False)
        if not trades:
            return True

        last_trade = trades[-1]

        # Calculate bars since close
        # current_time - last_trade.close_date
        # Note: This requires last_trade to have close_date set.

        if last_trade.close_date:
            delta = current_time - last_trade.close_date
            days_passed = delta.days

            if last_trade.close_profit < 0:
                # Loss cooldown: 5 days
                if days_passed < 5:
                    return False
            else:
                # Win cooldown: 20 days
                if days_passed < 20:
                    return False

        return True

    def custom_stoploss(
        self,
        pair: str,
        trade: "Trade",
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        # Trailing Stop: 3 * ATR
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        atr = last_candle["atr_14"]

        stop_dist_pct = (3 * atr) / current_rate

        # Return percentage (negative)
        return -stop_dist_pct
