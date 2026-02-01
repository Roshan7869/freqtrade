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
"""
Whale Momentum Strategy
Combines whale tracking signals with AroonMACD indicators for high-confidence trades.

This strategy reads whale signals from a JSON file or REST API and only enters trades
when both whale activity AND technical momentum indicators confirm the direction.
"""


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

import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import datetime
from typing import Optional, Union
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    PairLocks,
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    timeframe_to_minutes,
    timeframe_to_next_date,
    timeframe_to_prev_date,
    merge_informative_pair,
    stoploss_from_absolute,
    stoploss_from_open,
)

import talib.abstract as ta
from technical import qtpylib

logger = logging.getLogger(__name__)


class WhaleMomentumStrategy(IStrategy):
    """
    Hybrid strategy combining whale tracking signals with AroonMACD momentum.

    Entry Logic:
    - LONG: Whale BUY signal + AroonUp crosses above AroonDown + MACD bullish
    - SHORT: Whale SELL signal + AroonUp crosses below AroonDown + MACD bearish

    The whale signal must have confidence >= min_whale_confidence and be within
    the signal TTL window to be considered valid.
    """

    INTERFACE_VERSION = 3
    can_short: bool = True

    # Minimal ROI (disabled - use custom exit)
    minimal_roi = {"0": 100}

    # Wide stoploss (handled by custom_stoploss)
    stoploss = -0.99

    # Trailing stop disabled
    trailing_stop = False

    # Optimal timeframe
    timeframe = "1h"

    # Process only new candles
    process_only_new_candles = True

    # Exit configuration
    use_exit_signal = False
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # ========== WHALE SIGNAL PARAMETERS ==========

    # Minimum confidence required from whale signal
    min_whale_confidence = DecimalParameter(
        low=0.5, high=0.95, default=0.70, decimals=2, space="buy", optimize=True, load=True
    )

    # Maximum age of whale signal in minutes
    whale_signal_ttl = IntParameter(
        low=5, high=60, default=10, space="buy", optimize=True, load=True
    )

    # Require momentum confirmation (AroonMACD)
    require_momentum = BooleanParameter(default=True, space="buy", optimize=False, load=True)

    # ========== AROON PARAMETERS ==========

    aroon_period = IntParameter(low=10, high=30, default=14, space="buy", optimize=True, load=True)

    # ========== RISK MANAGEMENT PARAMETERS ==========

    atr_multiplier = DecimalParameter(
        low=1.5, high=3.5, default=2.5, decimals=1, space="sell", optimize=True, load=True
    )

    risk_reward = DecimalParameter(
        low=1.5, high=3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True
    )

    # ========== CONFIGURATION ==========

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

    # ========== STARTUP ==========

    startup_candle_count: int = 400

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
                score=0.90 if "whale" in (entry_tag or "") else 0.60,
                indicators={},
                reasoning=f"Whale Momentum Signal ({entry_tag})",
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

    # Plot configuration
    plot_config = {
        "subplots": {
            "Aroon": {
                "aroonup": {"color": "orange"},
                "aroondown": {"color": "blue"},
            },
            "MACD": {
                "macd": {"color": "blue"},
                "macdsignal": {"color": "orange"},
            },
            "Whale": {
                "whale_signal": {"color": "green"},
            },
        },
    }

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
        """Send Telegram alert on trade entry."""
        msg = (
            f"🐋 <b>WHALE TRADE ENTRY</b> 🐋\n"
            f"Strategy: WhaleMomentum\n"
            f"Pair: {pair}\n"
            f"Side: {side}\n"
            f"Rate: {rate}\n"
            f"Tag: {entry_tag}\n"
            f"⚡ <b>Whale + AroonMACD Confirmed!</b> ⚡"
        )
        self.dp.send_msg(msg)
        return True

    def informative_pairs(self):
        return []

    # ========== WHALE SIGNAL METHODS ==========

    # Removed local whale signal methods - handled by Intelligent Layer

    # ========== INDICATOR METHODS ==========

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Add Aroon, MACD, and ATR indicators.
        """
        # Aroon indicators
        aroon = ta.AROON(dataframe, timeperiod=self.aroon_period.value)
        dataframe["aroonup"] = aroon["aroonup"]
        dataframe["aroondown"] = aroon["aroondown"]
        dataframe["aroon_osc"] = dataframe["aroonup"] - dataframe["aroondown"]

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]

        # ATR for dynamic SL/TP
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # Placeholder for whale signal (will be checked in populate_entry_trend)
        dataframe["whale_signal"] = 0

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry logic: Intelligent Layer Whale Signal + Local Momentum."""
        pair = metadata["pair"]
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0

        # 1. Get Intelligent Whale Signal
        whale_signal = self.whale_provider.get_signal(pair)

        # 2. Local Technical Conditions
        aroon_bullish = (
            qtpylib.crossed_above(dataframe["aroonup"], dataframe["aroondown"])
            & (dataframe["aroon_osc"] > 0)
            & qtpylib.crossed_above(dataframe["macd"], dataframe["macdsignal"])
        )
        aroon_bearish = (
            qtpylib.crossed_below(dataframe["aroonup"], dataframe["aroondown"])
            & (dataframe["aroon_osc"] < 0)
            & qtpylib.crossed_below(dataframe["macd"], dataframe["macdsignal"])
        )

        # 3. Decision Logic
        if whale_signal:
            if whale_signal.signal_type == "BUY":
                # If momentum required, need aroon bullish cross. Otherwise just price action.
                if self.require_momentum.value:
                    dataframe.loc[aroon_bullish, "enter_long"] = 1
                    dataframe.loc[aroon_bullish, "enter_tag"] = "whale_momentum_long"
                else:
                    dataframe.loc[dataframe.index[-1], "enter_long"] = 1
                    dataframe.loc[dataframe.index[-1], "enter_tag"] = "whale_direct_long"

            elif whale_signal.signal_type == "SELL":
                if self.require_momentum.value:
                    dataframe.loc[aroon_bearish, "enter_short"] = 1
                    dataframe.loc[aroon_bearish, "enter_tag"] = "whale_momentum_short"
                else:
                    dataframe.loc[dataframe.index[-1], "enter_short"] = 1
                    dataframe.loc[dataframe.index[-1], "enter_tag"] = "whale_direct_short"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit handled via custom_exit and custom_stoploss."""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    # ========== RISK MANAGEMENT ==========

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        """ATR-based dynamic stoploss."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return -1

        candle_date = timeframe_to_prev_date(self.timeframe, trade.open_date_utc)
        candles = dataframe.loc[dataframe["date"] == candle_date]
        if candles.empty:
            return -1

        candle = candles.iloc[0]
        atr = candle["atr"]
        multiplier = self.atr_multiplier.value

        if not trade.is_short:
            sl_abs = candle["close"] - (multiplier * atr)
        else:
            sl_abs = candle["high"] + (multiplier * atr)

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
        """Risk-reward based take profit."""
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
        multiplier = self.atr_multiplier.value

        if not trade.is_short:
            sl_abs = candle["close"] - (multiplier * atr)
            risk = (entry_price - sl_abs) / entry_price
        else:
            sl_abs = candle["high"] + (multiplier * atr)
            risk = (sl_abs - entry_price) / entry_price

        target_profit = self.risk_reward.value * risk

        if current_profit >= target_profit:
            return "tp_hit"

        return None

