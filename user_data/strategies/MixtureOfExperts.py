import sys
import os
from pathlib import Path


# Add the 'strategies' root directory to sys.path to enable absolute imports
def _setup_path():
    p = Path(__file__).resolve()
    for parent in p.parents:
        if parent.name == "strategies":
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return


_setup_path()
"""
Mixture of Experts - Weighted Ensemble Strategy
================================================
Synthesizes signals from multiple expert strategies using regime-specific weights.

Expert Pool:
- AroonMACDStrategy (Trend expert)
- TEMA_ADX_CMOStrategy (Momentum expert)
- ALMA_MACDStrategy (Smooth trend expert)
- MeanReversionBBStrategy (Mean reversion expert)

Author: Professional Algotrader
"""

from freqtrade.strategy import (
    IStrategy,
    DecimalParameter,
    IntParameter,
    BooleanParameter,
    CategoricalParameter,
)
from pandas import DataFrame
from typing import Optional, Dict, List
from datetime import datetime
import logging

# Intelligent & Decision Layers (with mock fallback for backtesting)
try:
    from signal_layer.src.providers.whale_signal_provider import (
        get_whale_signal_provider,
    )
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

# Import expert strategies with fallback
try:
    from AroonMACDStrategy import AroonMACDStrategy
except ImportError:
    AroonMACDStrategy = None

try:
    from TEMA_ADX_CMOStrategy import TEMA_ADX_CMOStrategy
except ImportError:
    TEMA_ADX_CMOStrategy = None

try:
    from ALMA_MACDStrategy import ALMA_MACDStrategy
except ImportError:
    ALMA_MACDStrategy = None

try:
    from MeanReversionBBStrategy import MeanReversionBBStrategy
except ImportError:
    MeanReversionBBStrategy = None


logger = logging.getLogger(__name__)


class MixtureOfExperts(IStrategy):
    """
    Ensemble Strategy using Weighted Expert Voting

    Combines signals from 4 expert strategies with regime-adaptive weights.
    Uses DecisionEngine for final position sizing and leverage.
    """

    # Strategy metadata
    INTERFACE_VERSION = 3
    can_short = True

    # Expert Weights Hyperopt (per strategy, summed weight used in voting)
    # These override the hardcoded REGIME_WEIGHTS if used in populate_entry_trend
    weight_aroon = DecimalParameter(
        0.0, 1.0, default=0.25, decimals=2, space="buy", optimize=True
    )
    weight_tema = DecimalParameter(
        0.0, 1.0, default=0.25, decimals=2, space="buy", optimize=True
    )
    weight_alma = DecimalParameter(
        0.0, 1.0, default=0.25, decimals=2, space="buy", optimize=True
    )
    weight_bb = DecimalParameter(
        0.0, 1.0, default=0.25, decimals=2, space="buy", optimize=True
    )

    # Minimal config
    minimal_roi = {"0": 0.05}
    stoploss = -0.10
    timeframe = "1h"
    startup_candle_count: int = 400

    # Regime-specific expert weights
    # Format: {regime: {expert_name: weight}}
    REGIME_WEIGHTS = {
        "TRENDING_BULL": {
            "AroonMACDStrategy": 0.45,
            "TEMA_ADX_CMOStrategy": 0.30,
            "ALMA_MACDStrategy": 0.20,
            "MeanReversionBBStrategy": 0.05,
        },
        "TRENDING_BEAR": {
            "AroonMACDStrategy": 0.40,
            "TEMA_ADX_CMOStrategy": 0.35,
            "ALMA_MACDStrategy": 0.20,
            "MeanReversionBBStrategy": 0.05,
        },
        "RANGING": {
            "AroonMACDStrategy": 0.10,
            "TEMA_ADX_CMOStrategy": 0.15,
            "ALMA_MACDStrategy": 0.15,
            "MeanReversionBBStrategy": 0.60,  # Mean reversion dominates
        },
        "HIGH_VOLATILITY": {
            "AroonMACDStrategy": 0.30,
            "TEMA_ADX_CMOStrategy": 0.40,  # Momentum works in vol
            "ALMA_MACDStrategy": 0.15,
            "MeanReversionBBStrategy": 0.15,
        },
        "DEFAULT": {  # Fallback balanced weights
            "AroonMACDStrategy": 0.25,
            "TEMA_ADX_CMOStrategy": 0.25,
            "ALMA_MACDStrategy": 0.25,
            "MeanReversionBBStrategy": 0.25,
        },
    }

    def __init__(self, config: dict) -> None:
        super().__init__(config)

        # Initialize experts
        self.experts: Dict[str, IStrategy] = {
            "AroonMACDStrategy": AroonMACDStrategy(config),
            "TEMA_ADX_CMOStrategy": TEMA_ADX_CMOStrategy(config),
            "ALMA_MACDStrategy": ALMA_MACDStrategy(config),
            "MeanReversionBBStrategy": MeanReversionBBStrategy(config),
        }

        # Initialize layers
        self.decision_engine = get_decision_engine()
        self.llm_analyst = get_llm_market_analyst()
        self.whale_provider = get_whale_signal_provider()
        self._active_decision = None

        logger.info(
            f"🧑‍🏫 Mixture of Experts initialized with {len(self.experts)} experts"
        )

    def _get_regime_weights(self, regime: Optional[str]) -> Dict[str, float]:
        """Get expert weights for current regime"""
        if regime and regime in self.REGIME_WEIGHTS:
            return self.REGIME_WEIGHTS[regime]
        return self.REGIME_WEIGHTS["DEFAULT"]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Populate indicators from all experts"""

        # Each expert populates its own indicators
        for expert_name, expert in self.experts.items():
            # Delegate to expert (they'll add their indicators to dataframe)
            dataframe = expert.populate_indicators(dataframe, metadata)

        # Add ensemble metadata
        dataframe["moe_expert_count"] = len(self.experts)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Ensemble entry logic via weighted voting"""

        pair = metadata["pair"]

        # Initialize columns
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Get current regime
        regime = None
        if self.llm_analyst.is_enabled:
            try:
                market_data = {
                    "close": dataframe["close"].tolist()[-100:],
                    "volume": dataframe["volume"].tolist()[-100:],
                    "high": dataframe["high"].tolist()[-100:],
                    "low": dataframe["low"].tolist()[-100:],
                }
                regime_result = self.llm_analyst.get_market_regime(
                    pair, market_data, self.timeframe
                )
                regime = regime_result.regime.value
            except:
                regime = None

        # Get regime-specific weights
        regime_weights = self._get_regime_weights(regime)

        # Combine base hyperopt weights with regime adjustments
        # Logic: If regime weight > DEFAULT weight, it means this expert is favored in this regime.
        # We multiply our hyperopt base weights by the relative favoring in REGIME_WEIGHTS.
        base_weights = {
            "AroonMACDStrategy": self.weight_aroon.value,
            "TEMA_ADX_CMOStrategy": self.weight_tema.value,
            "ALMA_MACDStrategy": self.weight_alma.value,
            "MeanReversionBBStrategy": self.weight_bb.value,
        }

        # Use normalized hyperopt weights adjusted by regime
        weights = {}
        for name, base_w in base_weights.items():
            regime_factor = (
                regime_weights.get(name, 0.25) / 0.25
            )  # Relative to balanced fallback
            weights[name] = base_w * regime_factor

        # Normalize final weights
        total_w = sum(weights.values())
        if total_w > 0:
            weights = {k: v / total_w for k, v in weights.items()}

        # Collect signals from all experts
        expert_signals_long = {}
        expert_signals_short = {}

        for expert_name, expert in self.experts.items():
            # Get expert's entry signals
            expert_df = expert.populate_entry_trend(dataframe.copy(), metadata)

            # Extract signals
            expert_signals_long[expert_name] = expert_df["enter_long"].values
            expert_signals_short[expert_name] = expert_df["enter_short"].values

        # Weighted voting (Vectorized)
        long_weighted_sum = np.zeros(len(dataframe))
        short_weighted_sum = np.zeros(len(dataframe))

        for expert_name in self.experts.keys():
            weight = weights.get(expert_name, 0.25)
            long_weighted_sum += expert_signals_long[expert_name] * weight
            short_weighted_sum += expert_signals_short[expert_name] * weight

        # Threshold: >0.5 weighted vote triggers signal
        dataframe.loc[long_weighted_sum > 0.5, "enter_long"] = 1
        dataframe.loc[long_weighted_sum > 0.5, "enter_tag"] = (
            f"moe_ensemble_long_{regime or 'default'}"
        )

        dataframe.loc[short_weighted_sum > 0.5, "enter_short"] = 1
        dataframe.loc[short_weighted_sum > 0.5, "enter_tag"] = (
            f"moe_ensemble_short_{regime or 'default'}"
        )

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Ensemble exit logic (simple majority vote)"""

        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        # Collect exit signals
        exit_signals_long = []
        exit_signals_short = []

        for expert in self.experts.values():
            expert_df = expert.populate_exit_trend(dataframe.copy(), metadata)
            exit_signals_long.append(expert_df["exit_long"].values)
            exit_signals_short.append(expert_df["exit_short"].values)

        # Simple majority vote for exit (Vectorized)
        long_exit_votes = np.sum(exit_signals_long, axis=0)
        short_exit_votes = np.sum(exit_signals_short, axis=0)

        threshold = len(self.experts) / 2

        dataframe.loc[long_exit_votes > threshold, "exit_long"] = 1
        dataframe.loc[short_exit_votes > threshold, "exit_short"] = 1

        return dataframe

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
        """Decision Layer: Determine leverage via DecisionEngine"""
        if self._active_decision and self._active_decision.entry_tag == entry_tag:
            return self._active_decision.leverage
        return 15.0

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
        """Decision Layer: Synthesize trade size via ensemble confidence"""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            wallet_balance = self.wallets.get_total_stake_amount()

            # Get regime for confidence boost
            regime = None
            try:
                market_data = {
                    "close": dataframe["close"].tolist()[-100:],
                    "volume": dataframe["volume"].tolist()[-100:],
                    "high": dataframe["high"].tolist()[-100:],
                    "low": dataframe["low"].tolist()[-100:],
                }
                regime_result = self.llm_analyst.get_market_regime(
                    pair, market_data, self.timeframe
                )
                regime = regime_result.regime.value
            except:
                pass

            # Ensemble confidence: average of all expert confidences (weighted)
            weights = self._get_regime_weights(regime)
            ensemble_confidence = sum(weights.values()) / len(weights)  # Normalized

            # Boost confidence if entry_tag indicates ensemble agreement
            if "moe_ensemble" in (entry_tag or ""):
                ensemble_confidence = min(0.85, ensemble_confidence * 1.1)

            tech_signal = TechnicalSignal(
                should_enter=True,
                side="long" if side == "long" else "short",
                score=ensemble_confidence,
                indicators={},
                reasoning=f"MOE Ensemble ({len(self.experts)} experts, regime: {regime or 'default'})",
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
            logger.error(f"MOE stake error: {e}")
            return proposed_stake
