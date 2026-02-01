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


class EdriExtremePointsStrategy(IStrategy):
    """
    Edri Extreme Points Buy & Sell Strategy for perpetual futures.

    This strategy combines CCI, Momentum, and RSI indicators to identify
    extreme points for entry, with EMA pullback as a trend filter.

    Indicators Used:
    - CCI (Commodity Channel Index): Identifies overbought/oversold conditions
    - Momentum: Confirms trend direction via crossovers with CCI
    - RSI: Additional oversold/overbought confirmation
    - EMA (100): Trend filter - buy on pullback to EMA
    - ATR: Dynamic stop-loss and take-profit calculation

    Entry Logic:
    - LONG: CCI/MOM cross up + RSI recovering from oversold + price <= EMA100
    - SHORT: CCI/MOM cross down + RSI falling from overbought + price >= EMA100

    Exit Logic:
    - Stop Loss: 2x ATR from entry
    - Take Profit: 4x ATR from entry (2:1 RR ratio)

    Timeframe: 1h (designed for perpetual futures)
    """

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
                reasoning=f"Extreme Points Signal ({entry_tag})",
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

    # Hyperoptable parameters - CCI
    cci_period = IntParameter(low=10, high=20, default=14, space="buy", optimize=True, load=True)

    # Hyperoptable parameters - Momentum
    mom_period = IntParameter(low=8, high=14, default=10, space="buy", optimize=True, load=True)

    # Hyperoptable parameters - RSI thresholds
    rsi_period = IntParameter(low=10, high=20, default=14, space="buy", optimize=True, load=True)
    rsi_oversold = IntParameter(low=20, high=35, default=30, space="buy", optimize=True, load=True)
    rsi_overbought = IntParameter(
        low=65, high=80, default=70, space="sell", optimize=True, load=True
    )

    # Hyperoptable parameters - EMA
    ema_period = IntParameter(low=80, high=120, default=100, space="buy", optimize=True, load=True)

    # Hyperoptable parameters - Risk management
    atr_sl_multiplier = DecimalParameter(
        low=1.5, high=3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True
    )
    atr_tp_multiplier = DecimalParameter(
        low=3.0, high=5.0, default=4.0, decimals=1, space="sell", optimize=True, load=True
    )

    # Enable divergence detection
    use_divergence = BooleanParameter(default=True, space="buy", optimize=True, load=True)

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 400  # Need enough for EMA100 stabilization

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
            "ema100": {"color": "orange"},
        },
        "subplots": {
            "CCI": {
                "cci": {"color": "blue"},
            },
            "Momentum": {
                "mom": {"color": "green"},
            },
            "RSI": {
                "rsi": {"color": "purple"},
            },
        },
    }

    def informative_pairs(self):
        """Define additional informative pair/interval combinations."""
        return []

    def detect_bullish_divergence(self, dataframe: DataFrame, lookback: int = 14) -> pd.Series:
        """
        Detect regular bullish divergence:
        Price makes lower low, but RSI makes higher low.
        """
        price_low = dataframe["low"]
        rsi = dataframe["rsi"]

        # Find local lows in price (lower than previous lookback candles)
        price_lower_low = (price_low < price_low.shift(1)) & (
            price_low < price_low.rolling(lookback).min().shift(1)
        )

        # RSI higher low at price lower low
        rsi_higher_low = (rsi > rsi.shift(lookback)) & price_lower_low

        return rsi_higher_low

    def detect_bearish_divergence(self, dataframe: DataFrame, lookback: int = 14) -> pd.Series:
        """
        Detect regular bearish divergence:
        Price makes higher high, but RSI makes lower high.
        """
        price_high = dataframe["high"]
        rsi = dataframe["rsi"]

        # Find local highs in price (higher than previous lookback candles)
        price_higher_high = (price_high > price_high.shift(1)) & (
            price_high > price_high.rolling(lookback).max().shift(1)
        )

        # RSI lower high at price higher high
        rsi_lower_high = (rsi < rsi.shift(lookback)) & price_higher_high

        return rsi_lower_high

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds CCI, Momentum, RSI, EMA, and ATR indicators to the dataframe.

        Indicators:
        - cci: Commodity Channel Index (default 14 periods)
        - mom: Momentum indicator (default 10 periods)
        - rsi: Relative Strength Index (default 14 periods)
        - ema100: Exponential Moving Average (default 100 periods)
        - atr: Average True Range (14 periods) for SL/TP
        """
        # CCI (hyperoptable period)
        dataframe["cci"] = ta.CCI(dataframe, timeperiod=self.cci_period.value)

        # Momentum (hyperoptable period)
        dataframe["mom"] = ta.MOM(dataframe, timeperiod=self.mom_period.value)

        # RSI (hyperoptable period)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)

        # EMA (hyperoptable period)
        dataframe["ema100"] = ta.EMA(dataframe, timeperiod=self.ema_period.value)

        # ATR (14 periods) for SL/TP calculation
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # ADX (14 periods) for trend filter
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # Divergence detection
        if self.use_divergence.value:
            dataframe["bullish_div"] = self.detect_bullish_divergence(dataframe)
            dataframe["bearish_div"] = self.detect_bearish_divergence(dataframe)
        else:
            dataframe["bullish_div"] = False
            dataframe["bearish_div"] = False

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry logic: CCI/Mom cross + RSI recovery + Whale Boost."""
        pair = metadata["pair"]
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Technical indicators
        cci_mom_cross_up = qtpylib.crossed_above(dataframe["cci"], dataframe["mom"])
        cci_mom_cross_down = qtpylib.crossed_below(dataframe["cci"], dataframe["mom"])

        long_rsi_condition = (
            (dataframe["rsi"].shift(1) < self.rsi_oversold.value)
            & (dataframe["rsi"] > dataframe["rsi"].shift(1))
        ) | dataframe["bullish_div"]

        short_rsi_condition = (
            (dataframe["rsi"].shift(1) > self.rsi_overbought.value)
            & (dataframe["rsi"] < dataframe["rsi"].shift(1))
        ) | dataframe["bearish_div"]

        conditions_long = (
            cci_mom_cross_up
            & long_rsi_condition
            & (dataframe["close"] <= dataframe["ema100"])
            & (dataframe["adx"] > 20)
        )
        conditions_short = (
            cci_mom_cross_down
            & short_rsi_condition
            & (dataframe["close"] >= dataframe["ema100"])
            & (dataframe["adx"] > 20)
        )

        dataframe.loc[conditions_long, "enter_long"] = 1
        dataframe.loc[conditions_long, "enter_tag"] = "technical_extreme_long"
        dataframe.loc[conditions_short, "enter_short"] = 1
        dataframe.loc[conditions_short, "enter_tag"] = "technical_extreme_short"

        # Whale Boost integration
        whale_signal = self.whale_provider.get_signal(pair)
        if whale_signal:
            if whale_signal.signal_type == "BUY":
                # Relaxed: Only need cross + close <= EMA100
                whale_long = cci_mom_cross_up & (dataframe["close"] <= dataframe["ema100"])
                dataframe.loc[whale_long, "enter_long"] = 1
                dataframe.loc[whale_long, "enter_tag"] = "whale_boost_extreme_long"
            elif whale_signal.signal_type == "SELL":
                whale_short = cci_mom_cross_down & (dataframe["close"] >= dataframe["ema100"])
                dataframe.loc[whale_short, "enter_short"] = 1
                dataframe.loc[whale_short, "enter_tag"] = "whale_boost_extreme_short"

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
        - Long: SL = entry_price - (ATR * 2)
        - Short: SL = entry_price + (ATR * 2)

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
        multiplier = self.atr_sl_multiplier.value

        if not trade.is_short:
            # Long: SL below entry
            sl_abs = trade.open_rate - (multiplier * atr)
        else:
            # Short: SL above entry
            sl_abs = trade.open_rate + (multiplier * atr)

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
        Custom exit: Take profit at 4x ATR from entry.

        Logic:
        - Long TP: entry_price + (ATR * 4)
        - Short TP: entry_price - (ATR * 4)
        - Exit when current_rate reaches TP level

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
        tp_multiplier = self.atr_tp_multiplier.value

        # Calculate take profit level
        if not trade.is_short:
            tp_abs = entry_price + (tp_multiplier * atr)
            if current_rate >= tp_abs:
                return "tp_hit"
        else:
            tp_abs = entry_price - (tp_multiplier * atr)
            if current_rate <= tp_abs:
                return "tp_hit"

        return None
