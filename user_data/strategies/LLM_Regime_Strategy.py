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
# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
"""
LLM Regime Strategy - Intelligent Adaptive Trading

This strategy uses an LLM (DeepSeek R1) to analyze market conditions and
dynamically adapt its trading behavior based on the detected market regime.

Regimes:
- TRENDING_BULL: Aggressive long entries with higher leverage
- TRENDING_BEAR: Aggressive short entries with higher leverage
- RANGING: Mean reversion with lower leverage
- HIGH_VOLATILITY: Conservative or no trading

The LLM is called periodically (cached for 1 hour) to reduce API costs.
"""

from datetime import datetime, timedelta
from typing import Optional, Union
import logging

# Intelligent & Decision Layers (with mock fallback for backtesting)

# Intelligent & Decision Layers (with mock fallback for backtesting)
try:
    # Corrected Paths
    from signal_layer.src.services.whale_provider import (
        get_whale_signal_provider,
    )
    from analysis_layer.src.domain.regime.analyst import (
        get_llm_market_analyst,
        MarketRegime,
        MarketRegimeType,
    )

    # Decision Engine - We can't use the async DecisionEngine directly in Sync Backtesting
    # So we define the Mock/Backtest Engine here even if imports succeed
    from decision_layer.src.decision_engine import (
        DecisionEngine,
    )  # Just to check existence
    from shared.schemas.events import (
        StrategySignal,
        TradeOrder as TradeAction,
    )  # Approximate mapping

    def get_decision_engine():
        return MockDecisionEngine()

except ImportError as e:
    logging.warning(f"⚠️ Import failed: {e}. Using Mocks.")

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


# Ensure MockDecisionEngine is available globally if needed
if "MockDecisionEngine" not in locals():

    class MockDecisionEngine:
        def analyze_entry(self, **kwargs):
            # Simple allow-all logic for backtesting
            class Decision:
                action = "BUY"  # Default to BUY to allow strategy to trade
                position_size_usd = 999999
                leverage = 20.0
                entry_tag = "backtest_entry"

            return Decision()

    class TradeAction:
        HOLD = "HOLD"
        BUY = "BUY"
        SELL = "SELL"

    class TechnicalSignal:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)


import numpy as np
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
    RealParameter,
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


# Mock MarketRegime classes for standalone backtesting
class MarketRegimeType:
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"


class MarketRegime:
    def __init__(self, regime=None, risk_score=5, reasoning=""):
        self.regime = regime if regime else MarketRegimeType.RANGING
        self.risk_score = risk_score
        self.reasoning = reasoning


class LLM_Regime_Strategy(IStrategy):
    """
    Intelligent trading strategy that adapts based on LLM market regime analysis.

    The strategy uses DeepSeek R1 (via OpenRouter) to classify the market into:
    - TRENDING_BULL: Focus on long entries with momentum confirmation
    - TRENDING_BEAR: Focus on short entries with momentum confirmation
    - RANGING: Mean reversion using Bollinger Bands
    - HIGH_VOLATILITY: Reduce leverage or skip trades

    Entry signals combine technical indicators with LLM regime recommendations.
    """

    INTERFACE_VERSION = 3
    can_short: bool = True

    # Minimal ROI (disabled - use custom exit)
    minimal_roi = {"0": 100}

    # Wide stoploss (handled by custom_stoploss)
    stoploss = -0.99

    # Trailing stop disabled (using ATR-based exits)
    trailing_stop = False

    # Optimal timeframe
    timeframe = "1h"

    # Process only new candles
    process_only_new_candles = True

    # Exit configuration
    use_exit_signal = False
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # ========== HYPEROPTABLE PARAMETERS ==========

    # RSI thresholds
    rsi_buy = IntParameter(
        low=20, high=40, default=30, space="buy", optimize=True, load=True
    )
    rsi_sell = IntParameter(
        low=60, high=80, default=70, space="buy", optimize=True, load=True
    )

    # ADX threshold for trend confirmation
    adx_threshold = IntParameter(
        low=20, high=35, default=25, space="buy", optimize=True, load=True
    )

    # Bollinger Band settings for ranging
    bb_period = IntParameter(
        low=15, high=25, default=20, space="buy", optimize=True, load=True
    )
    bb_std = DecimalParameter(
        low=1.5,
        high=2.5,
        default=2.0,
        decimals=1,
        space="buy",
        optimize=True,
        load=True,
    )

    # Risk management
    atr_multiplier = DecimalParameter(
        low=1.5,
        high=3.5,
        default=2.5,
        decimals=1,
        space="sell",
        optimize=True,
        load=True,
    )
    risk_reward = DecimalParameter(
        low=1.5,
        high=3.0,
        default=2.0,
        decimals=1,
        space="sell",
        optimize=True,
        load=True,
    )

    # LLM influence weight (how much to trust LLM vs pure technical)
    llm_weight = DecimalParameter(
        low=0.3,
        high=0.9,
        default=0.7,
        decimals=1,
        space="buy",
        optimize=True,
        load=True,
    )

    # ========== STARTUP ==========

    startup_candle_count: int = 400

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # Plot configuration
    plot_config = {
        "main_plot": {
            "bb_upper": {"color": "rgba(255, 0, 0, 0.3)"},
            "bb_lower": {"color": "rgba(0, 255, 0, 0.3)"},
            "bb_mid": {"color": "rgba(128, 128, 128, 0.5)"},
        },
        "subplots": {
            "RSI": {
                "rsi": {"color": "purple"},
            },
            "MACD": {
                "macd": {"color": "blue"},
                "macdsignal": {"color": "orange"},
            },
            "ADX": {
                "adx": {"color": "red"},
            },
        },
    }

    # Store current regime for leverage/risk decisions
    _current_regime: Optional[MarketRegime] = None

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.decision_engine = get_decision_engine()
        self.whale_provider = get_whale_signal_provider()
        self.llm_analyst = get_llm_market_analyst()
        self._active_decision = None
        logger.info("🧠 LLM Regime Strategy initialized using 3-layer architecture")

    def informative_pairs(self):
        return []

    def _prepare_market_data(self, dataframe: DataFrame, pair: str) -> dict:
        """Prepare market data summary for LLM analysis."""
        if len(dataframe) < 24:
            return {}

        recent = dataframe.tail(24)
        current = dataframe.iloc[-1]

        return {
            "pair": pair,
            "current_price": current["close"],
            "high_24h": recent["high"].max(),
            "low_24h": recent["low"].min(),
            "change_24h": (
                (current["close"] - recent.iloc[0]["close"]) / recent.iloc[0]["close"]
            )
            * 100,
            "rsi": current.get("rsi", 50),
            "adx": current.get("adx", 25),
            "atr": current.get("atr", 0),
            "macd": current.get("macd", 0),
            "macd_signal": current.get("macdsignal", 0),
            "bb_width": current.get("bb_width", 0),
            "volume": current["volume"],
            "volume_ma": recent["volume"].mean(),
            "volume_ratio": current["volume"] / recent["volume"].mean()
            if recent["volume"].mean() > 0
            else 1,
        }

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add all technical indicators and call Intelligent Layer for regime analysis."""

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # ADX (trend strength)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]

        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe),
            window=self.bb_period.value,
            stds=self.bb_std.value,
        )
        dataframe["bb_lower"] = bollinger["lower"]
        dataframe["bb_mid"] = bollinger["mid"]
        dataframe["bb_upper"] = bollinger["upper"]
        dataframe["bb_width"] = (
            dataframe["bb_upper"] - dataframe["bb_lower"]
        ) / dataframe["bb_mid"]

        # ATR for risk management
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # EMA for trend
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=12)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=26)

        # Intelligent Layer: Get Market Regime (cached hourly)
        pair = metadata.get("pair", "UNKNOWN")
        market_data = dataframe.tail(24).to_dict(orient="records")

        regime = self.llm_analyst.get_market_regime(pair, market_data, self.timeframe)

        # Fallback to default regime if None (backtesting without LLM)
        if regime is None:
            regime = MarketRegime(
                MarketRegimeType.RANGING, 5, "Fallback regime for backtesting"
            )

        self._current_regime = regime

        # Store regime in dataframe for backtesting/UI
        regime_value = (
            regime.regime
            if isinstance(regime.regime, str)
            else getattr(regime.regime, "value", "RANGING")
        )
        dataframe["llm_regime"] = regime_value
        dataframe["llm_risk"] = regime.risk_score

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry logic adapts based on Intelligent Layer regime."""
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0

        regime = self._current_regime
        whale_signal = self.whale_provider.get_signal(metadata["pair"])

        volume_ok = dataframe["volume"] > 0
        adx_trending = dataframe["adx"] > self.adx_threshold.value

        # 1. TRENDING_BULL
        if regime.regime == MarketRegimeType.TRENDING_BULL:
            long_conditions = (
                qtpylib.crossed_above(dataframe["macd"], dataframe["macdsignal"])
                & (dataframe["rsi"] < self.rsi_sell.value)
                & (dataframe["ema_fast"] > dataframe["ema_slow"])
                & volume_ok
            )
            # Whale Boost enrichment
            if whale_signal and whale_signal.signal_type == "BUY":
                long_conditions |= dataframe["ema_fast"] > dataframe["ema_slow"]

            dataframe.loc[long_conditions, "enter_long"] = 1
            dataframe.loc[long_conditions, "enter_tag"] = "llm_bull_entry"

        # 2. TRENDING_BEAR
        elif regime.regime == MarketRegimeType.TRENDING_BEAR:
            short_conditions = (
                qtpylib.crossed_below(dataframe["macd"], dataframe["macdsignal"])
                & (dataframe["rsi"] > self.rsi_buy.value)
                & (dataframe["ema_fast"] < dataframe["ema_slow"])
                & volume_ok
            )
            if whale_signal and whale_signal.signal_type == "SELL":
                short_conditions |= dataframe["ema_fast"] < dataframe["ema_slow"]

            dataframe.loc[short_conditions, "enter_short"] = 1
            dataframe.loc[short_conditions, "enter_tag"] = "llm_bear_entry"

        # 3. RANGING
        elif regime.regime == MarketRegimeType.RANGING:
            long_ranging = (dataframe["close"] <= dataframe["bb_lower"]) & (
                dataframe["rsi"] < self.rsi_buy.value
            )
            short_ranging = (dataframe["close"] >= dataframe["bb_upper"]) & (
                dataframe["rsi"] > self.rsi_sell.value
            )

            dataframe.loc[long_ranging, "enter_long"] = 1
            dataframe.loc[short_ranging, "enter_short"] = 1
            dataframe.loc[long_ranging | short_ranging, "enter_tag"] = "llm_range_entry"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit handled via custom_exit and custom_stoploss."""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
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
        """Decision Layer: Determine leverage via DecisionEngine."""
        if self._active_decision and self._active_decision.entry_tag == entry_tag:
            return self._active_decision.leverage
        return 10.0

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
                score=0.85,  # AI-enhanced signals have higher base score
                indicators={
                    "regime": self._current_regime.regime.value
                    if self._current_regime
                    else "RANGING"
                },
                reasoning=f"LLM Regime Signal ({entry_tag})",
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
        """ATR-based dynamic stoploss, adjusted by regime."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return -1

        candle_date = timeframe_to_prev_date(self.timeframe, trade.open_date_utc)
        candles = dataframe.loc[dataframe["date"] == candle_date]
        if candles.empty:
            return -1

        candle = candles.iloc[0]
        atr = candle["atr"]

        # Adjust multiplier based on regime
        regime = self._current_regime
        if regime and regime.regime == "HIGH_VOLATILITY":
            multiplier = (
                self.atr_multiplier.value * 1.5
            )  # Wider stop in volatile markets
        elif regime and regime.regime == "RANGING":
            multiplier = self.atr_multiplier.value * 0.8  # Tighter stop in ranging
        else:
            multiplier = self.atr_multiplier.value

        if not trade.is_short:
            sl_abs = candle["close"] - (multiplier * atr)
        else:
            sl_abs = candle["close"] + (multiplier * atr)

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
            sl_abs = candle["close"] + (multiplier * atr)
            risk = (sl_abs - entry_price) / entry_price

        target_profit = self.risk_reward.value * risk

        if current_profit >= target_profit:
            return "llm_tp_hit"

        return None

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
        """Send Telegram alert with LLM analysis on trade entry."""
        regime = self._current_regime
        regime_info = (
            f"{regime.regime} (Risk: {regime.risk_score}/10)" if regime else "UNKNOWN"
        )
        reasoning = regime.reasoning if regime else "No analysis"

        msg = (
            f"🧠 <b>LLM INTELLIGENT TRADE</b> 🧠\n"
            f"Strategy: LLM_Regime\n"
            f"Pair: {pair}\n"
            f"Side: <b>{side.upper()}</b>\n"
            f"Rate: {rate:.4f}\n"
            f"Tag: {entry_tag}\n"
            f"Regime: <b>{regime_info}</b>\n"
            f"Analysis: {reasoning}\n"
            f"⚡ <b>AI-Powered Entry!</b> ⚡"
        )
        self.dp.send_msg(msg)
        return True
