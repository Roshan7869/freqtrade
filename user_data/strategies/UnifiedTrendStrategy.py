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
# --- Do not remove these libs ---
import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import datetime
from typing import Optional, Union
from functools import reduce

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, CategoricalParameter
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
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


class UnifiedTrendStrategy(IStrategy):
    """
    UnifiedTrendStrategy (Refined)
    Stricter filters to overcome Chop.

    Target: >20% Profit on 1h Timeframe.
    Leverage: 10x (Optimized).
    """

    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {"0": 0.25, "120": 0.15, "240": 0.08, "480": 0.04}

    stoploss = -0.10
    timeframe = "1h"

    # Stricter Params
    aroon_period = IntParameter(14, 30, default=25, space="buy")  # Increased to 25
    adx_threshold = IntParameter(20, 50, default=30, space="buy")  # Increased to 30
    rsi_buy = IntParameter(30, 70, default=50, space="buy")
    rsi_sell = IntParameter(30, 70, default=70, space="sell")

    # Leverage -> 10x
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
                score=0.80 if "whale" in (entry_tag or "") else 0.70,
                indicators={},
                reasoning=f"Trend Signal ({entry_tag})",
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

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        aroon = ta.AROON(dataframe, timeperiod=self.aroon_period.value)
        dataframe["aroonup"] = aroon["aroonup"]
        dataframe["aroondown"] = aroon["aroondown"]
        dataframe["aroonosc"] = ta.AROONOSC(dataframe, timeperiod=self.aroon_period.value)

        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]

        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["bb_mid"] = bollinger["mid"]
        dataframe["bb_lowerband"] = bollinger["lower"]

        # ATR for risk management
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""

        # 1. Standard technical conditions
        conditions_long = (
            (dataframe["aroonup"] > dataframe["aroondown"])
            & (dataframe["macd"] > dataframe["macdsignal"])
            & (dataframe["adx"] > self.adx_threshold.value)
            & (dataframe["rsi"] > self.rsi_buy.value)
            & (dataframe["close"] > dataframe["bb_mid"])
        )
        dataframe.loc[conditions_long, "enter_long"] = 1
        dataframe.loc[conditions_long, "enter_tag"] = "technical_trend"

        # 2. Intelligent Layer Enrichment: Whale Boost
        whale_signal = self.whale_provider.get_signal(metadata["pair"])
        if whale_signal and whale_signal.signal_type == "BUY":
            # Relax conditions: ignore ADX and RSI threshold if whale is buying
            conditions_whale = (
                (dataframe["aroonup"] > dataframe["aroondown"])
                & (dataframe["macd"] > dataframe["macdsignal"])
                & (dataframe["close"] > dataframe["bb_mid"])
            )
            dataframe.loc[conditions_whale, "enter_long"] = 1
            dataframe.loc[conditions_whale, "enter_tag"] = "whale_boost_trend"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = []
        conditions.append(
            (dataframe["aroonup"] < dataframe["aroondown"])
            | (dataframe["macd"] < dataframe["macdsignal"])
            | (dataframe["rsi"] > self.rsi_sell.value)
        )

        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "exit_long"] = 1

        return dataframe

