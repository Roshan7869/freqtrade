# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these imports ---
from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from pandas import DataFrame
from typing import Optional, Union

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    PairLocks,
    informative,  # @informative decorator
    # Hyperopt Parameters
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    RealParameter,
    # timeframe helpers
    timeframe_to_minutes,
    timeframe_to_next_date,
    timeframe_to_prev_date,
    # Strategy helper functions
    merge_informative_pair,
    stoploss_from_absolute,
    stoploss_from_open,
)

# --------------------------------
# Add your lib to import here
import talib.abstract as ta
from technical import qtpylib


class DCAMartingaleStrategy(IStrategy):
    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        return 27.0

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
        msg = (
            f"?? <b>ALARM! Trade Entry Detected</b> ??\n"
            f"Strategy: {self.config['strategy']}\n"
            f"Pair: {pair}\n"
            f"Side: {side}\n"
            f"Rate: {rate}\n"
            f"?? <b>ACT FAST!</b> ??"
        )
        self.dp.send_msg(msg)
        return True

    """
    A Spot DCA + Martingale strategy for crypto trading.
    
    Initial Entry:
    - Based on VWAP crossover + DMI confirmation (DI+ > DI-) + ADX strength
    
    DCA/Safety Orders:
    - Adds safety orders on price drops using Martingale-style scaling
    - Each safety order uses scaled volume and step deviation
    
    Exit Logic:
    - Take profit based on percentage above average entry price
    
    Risk Management:
    - No stop-loss (DCA strategy accumulates on drops)
    - Maximum safety orders limit exposure
    
    Hyperoptable Parameters:
    - vwap_window: Rolling window for VWAP calculation (50-300)
    - adx_threshold: Minimum ADX for trend strength confirmation (15-30)
    - initial_deviation: First safety order trigger deviation % (0.5-5.0)
    - safety_size: Base safety order size in stake currency (10-200)
    - volume_scale: Martingale volume multiplier per safety order (1.1-3.0)
    - step_scale: Martingale step multiplier per safety order (1.1-3.0)
    - max_safety_orders: Maximum number of safety orders (1-10)
    - take_profit: Take profit percentage above average entry (0.5-5.0)
    """

    # Strategy interface version
    INTERFACE_VERSION = 3

    # Can this strategy go short? (Spot, so long only)
    can_short: bool = False

    # Minimal ROI (disabled since we use custom TP)
    minimal_roi = {"0": 100}

    # Wide initial stoploss to avoid early exits (DCA needs room to accumulate)
    stoploss = -0.99

    # Trailing stoploss (disabled)
    trailing_stop = False

    # Optimal timeframe for the strategy
    timeframe = "5m"

    # Run "populate_indicators()" only for new candle
    process_only_new_candles = True

    # These values can be overridden in the config
    use_exit_signal = False  # No indicator-based exits; use custom_exit for TP
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Hyperoptable parameters for VWAP/DMI entry
    vwap_window = IntParameter(
        low=50, high=300, default=200, space="buy", optimize=True, load=True
    )
    adx_threshold = IntParameter(
        low=15, high=30, default=20, space="buy", optimize=True, load=True
    )

    # Hyperoptable parameters for DCA/Martingale
    initial_deviation = DecimalParameter(
        low=0.5,
        high=5.0,
        default=3.0,
        decimals=1,
        space="buy",
        optimize=True,
        load=True,
    )
    safety_size = DecimalParameter(
        low=10.0,
        high=200.0,
        default=75.0,
        decimals=1,
        space="buy",
        optimize=True,
        load=True,
    )
    volume_scale = DecimalParameter(
        low=1.1,
        high=3.0,
        default=2.0,
        decimals=1,
        space="buy",
        optimize=True,
        load=True,
    )
    step_scale = DecimalParameter(
        low=1.1,
        high=3.0,
        default=2.0,
        decimals=1,
        space="buy",
        optimize=True,
        load=True,
    )
    max_safety_orders = IntParameter(
        low=1, high=10, default=5, space="buy", optimize=True, load=True
    )
    take_profit = DecimalParameter(
        low=0.5,
        high=5.0,
        default=1.0,
        decimals=1,
        space="sell",
        optimize=True,
        load=True,
    )

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 200

    # Optional order type mapping
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Optional order time in force
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    def informative_pairs(self):
        """Define additional informative pair/interval combinations."""
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds VWAP, DMI, ADX, and ATR indicators to the dataframe.
        ATR is included for potential future SL enhancements.
        """
        # Rolling VWAP (using typical price weighted by volume)
        tp = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3
        dataframe["rolling_vwap"] = (tp * dataframe["volume"]).rolling(
            window=self.vwap_window.value
        ).sum() / dataframe["volume"].rolling(window=self.vwap_window.value).sum()

        # DMI and ADX (14 periods)
        dataframe["plus_di"] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe["minus_di"] = ta.MINUS_DI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # ATR (14 periods) - optional for future enhancements
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populates entry signals based on VWAP crossover, DMI, and ADX (long only).

        Entry Conditions:
        - Price crosses above rolling VWAP
        - DI+ > DI- (bullish directional movement)
        - ADX > threshold (strong trend)
        - Volume > 0 (basic volume filter)
        """
        dataframe.loc[
            (
                qtpylib.crossed_above(dataframe["close"], dataframe["rolling_vwap"])
                & (dataframe["plus_di"] > dataframe["minus_di"])
                & (dataframe["adx"] > self.adx_threshold.value)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        No indicator-based exits; handled via custom_exit for TP.
        """
        dataframe["exit_long"] = 0
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
        Adjust position by adding safety orders on price drops.
        Uses Martingale scaling for volume and steps.

        Logic:
        - Tracks safety order count and last buy price in trade.extra_info
        - Calculates trigger price based on deviation and step scale
        - When price drops below trigger, adds scaled safety order

        Returns additional stake (in stake currency) to buy more, or None.
        """
        # Initialize extra_info on first call
        if "safety_count" not in trade.extra_info:
            trade.extra_info["safety_count"] = 0
            trade.extra_info["last_buy_price"] = trade.open_rate

        safety_count = trade.extra_info["safety_count"]

        # Check if max safety orders reached
        if safety_count >= self.max_safety_orders.value:
            return None

        # Calculate trigger price for next safety order
        # Each subsequent order triggers at a larger deviation from last buy
        deviation = (self.initial_deviation.value / 100) * (
            self.step_scale.value**safety_count
        )
        trigger_price = trade.extra_info["last_buy_price"] * (1 - deviation)

        # Check if price has dropped enough to trigger safety order
        if current_rate > trigger_price:
            return None

        # Calculate additional stake with Martingale volume scaling
        vol_mult = self.volume_scale.value**safety_count
        additional_stake = self.safety_size.value * vol_mult

        # Cap to available stake
        available_stake = min(additional_stake, max_stake)
        if min_stake is not None and available_stake < min_stake:
            return None

        # Update tracking info for next safety order
        trade.extra_info["safety_count"] = safety_count + 1
        trade.extra_info["last_buy_price"] = current_rate

        return available_stake

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
        Custom exit: Check if current profit hits take-profit target.

        Exit when profit percentage exceeds take_profit threshold.
        The profit is calculated based on average entry price (DCA average).

        Returns 'tp_hit' to exit, or None to continue.
        """
        if current_profit >= (self.take_profit.value / 100):
            return "tp_hit"

        return None
