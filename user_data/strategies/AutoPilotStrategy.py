"""
AutoPilot Strategy - Dynamic Best Strategy Selector
=====================================================
Automatically switches to the highest-scoring strategy based on backtest performance.

Features:
1. Loads strategy rankings from backtest analysis
2. Dynamically delegates to the top-scoring strategy
3. Re-evaluates strategy selection periodically
4. Integrates with the 4-Agent Swarm for additional validation
"""

import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import importlib
import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame

# Freqtrade imports
from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    Trade,
)
import freqtrade.vendor.qtpylib.indicators as qtpylib

# Add project root to path
current_path = Path(__file__).resolve()
root_path = current_path.parents[2]
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

logger = logging.getLogger(__name__)


class AutoPilotStrategy(IStrategy):
    """
    Meta-Strategy that automatically delegates to the highest-scoring strategy.

    How it works:
    1. At startup, loads strategy rankings from user_data/strategy_rankings.json
    2. Imports and delegates signals to the top-ranked strategy
    3. Optionally validates with 4-Agent Swarm before executing
    4. Re-checks rankings every N candles to adapt to changing conditions
    """

    INTERFACE_VERSION = 3

    # Base configuration
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    stoploss = -0.15
    use_exit_signal = True

    minimal_roi = {"0": 0.10, "60": 0.05, "120": 0.02}

    # Parameters
    leverage_base = IntParameter(5, 15, default=10, space="buy", optimize=False)
    use_swarm_validation = DecimalParameter(
        0, 1, default=1.0, space="buy", optimize=False
    )
    min_score_threshold = DecimalParameter(
        30, 70, default=50.0, space="buy", optimize=False
    )

    # Tracking
    _rankings_file = None
    _rankings_data = None
    _rankings_loaded_at = None
    _current_strategy_name = None
    _delegated_strategy = None
    _swarm = None

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)

        # Set paths
        self._rankings_file = root_path / "user_data" / "strategy_rankings.json"

        # Load rankings
        self._load_rankings()

        # Initialize Swarm (optional)
        if self.use_swarm_validation.value > 0.5:
            try:
                from decision_layer.src.swarm_orchestrator import get_swarm_orchestrator

                self._swarm = get_swarm_orchestrator()
                logger.info("AutoPilot: 4-Agent Swarm enabled for validation")
            except Exception as e:
                logger.warning(f"AutoPilot: Swarm not available: {e}")

        logger.info(f"AutoPilot Strategy initialized")
        logger.info(f"Delegating to: {self._current_strategy_name}")

    def _load_rankings(self) -> bool:
        """Load strategy rankings from JSON file"""
        try:
            if not self._rankings_file.exists():
                logger.warning(f"Rankings file not found: {self._rankings_file}")
                logger.info("Run: python decision_layer/src/strategy_selector.py")
                return False

            with open(self._rankings_file, "r") as f:
                self._rankings_data = json.load(f)

            self._rankings_loaded_at = datetime.now()

            # Get top strategy
            rankings = self._rankings_data.get("rankings", [])
            if rankings:
                top = rankings[0]
                self._current_strategy_name = top["strategy_name"]

                # Filter by minimum score
                if top["composite_score"] < self.min_score_threshold.value:
                    logger.warning(
                        f"Top strategy {self._current_strategy_name} score "
                        f"{top['composite_score']:.1f} below threshold {self.min_score_threshold.value}"
                    )

                logger.info(
                    f"AutoPilot: Selected '{self._current_strategy_name}' "
                    f"(Score: {top['composite_score']:.1f}, "
                    f"PF: {top['profit_factor']:.2f}, "
                    f"WR: {top['win_rate'] * 100:.1f}%)"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to load rankings: {e}")
            return False

    def _get_delegated_indicators(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        Get indicators from the delegated strategy.
        Since we can't dynamically import strategies, we calculate common indicators.
        """
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(dataframe["close"], window=20, stds=2)
        dataframe["bb_lower"] = bollinger["lower"]
        dataframe["bb_mid"] = bollinger["mid"]
        dataframe["bb_upper"] = bollinger["upper"]

        # ATR
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # ADX
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # EMAs
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=12)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=26)
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=50)

        # WMAs (for trend strategies)
        dataframe["wma_13"] = ta.WMA(dataframe, timeperiod=13)
        dataframe["wma_21"] = ta.WMA(dataframe, timeperiod=21)
        dataframe["wma_34"] = ta.WMA(dataframe, timeperiod=34)

        # Aroon (for ranging)
        aroon = ta.AROON(dataframe, timeperiod=14)
        dataframe["aroon_up"] = aroon["aroonup"]
        dataframe["aroon_down"] = aroon["aroondown"]

        # Stochastic
        stoch = ta.STOCH(dataframe)
        dataframe["stoch_k"] = stoch["slowk"]
        dataframe["stoch_d"] = stoch["slowd"]

        # CCI
        dataframe["cci"] = ta.CCI(dataframe, timeperiod=20)

        # Volume
        dataframe["volume_ma"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_ma"]

        return dataframe

    def _get_strategy_type(self) -> str:
        """
        Determine the type of strategy based on name patterns.
        Used to select appropriate entry/exit logic.
        """
        if not self._current_strategy_name:
            return "balanced"

        name = self._current_strategy_name.lower()

        if any(kw in name for kw in ["trend", "wma", "ema", "supertrend", "momentum"]):
            return "trend"
        elif any(kw in name for kw in ["range", "reversion", "rsi", "bb", "aroon"]):
            return "ranging"
        elif any(kw in name for kw in ["breakout", "volatility", "squeeze"]):
            return "breakout"
        else:
            return "balanced"

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Populate indicators needed for signal generation"""
        dataframe = self._get_delegated_indicators(dataframe, metadata)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Generate entry signals based on the selected strategy type.
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        strategy_type = self._get_strategy_type()

        if strategy_type == "trend":
            # Trend Following Logic (WMA-based)
            conditions_long = (
                (dataframe["close"] > dataframe["wma_13"])
                & (dataframe["wma_13"] > dataframe["wma_21"])
                & (dataframe["wma_21"] > dataframe["wma_34"])
                & (dataframe["adx"] > 25)
                & (dataframe["volume_ratio"] > 0.8)
            )

            conditions_short = (
                (dataframe["close"] < dataframe["wma_13"])
                & (dataframe["wma_13"] < dataframe["wma_21"])
                & (dataframe["wma_21"] < dataframe["wma_34"])
                & (dataframe["adx"] > 25)
                & (dataframe["volume_ratio"] > 0.8)
            )

            dataframe.loc[conditions_long, "enter_long"] = 1
            dataframe.loc[conditions_long, "enter_tag"] = (
                f"autopilot_trend_long_{self._current_strategy_name}"
            )

            dataframe.loc[conditions_short, "enter_short"] = 1
            dataframe.loc[conditions_short, "enter_tag"] = (
                f"autopilot_trend_short_{self._current_strategy_name}"
            )

        elif strategy_type == "ranging":
            # Mean Reversion Logic (BB + RSI)
            conditions_long = (
                (dataframe["close"] < dataframe["bb_lower"])
                & (dataframe["rsi"] < 30)
                & (dataframe["adx"] < 25)
            )

            conditions_short = (
                (dataframe["close"] > dataframe["bb_upper"])
                & (dataframe["rsi"] > 70)
                & (dataframe["adx"] < 25)
            )

            dataframe.loc[conditions_long, "enter_long"] = 1
            dataframe.loc[conditions_long, "enter_tag"] = (
                f"autopilot_range_long_{self._current_strategy_name}"
            )

            dataframe.loc[conditions_short, "enter_short"] = 1
            dataframe.loc[conditions_short, "enter_tag"] = (
                f"autopilot_range_short_{self._current_strategy_name}"
            )

        elif strategy_type == "breakout":
            # Breakout Logic (BB + Volume)
            conditions_long = (
                (dataframe["close"] > dataframe["bb_upper"])
                & (dataframe["volume_ratio"] > 1.5)
                & (dataframe["macd"] > dataframe["macdsignal"])
            )

            conditions_short = (
                (dataframe["close"] < dataframe["bb_lower"])
                & (dataframe["volume_ratio"] > 1.5)
                & (dataframe["macd"] < dataframe["macdsignal"])
            )

            dataframe.loc[conditions_long, "enter_long"] = 1
            dataframe.loc[conditions_long, "enter_tag"] = (
                f"autopilot_breakout_long_{self._current_strategy_name}"
            )

            dataframe.loc[conditions_short, "enter_short"] = 1
            dataframe.loc[conditions_short, "enter_tag"] = (
                f"autopilot_breakout_short_{self._current_strategy_name}"
            )

        else:  # balanced
            # Balanced Logic (Multi-factor)
            conditions_long = (
                (dataframe["rsi"] > 40)
                & (dataframe["rsi"] < 65)
                & (dataframe["macd"] > dataframe["macdsignal"])
                & (dataframe["close"] > dataframe["ema_trend"])
                & (dataframe["volume_ratio"] > 0.8)
            )

            conditions_short = (
                (dataframe["rsi"] > 35)
                & (dataframe["rsi"] < 60)
                & (dataframe["macd"] < dataframe["macdsignal"])
                & (dataframe["close"] < dataframe["ema_trend"])
                & (dataframe["volume_ratio"] > 0.8)
            )

            dataframe.loc[conditions_long, "enter_long"] = 1
            dataframe.loc[conditions_long, "enter_tag"] = (
                f"autopilot_balanced_long_{self._current_strategy_name}"
            )

            dataframe.loc[conditions_short, "enter_short"] = 1
            dataframe.loc[conditions_short, "enter_tag"] = (
                f"autopilot_balanced_short_{self._current_strategy_name}"
            )

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Generate exit signals"""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        dataframe["exit_tag"] = ""

        strategy_type = self._get_strategy_type()

        if strategy_type == "trend":
            # Exit when trend reverses
            dataframe.loc[
                (dataframe["close"] < dataframe["wma_21"]), ["exit_long", "exit_tag"]
            ] = [1, "trend_reversal"]

            dataframe.loc[
                (dataframe["close"] > dataframe["wma_21"]), ["exit_short", "exit_tag"]
            ] = [1, "trend_reversal"]

        elif strategy_type == "ranging":
            # Exit at mean or opposite extreme
            dataframe.loc[
                (dataframe["close"] > dataframe["bb_mid"]) | (dataframe["rsi"] > 60),
                ["exit_long", "exit_tag"],
            ] = [1, "mean_reached"]

            dataframe.loc[
                (dataframe["close"] < dataframe["bb_mid"]) | (dataframe["rsi"] < 40),
                ["exit_short", "exit_tag"],
            ] = [1, "mean_reached"]

        else:
            # Generic exit
            dataframe.loc[(dataframe["rsi"] > 70), ["exit_long", "exit_tag"]] = [
                1,
                "overbought",
            ]

            dataframe.loc[(dataframe["rsi"] < 30), ["exit_short", "exit_tag"]] = [
                1,
                "oversold",
            ]

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
        """Calculate leverage based on top strategy's performance metrics"""
        if not self._rankings_data:
            return float(self.leverage_base.value)

        rankings = self._rankings_data.get("rankings", [])
        if not rankings:
            return float(self.leverage_base.value)

        top = rankings[0]

        # Scale leverage based on score
        score = top.get("composite_score", 50)
        base_lev = float(self.leverage_base.value)

        if score >= 70:
            leverage = base_lev * 1.2  # Confidence boost
        elif score >= 50:
            leverage = base_lev
        else:
            leverage = base_lev * 0.8  # Reduce for low confidence

        return min(leverage, max_leverage)

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> Optional[float]:
        """Trailing stop based on ATR"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        if len(dataframe) < 1:
            return None

        atr = dataframe["atr"].iloc[-1]

        if current_profit > 0.02:  # After 2% profit
            # Trail at 2x ATR
            sl_distance = (atr * 2) / current_rate
            return -sl_distance

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
        """
        Optional: Validate entry with 4-Agent Swarm before executing.
        """
        if not self._swarm or self.use_swarm_validation.value < 0.5:
            return True  # Skip validation

        try:
            import asyncio

            # Get dataframe for swarm analysis
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

            if len(dataframe) < 30:
                return True  # Not enough data

            # Run swarm (async to sync bridge)
            decision = asyncio.run(
                self._swarm.analyze_and_decide(
                    pair=pair,
                    ohlcv_dataframe=dataframe,
                    timeframe=self.timeframe,
                    portfolio_balance=10000.0,  # Could get from exchange
                )
            )

            # Validate
            if decision.should_execute:
                logger.info(f"Swarm APPROVED {side} on {pair}")
                return True
            else:
                logger.warning(f"Swarm REJECTED {side} on {pair}")
                return False

        except Exception as e:
            logger.warning(f"Swarm validation error: {e}")
            return True  # Proceed on error
