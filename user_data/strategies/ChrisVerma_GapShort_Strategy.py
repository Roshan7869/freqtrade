# pragma pylint: disable=missing-docstring, invalid-name, (pointless-string-statement)
# flake8: noqa: F401
# isort: skip_file
import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import datetime, timedelta
from typing import Optional, Union

from freqtrade.strategy import IStrategy, DecimalParameter
from freqtrade.strategy import merge_informative_pair
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


from freqtrade.persistence import Trade


class ChrisVerma_GapShort_Strategy(IStrategy):
    """
    Chris Verma - Systematic Gap Short Strategy
    ===========================================
    Source: Chris Verma (Small-cap gap fading expert)

    Core Philosophy: "Small-cap pumps are low-volume manipulations destined to fade."

    Execution Models:
    1. Backside Short: Wait for topping action, short the pullback
    2. Liquidity Clearout: Short after PreMarket High rejection
    3. Recycling Technique: Partial exits/re-entries at 9/20 EMA levels

    Key Rules:
    - 10am Rule: If price > Open at 10am, cut position
    - 30min Rule: Check trade health every 30min
    - Edge Window: 4am-12pm (adapted for crypto 24/7)
    """

    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = True

    # Risk Management - Wide stops for manipulation
    stoploss = -1.50  # 150% stop (crypto adapted)
    use_custom_stoploss = True

    # ROI - Let fades run
    minimal_roi = {"0": 100}

    # Recycling EMA parameters (optimizable)
    ema_fast = DecimalParameter(5, 15, default=9, decimals=0, space="buy")
    ema_slow = DecimalParameter(15, 30, default=20, decimals=0, space="buy")

    def informative_pairs(self):
        # Get daily data for gap calculation
        pairs = self.dp.current_whitelist()
        return [(pair, "1d") for pair in pairs]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 1. Daily Context (Gap Detection)
        informative = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe="1d")

        # Gap % (Daily Open vs Prev Close)
        informative["prev_close"] = informative["close"].shift(1)
        informative["gap_pct"] = (
            (informative["open"] - informative["prev_close"])
            / informative["prev_close"]
        ) * 100

        # Volume trend (declining = bullish for shorts)
        informative["vol_sma_5"] = ta.SMA(informative, timeperiod=5, price="volume")
        informative["vol_declining"] = informative["volume"] < informative["vol_sma_5"]

        # Merge to 5m
        dataframe = merge_informative_pair(
            dataframe, informative, self.timeframe, "1d", ffill=True
        )

        # 2. 5m Indicators for Recycling
        dataframe["ema_9"] = ta.EMA(dataframe, timeperiod=int(self.ema_fast.value))
        dataframe["ema_20"] = ta.EMA(dataframe, timeperiod=int(self.ema_slow.value))

        # RSI for overbought (topping detection)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # Identify day boundaries and track Open price
        dataframe["date_only"] = dataframe["date"].dt.date
        dataframe["time_only"] = dataframe["date"].dt.time

        # Daily Open (first candle of day = crypto doesn't have traditional "open" like stocks)
        # Use 00:00 UTC candle as proxy
        dataframe["is_day_start"] = (dataframe["date"].dt.hour == 0) & (
            dataframe["date"].dt.minute == 0
        )
        dataframe["day_open_raw"] = np.where(
            dataframe["is_day_start"], dataframe["open"], np.nan
        )
        dataframe["day_open"] = dataframe.groupby(dataframe["date"].dt.date)[
            "day_open_raw"
        ].transform("first")

        # PreMarket High simulation (use first 4 hours of day as "premarket")
        # Since crypto is 24/7, we'll use "previous 4 hours high" before current candle
        dataframe["pmh"] = (
            dataframe["high"].rolling(window=48).max().shift(1)
        )  # 48 bars = 4 hours on 5m

        # Topping signals (wicks + red candles)
        dataframe["upper_wick"] = dataframe["high"] - dataframe[["open", "close"]].max(
            axis=1
        )
        dataframe["body"] = abs(dataframe["close"] - dataframe["open"])
        dataframe["is_topping"] = (
            (dataframe["upper_wick"] > 2 * dataframe["body"])  # Long upper wick
            & (dataframe["close"] < dataframe["open"])  # Red candle
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Model 1: Backside Short
        # Setup: Gap > 75%, RSI > 70 (overbought), Topping confirmed
        # Entry: Short on pullback after top

        gap_condition = dataframe["gap_pct_1d"] > 75.0

        backside_short = (
            gap_condition
            & (dataframe["rsi"] > 70)
            & (dataframe["is_topping"])
            & (dataframe["close"] < dataframe["ema_9"])  # Pullback below fast EMA
        )

        dataframe.loc[backside_short, "enter_short"] = 1
        dataframe.loc[backside_short, "enter_tag"] = "verma_backside"

        # Model 2: PMH Clearout
        # Setup: Price breaks above PMH briefly, then fails back below
        pmh_clearout = (
            gap_condition
            & (dataframe["high"].shift(1) > dataframe["pmh"])  # Prev candle broke PMH
            & (dataframe["close"] < dataframe["pmh"])  # Current close back below
            & (dataframe["vol_declining_1d"])  # Volume declining
        )

        dataframe.loc[pmh_clearout, "enter_short"] = 1
        dataframe.loc[pmh_clearout, "enter_tag"] = "verma_pmh_fail"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "exit_long"] = 0
        dataframe.loc[:, "exit_short"] = 0

        # Recycling Exit: Cover half at 20 EMA support
        # (This is handled in custom_exit, not here)

        # Time-based exit: After 12pm (12:00 UTC), edge diminishes
        # For crypto, we can use "after X hours in trade" instead

        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade: "Trade",
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        # 10am Rule: If we're past "10am equivalent" (10 hours into day? or 10am UTC?)
        # For crypto, let's use: If held > 10 hours AND price > entry, cut
        duration = current_time - trade.open_date
        hours_held = duration.total_seconds() / 3600

        if hours_held > 10 and current_profit < 0:
            # Not working out, tighter stop
            return -0.20

        # Default wide stop (survive manipulation)
        return self.stoploss

    def custom_exit(
        self,
        pair: str,
        trade: "Trade",
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[Union[str, bool]]:
        # Recycling Logic: Take partial profits at EMA levels
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        ema_20 = last_candle.get("ema_20", current_rate)

        # If we're in profit and price touches 20 EMA (support for shorts = resistance for price)
        # Cover half (return "recycling_half")
        if current_profit > 0.05 and abs(current_rate - ema_20) / current_rate < 0.01:
            return "verma_recycle_ema20"

        # 30min Rule: If not green after 30min, exit
        duration = current_time - trade.open_date
        minutes_held = duration.total_seconds() / 60

        if minutes_held > 30 and current_profit < 0:
            return "verma_30min_rule"

        return None
