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


class MeanReversionBBStrategy(IStrategy):
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
                reasoning=f"Mean Reversion Signal ({entry_tag})",
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
    A mean reversion strategy using Bollinger Bands for perpetual futures.
    
    Concept:
    - Price tends to revert to the mean (middle Bollinger Band)
    - Enter when price deviates significantly from mean (touches outer bands)
    - Exit when price returns to the opposite band
    
    Indicators:
    - Bollinger Bands: Entry signals (lower/upper band touches)
    - 4h RSI: Higher timeframe trend filter
    - 1h & 4h ADX: Trend strength confirmation
    - ATR: Dynamic stop-loss calculation
    
    Entry Logic:
    - LONG: Close < lower BB + 4h RSI > 55 + ADX filters
    - SHORT: Close > upper BB + 4h RSI < 45 + ADX filters
    
    Exit Logic:
    - LONG TP: Close > upper BB (full reversion)
    - SHORT TP: Close < lower BB (full reversion)
    - SL: ATR-based (4.5x ATR from signal candle)
    
    Timeframe: 1h with 4h informative
    """

    # Strategy interface version
    INTERFACE_VERSION = 3

    # Can this strategy go short?
    can_short: bool = True

    # Minimal ROI (disabled since we use indicator-based TP)
    minimal_roi = {"0": 100}

    # Wide initial stoploss to allow custom dynamic SL
    stoploss = -0.99

    # Trailing stoploss (disabled)
    trailing_stop = False

    # Optimal timeframe for the strategy
    timeframe = "1h"

    # Run "populate_indicators()" only for new candle
    process_only_new_candles = True

    # Use indicator-based exits for TP
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Hyperoptable parameters - Bollinger Bands
    bb_period = IntParameter(low=10, high=30, default=20, space="buy", optimize=True, load=True)
    bb_std = DecimalParameter(
        low=1.5, high=2.5, default=2.0, decimals=1, space="buy", optimize=True, load=True
    )

    # Hyperoptable parameters - RSI thresholds (4h)
    rsi_long_threshold = IntParameter(
        low=50, high=60, default=55, space="buy", optimize=True, load=True
    )
    rsi_short_threshold = IntParameter(
        low=40, high=50, default=45, space="sell", optimize=True, load=True
    )

    # Hyperoptable parameters - ADX thresholds
    adx_1h_threshold = IntParameter(
        low=15, high=25, default=20, space="buy", optimize=True, load=True
    )
    adx_4h_threshold = IntParameter(
        low=20, high=30, default=25, space="buy", optimize=True, load=True
    )

    # Hyperoptable parameters - Risk management
    atr_multiplier = DecimalParameter(
        low=3.0, high=6.0, default=4.5, decimals=1, space="sell", optimize=True, load=True
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
            "bb_lowerband": {"color": "red"},
            "bb_middleband": {"color": "yellow"},
            "bb_upperband": {"color": "green"},
        },
        "subplots": {
            "RSI": {
                "rsi": {"color": "purple"},
            },
            "ADX": {
                "adx": {"color": "blue"},
            },
        },
    }

    def informative_pairs(self):
        """
        Define additional, informative pair/interval combinations.
        Returns 4h timeframe for all pairs in whitelist.
        """
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, "4h") for pair in pairs]
        return informative_pairs

    # @informative('4h') decorator removed - using manual merge instead

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds Bollinger Bands, 1h ADX, and ATR indicators to the 1h dataframe.
        Merges 4h informative data.

        Indicators (1h):
        - bb_lowerband, bb_middleband, bb_upperband: Bollinger Bands
        - adx: ADX for trend strength
        - atr: Average True Range for stop-loss
        """
        # Bollinger Bands (hyperoptable period and std)
        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=self.bb_period.value, stds=self.bb_std.value
        )
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]

        # ADX (14 periods) on 1h
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # ATR (14 periods) for SL calculation
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # Volume MA (24 periods) for volume filter
        dataframe["volume_mean_24"] = dataframe["volume"].rolling(window=24).mean()

        # Merge 4h informative data
        informative_4h = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe="4h")
        if len(informative_4h) > 0:
            informative_4h["rsi"] = ta.RSI(informative_4h, timeperiod=14)
            informative_4h["adx"] = ta.ADX(informative_4h, timeperiod=14)
            dataframe = merge_informative_pair(
                dataframe, informative_4h, self.timeframe, "4h", ffill=True
            )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry logic: BB Reversion + Filters + Whale Boost."""
        pair = metadata["pair"]
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # 1. Standard technical conditions
        long_technical = (
            (dataframe["rsi_4h"] > self.rsi_long_threshold.value)
            & (dataframe["adx"] > self.adx_1h_threshold.value)
            & (dataframe["adx_4h"] > self.adx_4h_threshold.value)
            & (dataframe["close"] < dataframe["bb_lowerband"])
            & (dataframe["volume"] > dataframe["volume_mean_24"] * 1.5)
            & (dataframe["volume"] > 0)
        )
        short_technical = (
            (dataframe["rsi_4h"] < self.rsi_short_threshold.value)
            & (dataframe["adx"] > self.adx_1h_threshold.value)
            & (dataframe["adx_4h"] > self.adx_4h_threshold.value)
            & (dataframe["close"] > dataframe["bb_upperband"])
            & (dataframe["volume"] > dataframe["volume_mean_24"] * 1.5)
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_technical, "enter_long"] = 1
        dataframe.loc[long_technical, "enter_tag"] = "technical_reversion"
        dataframe.loc[short_technical, "enter_short"] = 1
        dataframe.loc[short_technical, "enter_tag"] = "technical_reversion"

        # 2. Intelligent Layer: Whale Boost
        whale_signal = self.whale_provider.get_signal(pair)
        if whale_signal:
            if whale_signal.signal_type == "BUY":
                # Relaxed: Only need close < lower BB if whale buy
                whale_long = (dataframe["close"] < dataframe["bb_lowerband"]) & (
                    dataframe["volume"] > 0
                )
                dataframe.loc[whale_long, "enter_long"] = 1
                dataframe.loc[whale_long, "enter_tag"] = "whale_boost_reversion"
            elif whale_signal.signal_type == "SELL":
                whale_short = (dataframe["close"] > dataframe["bb_upperband"]) & (
                    dataframe["volume"] > 0
                )
                dataframe.loc[whale_short, "enter_short"] = 1
                dataframe.loc[whale_short, "enter_tag"] = "whale_boost_reversion"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populates exit signals based on BB reversion (price reaching opposite band).

        Long Exit: Close above upper BB (full mean reversion overshoot)
        Short Exit: Close below lower BB (full mean reversion overshoot)
        """
        # Long exit: Close above upper BB
        dataframe.loc[
            (dataframe["close"] > dataframe["bb_middleband"]),
            "exit_long",
        ] = 1

        # Short exit: Close below lower BB
        dataframe.loc[
            (dataframe["close"] < dataframe["bb_middleband"]),
            "exit_short",
        ] = 1

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

        Uses wider SL (4.5x ATR) for mean reversion to allow for volatility.

        Logic:
        - Long: SL = signal_close - (4.5 * ATR)
        - Short: SL = signal_high + (4.5 * ATR)

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

