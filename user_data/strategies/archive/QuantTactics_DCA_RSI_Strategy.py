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

from freqtrade.persistence import Trade


class QuantTactics_DCA_RSI_Strategy(IStrategy):
    """
    Quant Tactics - DCA RSI Strategy
    =================================
    Source: Quant Tactics (Freqtrade DCA expert)

    Objective: Average down during pullbacks using RSI oversold signals.

    DCA Logic:
    - Base order on RSI < threshold
    - Safety orders on price drops (geometric scaling)
    - Take profit at avg_entry + X%

    Parameters:
    - Base order size
    - Safety order ratio & volume scale
    - Price deviation & step scale
    - Max safety orders

    Performance: 50%+ returns vs negative buy-hold in bear markets
    """

    INTERFACE_VERSION = 3
    timeframe = "30m"
    can_short = False  # DCA typically long-only

    # Disable default ROI/stoploss (using custom logic)
    minimal_roi = {"0": 100}
    stoploss = -0.99  # Very wide, rely on DCA

    # RSI Parameters
    rsi_period = IntParameter(10, 20, default=14, space="buy")
    rsi_threshold = DecimalParameter(20, 40, default=30, decimals=0, space="buy")

    # DCA Parameters
    # Note: In Freqtrade, stake amount is controlled by config, but we can use adjust_trade_position
    max_safety_orders = IntParameter(1, 5, default=3, space="buy")
    price_deviation_pct = DecimalParameter(
        1.0, 5.0, default=2.0, decimals=1, space="buy"
    )  # Initial deviation
    safety_order_volume_scale = DecimalParameter(
        1.0, 2.5, default=2.0, decimals=1, space="buy"
    )
    safety_order_step_scale = DecimalParameter(
        1.0, 2.0, default=1.0, decimals=1, space="buy"
    )
    take_profit_pct = DecimalParameter(3.0, 10.0, default=5.0, decimals=1, space="sell")

    # Track DCA state per trade
    position_adjustment_enable = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI for entry
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=int(self.rsi_period.value))

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Entry: RSI below threshold (oversold)
        entry_condition = dataframe["rsi"] < self.rsi_threshold.value

        dataframe.loc[entry_condition, "enter_long"] = 1
        dataframe.loc[entry_condition, "enter_tag"] = "dca_rsi_entry"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exits handled by custom_exit (TP based on avg entry)
        return dataframe

    def adjust_trade_position(
        self,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        min_stake: Optional[float],
        max_stake: float,
        current_entry_rate: float,
        current_exit_rate: float,
        current_entry_profit: float,
        current_exit_profit: float,
        **kwargs,
    ) -> Optional[float]:
        """
        DCA Logic: Add to position when price drops

        Returns: stake amount to add (None = no action)
        """

        # Don't add if we've hit max safety orders
        if trade.nr_of_successful_entries >= (
            self.max_safety_orders.value + 1
        ):  # +1 for base order
            return None

        # Calculate how many safety orders already placed
        safety_orders_placed = trade.nr_of_successful_entries - 1

        # Calculate required deviation for next order
        # First safety order at price_deviation_pct%, then scaled by step_scale
        if safety_orders_placed == 0:
            required_deviation_pct = self.price_deviation_pct.value
        else:
            # Each subsequent order requires larger deviation
            required_deviation_pct = self.price_deviation_pct.value * (
                self.safety_order_step_scale.value**safety_orders_placed
            )

        # Check if current price dropped enough
        avg_entry = trade.open_rate  # Freqtrade auto-calculates weighted avg
        deviation_pct = ((avg_entry - current_rate) / avg_entry) * 100

        if deviation_pct >= required_deviation_pct:
            # Calculate next order size
            # First safety order: base_stake * safety_ratio
            # Subsequent: previous_size * volume_scale

            # Get base stake from first order
            base_stake = (
                trade.stake_amount / trade.nr_of_successful_entries
            )  # Approximate

            if safety_orders_placed == 0:
                # First safety order
                next_stake = (
                    base_stake * 1.0
                )  # Can add safety_order_ratio param if needed
            else:
                # Geometric scaling
                next_stake = base_stake * (
                    self.safety_order_volume_scale.value**safety_orders_placed
                )

            # Ensure within limits
            next_stake = max(min_stake or 0, min(next_stake, max_stake))

            return next_stake

        return None

    def custom_exit(
        self,
        pair: str,
        trade: "Trade",
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        # Take Profit: avg_entry + take_profit_pct%
        avg_entry = trade.open_rate
        tp_price = avg_entry * (1 + self.take_profit_pct.value / 100)

        if current_rate >= tp_price:
            return f"dca_tp_{self.take_profit_pct.value}pct"

        return None

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: Optional[float],
        max_stake: float,
        leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        # Use proposed stake for base order (controlled by config)
        return proposed_stake
