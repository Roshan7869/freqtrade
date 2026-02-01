"""
RSI-DCA Momentum Scaler Strategy
=================================
Mean-Reversion / Geometric Position Scaling

Uses RSI for precision entry and a safety-order matrix to programmatically
reduce average entry price during drawdown, ensuring profitable exits on
minor price rebounds.

Source: Quant Tactics
Timeframe: 30m
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

logger = logging.getLogger(__name__)


class RSIDCAMomentumScalerStrategy(IStrategy):
    """
    RSI-DCA Momentum Scaler

    Entry: RSI < threshold (oversold)
    Scaling: Geometric DCA (Safety Orders) on drawdown
    Exit: Take Profit based on average entry price
    """

    INTERFACE_VERSION = 3
    can_short = False  # DCA works best for longs

    # ROI disabled - we use custom TP
    minimal_roi = {"0": 100}

    # Wide stoploss - DCA strategy relies on averaging, not tight stops
    stoploss = -0.99

    # Timeframe
    timeframe = "30m"

    # Process only new candles
    process_only_new_candles = True

    # Allow position adjustment (DCA)
    position_adjustment_enable = True

    # Startup candle count
    startup_candle_count: int = 50

    # ==================== HYPEROPTABLE PARAMETERS ====================

    # RSI Parameters
    rsi_period = IntParameter(7, 21, default=14, space="buy", optimize=True)
    rsi_threshold = IntParameter(20, 40, default=30, space="buy", optimize=True)

    # DCA Parameters
    base_order_usdt = DecimalParameter(
        50.0, 200.0, default=100.0, decimals=0, space="buy", optimize=False
    )
    safety_order_ratio = DecimalParameter(
        1.0, 3.0, default=1.5, decimals=1, space="buy", optimize=True
    )
    max_safety_orders = IntParameter(1, 5, default=3, space="buy", optimize=True)
    price_deviation_initial = DecimalParameter(
        1.0, 5.0, default=2.0, decimals=1, space="buy", optimize=True
    )
    volume_scale = DecimalParameter(
        1.2, 3.0, default=2.0, decimals=1, space="buy", optimize=True
    )
    step_scale = DecimalParameter(
        1.0, 2.5, default=1.5, decimals=1, space="buy", optimize=True
    )

    # Take Profit
    take_profit_pct = DecimalParameter(
        2.0, 10.0, default=5.0, decimals=1, space="sell", optimize=True
    )

    # ==================== INDICATORS ====================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate RSI indicator."""
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        return dataframe

    # ==================== ENTRY LOGIC ====================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry: RSI below threshold (oversold condition)
        """
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""

        conditions = (dataframe["rsi"] < self.rsi_threshold.value) & (
            dataframe["volume"] > 0
        )

        dataframe.loc[conditions, "enter_long"] = 1
        dataframe.loc[conditions, "enter_tag"] = (
            f"rsi_oversold_{self.rsi_threshold.value}"
        )

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """No indicator-based exit - handled by custom_exit."""
        dataframe["exit_long"] = 0
        return dataframe

    # ==================== DCA / SAFETY ORDER LOGIC ====================

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
        DCA Logic: Add Safety Orders when price drops below deviation thresholds.

        Returns positive value to add to position, None to do nothing.
        """
        # Count existing orders (initial + DCA orders)
        filled_entries = trade.nr_of_successful_entries

        # Check if we've hit max safety orders
        if filled_entries > self.max_safety_orders.value:
            return None

        # Calculate current deviation threshold
        # For order N, deviation = initial_dev * (step_scale ^ (N-1))
        current_deviation = self.price_deviation_initial.value / 100
        for i in range(1, filled_entries):
            current_deviation *= self.step_scale.value

        # Calculate average entry price
        avg_entry = (
            trade.average_entry_price
            if hasattr(trade, "average_entry_price")
            else trade.open_rate
        )

        # Calculate trigger price for next safety order
        trigger_price = avg_entry * (1 - current_deviation)

        if current_rate <= trigger_price:
            # Calculate order size with geometric scaling
            # Base safety order = base_order * safety_order_ratio
            # Each subsequent = previous * volume_scale
            order_size_usdt = self.base_order_usdt.value * self.safety_order_ratio.value
            for i in range(1, filled_entries):
                order_size_usdt *= self.volume_scale.value

            # Cap at max_stake
            order_size_usdt = min(order_size_usdt, max_stake)

            logger.info(
                f"DCA Order #{filled_entries} for {trade.pair}: "
                f"Price {current_rate:.4f} <= Trigger {trigger_price:.4f}, "
                f"Adding {order_size_usdt:.2f} USDT"
            )

            return order_size_usdt

        return None

    # ==================== TAKE PROFIT LOGIC ====================

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
        Exit when price reaches take_profit_pct above average entry.
        """
        avg_entry = (
            trade.average_entry_price
            if hasattr(trade, "average_entry_price")
            else trade.open_rate
        )
        target_price = avg_entry * (1 + self.take_profit_pct.value / 100)

        if current_rate >= target_price:
            logger.info(
                f"TP Hit for {pair}: Price {current_rate:.4f} >= Target {target_price:.4f} "
                f"(Avg Entry: {avg_entry:.4f}, TP%: {self.take_profit_pct.value}%)"
            )
            return f"tp_{self.take_profit_pct.value}pct"

        return None

    # ==================== STAKE SIZING ====================

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
        """
        Initial entry uses base_order_usdt.
        """
        return min(self.base_order_usdt.value, max_stake)
