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


class WilliamsRSI_MACDStrategy(IStrategy):
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
                reasoning=f"Williams/RSI/MACD Signal ({entry_tag})",
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
    A momentum and trend-following strategy for perpetual futures.
    
    Indicators Used:
    - Williams %R: Overbought/Oversold with pullback/recovery detection
    - RSI: Momentum confirmation via threshold crossovers
    - MACD: Trend shift confirmation via signal line crossovers
    - ATR: Dynamic stop-loss and take-profit calculation
    
    Entry Logic:
    - LONG: Williams %R recovers from oversold + RSI crosses above 55 + MACD bullish cross
    - SHORT: Williams %R falls from overbought + RSI crosses below 45 + MACD bearish cross
    
    Exit Logic:
    - Stop Loss: ATR-based (2x ATR from signal candle)
    - Take Profit: 1.5:1 Risk-Reward ratio
    
    Timeframe: 1h (designed for perpetual futures)
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
    use_exit_signal = False  # No indicator-based exits; use custom_exit for TP
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Hyperoptable parameters - RSI thresholds
    rsi_long_threshold = IntParameter(
        low=50, high=60, default=55, space="buy", optimize=True, load=True
    )
    rsi_short_threshold = IntParameter(
        low=40, high=50, default=45, space="sell", optimize=True, load=True
    )

    # Hyperoptable parameters - Risk management
    atr_multiplier = DecimalParameter(
        low=1.0, high=3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True
    )
    risk_reward = DecimalParameter(
        low=1.0, high=2.0, default=1.5, decimals=1, space="sell", optimize=True, load=True
    )

    # Hyperoptable parameters - Williams %R levels
    willr_long_pullback = IntParameter(
        low=-90, high=-70, default=-80, space="buy", optimize=True, load=True
    )
    willr_short_pullback = IntParameter(
        low=-30, high=-10, default=-20, space="sell", optimize=True, load=True
    )
    willr_long_recovery = IntParameter(
        low=-50, high=-30, default=-40, space="buy", optimize=True, load=True
    )
    willr_short_recovery = IntParameter(
        low=-80, high=-50, default=-60, space="sell", optimize=True, load=True
    )

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 400

    # Optional order type mapping
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Optional order time in force
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # Plot configuration for FreqUI visualization
    plot_config = {
        "main_plot": {
            "macd": {"color": "blue"},
            "macdsignal": {"color": "orange"},
        },
        "subplots": {
            "RSI": {
                "rsi": {"color": "red"},
            },
            "Williams %R": {
                "willr": {"color": "purple"},
            },
        },
    }

    def informative_pairs(self):
        """Define additional informative pair/interval combinations."""
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds Williams %R, RSI, MACD, and ATR indicators to the dataframe.

        Indicators:
        - willr: Williams %R (14 periods) - Range: -100 to 0
        - rsi: Relative Strength Index (14 periods) - Range: 0 to 100
        - macd: MACD line (12, 26, 9)
        - macdsignal: MACD signal line
        - atr: Average True Range (14 periods) for SL/TP
        """
        # Williams %R (14 periods)
        dataframe["willr"] = ta.WILLR(dataframe, timeperiod=14)

        # RSI (14 periods)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # MACD (12, 26, 9)
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]

        # ATR (14 periods) for SL calculation
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry logic: Williams %R Recovery + RSI + MACD + Whale Boost."""
        pair = metadata["pair"]
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # 1. Standard technical conditions
        long_willr_condition = (
            (dataframe["willr"].shift(1) < self.willr_long_pullback.value)
            & (dataframe["willr"] > dataframe["willr"].shift(1))
            & (dataframe["willr"] > self.willr_long_pullback.value)
        )
        long_tech = (
            long_willr_condition
            & qtpylib.crossed_above(dataframe["rsi"], self.rsi_long_threshold.value)
            & qtpylib.crossed_above(dataframe["macd"], dataframe["macdsignal"])
            & (dataframe["volume"] > 0)
        )

        short_willr_condition = (
            (dataframe["willr"].shift(1) > self.willr_short_pullback.value)
            & (dataframe["willr"] < dataframe["willr"].shift(1))
            & (dataframe["willr"] < self.willr_short_pullback.value)
        )
        short_tech = (
            short_willr_condition
            & qtpylib.crossed_below(dataframe["rsi"], self.rsi_short_threshold.value)
            & qtpylib.crossed_below(dataframe["macd"], dataframe["macdsignal"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_tech, "enter_long"] = 1
        dataframe.loc[long_tech, "enter_tag"] = "technical_momentum_reversal"
        dataframe.loc[short_tech, "enter_short"] = 1
        dataframe.loc[short_tech, "enter_tag"] = "technical_momentum_reversal"

        # 2. Intelligent Layer: Whale Boost
        whale_signal = self.whale_provider.get_signal(pair)
        if whale_signal:
            if whale_signal.signal_type == "BUY":
                # Relaxed: Only need Williams recovery if whale buy
                whale_long = long_willr_condition & (dataframe["volume"] > 0)
                dataframe.loc[whale_long, "enter_long"] = 1
                dataframe.loc[whale_long, "enter_tag"] = "whale_boost_momentum"
            elif whale_signal.signal_type == "SELL":
                whale_short = short_willr_condition & (dataframe["volume"] > 0)
                dataframe.loc[whale_short, "enter_short"] = 1
                dataframe.loc[whale_short, "enter_tag"] = "whale_boost_momentum"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        No indicator-based exits; handled via custom_exit for TP and custom_stoploss for SL.
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
        Custom stoploss: ATR-based SL calculated from the signal candle.

        Logic:
        - Long: SL = signal_close - (ATR * multiplier)
        - Short: SL = signal_high + (ATR * multiplier)

        Returns relative stoploss (negative value).
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return -1

        # Get the signal candle
        candle_date = timeframe_to_prev_date(self.timeframe, trade.open_date_utc)
        candles = dataframe.loc[dataframe["date"] == candle_date]
        if candles.empty:
            return -1

        candle = candles.iloc[0]
        atr = candle["atr"]
        multiplier = self.atr_multiplier.value

        if not trade.is_short:
            # Long: SL below signal close
            sl_abs = candle["close"] - (multiplier * atr)
        else:
            # Short: SL above signal high
            sl_abs = candle["high"] + (multiplier * atr)

        # Convert to relative stoploss
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
        Custom exit: Check if current profit hits RR target based on ATR risk.

        Logic:
        - Calculate risk distance from entry to SL
        - Target profit = risk * risk_reward_ratio
        - Exit when current_profit >= target_profit

        Returns 'tp_hit' to exit, or None to continue.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None

        # Get the signal candle
        candle_date = timeframe_to_prev_date(self.timeframe, trade.open_date_utc)
        candles = dataframe.loc[dataframe["date"] == candle_date]
        if candles.empty:
            return None

        candle = candles.iloc[0]
        atr = candle["atr"]
        entry_price = trade.open_rate
        multiplier = self.atr_multiplier.value

        # Calculate risk (relative)
        if not trade.is_short:
            sl_abs = candle["close"] - (multiplier * atr)
            risk = (entry_price - sl_abs) / entry_price
        else:
            sl_abs = candle["high"] + (multiplier * atr)
            risk = (sl_abs - entry_price) / entry_price

        # Calculate target profit based on risk-reward ratio
        target_profit = self.risk_reward.value * risk

        if current_profit >= target_profit:
            return "tp_hit"

        return None

