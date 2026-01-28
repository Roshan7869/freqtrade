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
import json
import os
from pathlib import Path

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

import talib.abstract as ta

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


from technical import qtpylib

# Intelligent & Decision Layers - Deferred import for Docker compatibility
# These will be imported in __init__ with fallback logic


class AroonMACDStrategy(IStrategy):
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        # Initialize with fallback providers (already imported at module level)
        self.decision_engine = get_decision_engine()
        self.whale_provider = get_whale_signal_provider()
        self.llm_analyst = get_llm_market_analyst()
        self._active_decision = None  # Cache for current candle

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
        """
        Decision Layer: Use DecisionEngine to determine leverage.
        """
        # If we have a cached decision for this entry, use it
        if self._active_decision and self._active_decision.entry_tag == entry_tag:
            return self._active_decision.leverage

        # Use user-defined leverage parameter
        return self.leverage_multiplier.value

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
        Decision Layer: Final trade synthesis (Size, Confidence, Risk).
        """
        try:
            # 1. Get current data
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe.empty:
                return proposed_stake

            last_candle = dataframe.iloc[-1]
            wallet_balance = self.wallets.get_total_stake_amount()

            # 2. Build Technical Signal object
            tech_signal = TechnicalSignal(
                should_enter=True,
                side="long" if side == "long" else "short",
                score=0.75 if "whale_boost" in (entry_tag or "") else 0.65,
                indicators={
                    "aroon_osc": last_candle.get("aroon_osc", 0),
                    "macd": last_candle.get("macd", 0),
                },
                reasoning=f"Technical entry signal ({entry_tag})",
            )

            # 3. Call Decision Engine
            decision = self.decision_engine.analyze_entry(
                pair=pair,
                technical_signal=tech_signal,
                wallet_balance=wallet_balance,
                market_data=dataframe.tail(20).to_dict(orient="records"),
            )

            # 4. Cache for leverage() call
            self._active_decision = decision

            # 5. Return position size
            if decision.action == TradeAction.HOLD:
                return 0.0

            return max(min_stake or 0, min(decision.position_size_usd, max_stake))

        except Exception as e:
            logger.error(f"Error in Decision Layer synthesis: {e}")
            return proposed_stake

    """
    A trend-following strategy using Aroon indicators for perpetual futures.
    
    Concept:
    - Use Aroon Up/Down crossovers to identify trend direction
    - Aroon Oscillator momentum for trend strength confirmation
    - MACD signal line cross for additional confirmation
    - ATR-based risk management with 2:1 reward-to-risk
    
    Indicators Used:
    - Aroon Up: Measures time since highest high (0-100)
    - Aroon Down: Measures time since lowest low (0-100)
    - Aroon Oscillator: AroonUp - AroonDown (-100 to +100)
    - MACD: Trend confirmation via signal line cross
    - ATR: Dynamic stop-loss and take-profit calculation
    
    Entry Logic:
    - LONG: AroonUp crosses above AroonDown + Oscillator > 0 & rising + MACD bullish cross
    - SHORT: AroonUp crosses below AroonDown + Oscillator < 0 & falling + MACD bearish cross
    
    Exit Logic:
    - Stop Loss: ATR-based (2.5x ATR from signal candle)
    - Take Profit: 2:1 Risk-Reward ratio
    
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

    # Hyperoptable parameters - Aroon
    aroon_period = IntParameter(
        low=10, high=30, default=14, space="buy", optimize=True, load=True
    )

    # Hyperoptable parameters - Regime Filter (ADX)
    adx_threshold = IntParameter(
        low=20, high=35, default=25, space="buy", optimize=True, load=True
    )
    enable_regime_filter = BooleanParameter(
        default=True, space="buy", optimize=False, load=True
    )

    # Hyperoptable parameters - Risk management
    atr_multiplier = DecimalParameter(
        low=1.0,
        high=2.5,
        default=1.5,
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

    # User-defined leverage (can be overridden in config)
    leverage_multiplier = DecimalParameter(
        low=1.0,
        high=20.0,
        default=10.0,
        decimals=1,
        space="buy",
        optimize=False,
        load=True,
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
        "subplots": {
            "Aroon": {
                "aroonup": {"color": "orange"},
                "aroondown": {"color": "blue"},
            },
            "Aroon Oscillator": {
                "aroon_osc": {"color": "green"},
            },
            "MACD": {
                "macd": {"color": "blue"},
                "macdsignal": {"color": "orange"},
            },
        },
    }

    # Removed _get_whale_signal - now handled by Intelligent Layer (WhaleSignalProvider)

    def informative_pairs(self):
        """Define additional informative pair/interval combinations."""
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds Aroon Up/Down/Oscillator, MACD, ATR, and ADX indicators.

        Indicators:
        - aroonup: Aroon Up (0-100, high = recent high)
        - aroondown: Aroon Down (0-100, high = recent low)
        - aroon_osc: Aroon Oscillator (AroonUp - AroonDown)
        - macd: MACD line (12, 26, 9)
        - macdsignal: MACD signal line
        - atr: Average True Range for SL/TP
        - adx: Average Directional Index (trend strength filter)
        """
        # Aroon (hyperoptable period)
        aroon = ta.AROON(dataframe, timeperiod=self.aroon_period.value)
        dataframe["aroonup"] = aroon["aroonup"]
        dataframe["aroondown"] = aroon["aroondown"]

        # Aroon Oscillator = AroonUp - AroonDown
        dataframe["aroon_osc"] = dataframe["aroonup"] - dataframe["aroondown"]

        # MACD (12, 26, 9)
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]

        # ATR (14 periods) for SL calculation
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # ADX (14 periods) for regime filter - CRITICAL FIX
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populates entry signals based on Aroon crossovers, oscillator momentum, and MACD.

        Long Entry:
        - Aroon Up crosses above Aroon Down (bullish crossover)
        - Aroon Oscillator > 0 (bullish territory)
        - Aroon Oscillator rising (increasing momentum)
        - MACD crosses above signal line

        Short Entry:
        - Aroon Up crosses below Aroon Down (bearish crossover)
        - Aroon Oscillator < 0 (bearish territory)
        - Aroon Oscillator falling (increasing bearish momentum)
        - MACD crosses below signal line
        """
        # Recent Aroon cross (within last 3 candles)
        aroon_cross_long = (
            qtpylib.crossed_above(dataframe["aroonup"], dataframe["aroondown"])
            | qtpylib.crossed_above(dataframe["aroonup"], dataframe["aroondown"]).shift(
                1
            )
            | qtpylib.crossed_above(dataframe["aroonup"], dataframe["aroondown"]).shift(
                2
            )
        )

        # Regime filter: Only trade when ADX indicates a trend
        regime_filter = True
        if self.enable_regime_filter.value:
            regime_filter = dataframe["adx"] > self.adx_threshold.value

        # Standard technical conditions with regime filter
        conditions_long = (
            aroon_cross_long
            & (dataframe["aroonup"] > dataframe["aroondown"])
            & (dataframe["aroon_osc"] > 0)
            & (dataframe["macd"] > dataframe["macdsignal"])
            & (dataframe["volume"] > 0)
            & regime_filter
        )

        # Intelligent Layer Enrichment: Whale Boost
        whale_signal = self.whale_provider.get_signal(metadata["pair"])
        if whale_signal and whale_signal.signal_type == "BUY":
            # Relax conditions: if whale buy signal, only needs Aroon uptrend
            whale_boost_long = (
                (dataframe["aroonup"] > dataframe["aroondown"])
                & (dataframe["aroon_osc"] > -20)  # Relaxed from > 0
                & (dataframe["volume"] > 0)
            )
            dataframe.loc[whale_boost_long, "enter_long"] = 1
            dataframe.loc[whale_boost_long, "enter_tag"] = "whale_boost_long"

        dataframe.loc[conditions_long, "enter_long"] = 1
        dataframe.loc[conditions_long, "enter_tag"] = "technical_long"

        # Recent Aroon cross down
        aroon_cross_short = (
            qtpylib.crossed_below(dataframe["aroonup"], dataframe["aroondown"])
            | qtpylib.crossed_below(dataframe["aroonup"], dataframe["aroondown"]).shift(
                1
            )
            | qtpylib.crossed_below(dataframe["aroonup"], dataframe["aroondown"]).shift(
                2
            )
        )

        # Standard technical conditions with regime filter
        conditions_short = (
            aroon_cross_short
            & (dataframe["aroonup"] < dataframe["aroondown"])
            & (dataframe["aroon_osc"] < 0)
            & (dataframe["macd"] < dataframe["macdsignal"])
            & (dataframe["volume"] > 0)
            & regime_filter
        )

        # Intelligent Layer Enrichment: Whale Boost
        if whale_signal and whale_signal.signal_type == "SELL":
            # Relax conditions
            whale_boost_short = (
                (dataframe["aroonup"] < dataframe["aroondown"])
                & (dataframe["aroon_osc"] < 20)  # Relaxed from < 0
                & (dataframe["volume"] > 0)
            )
            dataframe.loc[whale_boost_short, "enter_short"] = 1
            dataframe.loc[whale_boost_short, "enter_tag"] = "whale_boost_short"

        dataframe.loc[conditions_short, "enter_short"] = 1
        dataframe.loc[conditions_short, "enter_tag"] = "technical_short"

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
        **kwargs,
    ) -> float:
        """
        Custom stoploss with TRAILING STOP activation.

        Logic:
        - Initial: ATR-based SL from signal candle
        - After 1% profit: Trail at 0.5%
        - After 2% profit: Trail at 0.3%

        Returns relative stoploss (negative value).
        """
        # ENHANCED TRAILING STOP - Lock in profits progressively
        if current_profit > 0.05:  # 5% profit - trail by 1%
            return -0.01
        elif current_profit > 0.02:  # 2% profit - move to break-even
            return -0.001  # Minimal trail (essentially break-even)
        elif current_profit > 0.01:  # 1% profit - tight trail
            return -0.005  # Trail at 0.5%

        # Initial ATR-based SL
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
        **kwargs,
    ) -> Optional[Union[str, bool]]:
        """
        Custom exit: Check if current profit hits RR target based on ATR risk.

        Logic:
        - Calculate risk distance from entry to SL
        - Target profit = risk * risk_reward_ratio (default 2:1)
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
