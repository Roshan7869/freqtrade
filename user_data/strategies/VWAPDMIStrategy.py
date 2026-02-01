import sys
import os
from pathlib import Path

# Add the 'strategies' root directory to sys.path to enable absolute imports
def _setup_path():
    p = Path(__file__).resolve()
    for parent in p.parents:
        if parent.name == 'strategies':
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return
_setup_path()
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

import talib.abstract as ta
from technical import qtpylib
import logging

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



logger = logging.getLogger(__name__)


class VWAPDMIStrategy(IStrategy):
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.decision_engine = get_decision_engine()
        self.whale_provider = get_whale_signal_provider()
        self.llm_analyst = get_llm_market_analyst()
        self._active_decision = None

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
        """Decision Layer: Determine leverage via DecisionEngine."""
        if self._active_decision and self._active_decision.entry_tag == entry_tag:
            return self._active_decision.leverage
        return 18.0

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
        """Decision Layer: Synthesize trade size."""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            wallet_balance = self.wallets.get_total_stake_amount()

            tech_signal = TechnicalSignal(
                should_enter=True,
                side="long" if side == "long" else "short",
                score=0.85 if "whale" in (entry_tag or "") else 0.70,
                indicators={},
                reasoning=f"VWAP/DMI Signal ({entry_tag})",
            )

            decision = self.decision_engine.analyze_entry(
                pair=pair,
                technical_signal=tech_signal,
                wallet_balance=wallet_balance,
                market_data=dataframe.tail(20).to_dict(orient="records"),
            )
            self._active_decision = decision

            if decision.action == TradeAction.HOLD:
                return 0.0
            return max(min_stake or 0, min(decision.position_size_usd, max_stake))
        except Exception as e:
            logger.error(f"Stake error: {e}")
            return proposed_stake

    """
    A trend-following strategy using rolling VWAP, DMI, and ADX for entries.
    
    Entry Logic:
    - LONG: Price crosses above VWAP + DI+ > DI- + ADX above threshold
    - SHORT: Price crosses below VWAP + DI- > DI+ + ADX above threshold
    
    Exit Logic:
    - Stop Loss: ATR-based dynamic stoploss (ATR multiplier configurable)
    - Take Profit: Risk-reward ratio based on ATR risk (default 3:1)
    
    Hyperoptable Parameters:
    - vwap_window: Rolling window for VWAP calculation (50-300)
    - adx_threshold: Minimum ADX for trend strength confirmation (15-30)
    - atr_multiplier: ATR multiplier for stop-loss distance (1.0-4.0)
    - risk_reward: Risk-reward ratio for take-profit (1.0-5.0)
    """

    # Strategy interface version
    INTERFACE_VERSION = 3

    # Can this strategy go short?
    can_short: bool = True

    # Minimal ROI (disabled since we use custom TP)
    minimal_roi = {"0": 100}

    # Wide initial stoploss to allow custom dynamic SL
    stoploss = -0.99

    # Trailing stoploss (disabled)
    trailing_stop = False

    # Optimal timeframe for the strategy
    timeframe = "1h"

    # Run "populate_indicators()" only for new candle
    process_only_new_candles = True

    # These values can be overridden in the config
    use_exit_signal = False
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Hyperoptable parameters
    vwap_window = IntParameter(low=50, high=300, default=200, space="buy", optimize=True, load=True)
    adx_threshold = IntParameter(low=15, high=30, default=20, space="buy", optimize=True, load=True)
    atr_multiplier = DecimalParameter(
        low=1.0, high=4.0, default=1.5, decimals=1, space="sell", optimize=True, load=True
    )
    risk_reward = DecimalParameter(
        low=1.0, high=5.0, default=3.0, decimals=1, space="sell", optimize=True, load=True
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

        # ATR (14 periods) for SL/TP calculations
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry logic: VWAP Cross + DMI Trend + Whale Boost."""
        pair = metadata["pair"]
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # 1. Standard technical conditions
        vwap_cross_above = qtpylib.crossed_above(dataframe["close"], dataframe["rolling_vwap"])
        vwap_cross_below = qtpylib.crossed_below(dataframe["close"], dataframe["rolling_vwap"])

        long_tech = (
            vwap_cross_above
            & (dataframe["plus_di"] > dataframe["minus_di"])
            & (dataframe["adx"] > 25)
            & (dataframe["volume"] > 0)
        )
        short_tech = (
            vwap_cross_below
            & (dataframe["minus_di"] > dataframe["plus_di"])
            & (dataframe["adx"] > 25)
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_tech, "enter_long"] = 1
        dataframe.loc[long_tech, "enter_tag"] = "technical_vwap_trend"
        dataframe.loc[short_tech, "enter_short"] = 1
        dataframe.loc[short_tech, "enter_tag"] = "technical_vwap_trend"

        # 2. Intelligent Layer: Whale Boost
        whale_signal = self.whale_provider.get_signal(pair)
        if whale_signal:
            if whale_signal.signal_type == "BUY":
                # Relaxed: Only need VWAP cross above if whale is buying
                whale_long = vwap_cross_above & (dataframe["volume"] > 0)
                dataframe.loc[whale_long, "enter_long"] = 1
                dataframe.loc[whale_long, "enter_tag"] = "whale_boost_vwap"
            elif whale_signal.signal_type == "SELL":
                whale_short = vwap_cross_below & (dataframe["volume"] > 0)
                dataframe.loc[whale_short, "enter_short"] = 1
                dataframe.loc[whale_short, "enter_tag"] = "whale_boost_vwap"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        No indicator-based exits; handled via custom_exit for TP.
        """
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

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
        Custom stoploss with TRAILING STOP activation.
        Returns relative stoploss (negative value).
        """
        # TRAILING STOP - Activate after profit threshold
        if current_profit > 0.02:  # 2% profit
            return -0.004  # Trail at 0.4%
        elif current_profit > 0.01:  # 1% profit
            return -0.007  # Trail at 0.7%
        elif current_profit > 0.005:  # 0.5% profit
            return -0.01  # Trail at 1%

        # Initial ATR-based SL
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return -1

        candle_date = timeframe_to_prev_date(self.timeframe, trade.open_date_utc)
        candles = dataframe.loc[dataframe["date"] == candle_date]
        if candles.empty:
            return -1

        candle = candles.iloc[0]
        atr = candle["atr"]
        entry_price = trade.open_rate

        if not trade.is_short:
            sl_abs = entry_price - (self.atr_multiplier.value * atr)
        else:
            sl_abs = entry_price + (self.atr_multiplier.value * atr)

        sl_rel = stoploss_from_absolute(sl_abs, current_rate, is_short=trade.is_short)
        return sl_rel

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> Optional[Union[str, bool]]:
        """
        Custom exit: Check if current profit hits target RR based on ATR risk.
        Returns 'tp_hit' to exit, or None to continue.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None

        candle_date = timeframe_to_prev_date(self.timeframe, trade.open_date_utc)
        candles = dataframe.loc[dataframe["date"] == candle_date]
        if candles.empty:
            return None

        candle = candles.iloc[0]
        atr = candle["atr"]
        entry_price = trade.open_rate

        if not trade.is_short:
            sl_abs = entry_price - (self.atr_multiplier.value * atr)
            risk = (entry_price - sl_abs) / entry_price
        else:
            sl_abs = entry_price + (self.atr_multiplier.value * atr)
            risk = (sl_abs - entry_price) / entry_price

        target_profit = self.risk_reward.value * risk

        if current_profit >= target_profit:
            return "tp_hit"

        return None

