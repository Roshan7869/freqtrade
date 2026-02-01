# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these imports ---
from datetime import datetime, timezone
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame
from typing import Optional, Union

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    DecimalParameter,
    IntParameter,
    BooleanParameter,
    informative,
)

import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class AroonMomentumEngine(IStrategy):
    """
    Aroon MomentumEngine (Long Optimization: 'Safe Trend' - Phase 1 Enhanced)

    PHASE 1 ENHANCEMENTS:
    - Multi-Timeframe (4H) Trend Confirmation
    - Dynamic ADX Threshold (volatility-adjusted)
    - Custom Exit with Risk/Reward based Take Profit
    - Three-Tier Filter Architecture (Regime → Timing → Confirmation)

    Best Performing Long Setup:
    - Trend Following with strict filters to avoid 'buying tops' in bear markets.
    - Performance: Reduced Long Losses from -113% to -9% (pre-Phase 1).
    - Note: For Shorts, use 'AroonMomentumEngine_Shorts.py'.

    Architecture: Event-Driven Microservices compatible
    """

    # Strategy interface version
    INTERFACE_VERSION = 3

    # Optimal timeframe
    timeframe = "1h"

    # Can this strategy go short?
    can_short: bool = False  # LONG ONLY

    # ROI handled by custom exit AND time-based decay
    # 0 min: 20%, 60 min: 10%, 24h: 1% (Kill stale trades)
    minimal_roi = {"0": 0.20, "60": 0.10, "1440": 0.01}

    # Stoploss (backup, primary is ATR-based dynamic stop)
    stoploss = -0.08  # -8% hard stop

    # Trailing stop
    trailing_stop = False

    # Run "populate_indicators" only for new candle
    process_only_new_candles = True

    # Startup candle count (increased for 4H MTF data)
    startup_candle_count: int = 200

    # Optional order type mapping
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Optional order time in force
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # ===========================
    # HYPEROPTABLE PARAMETERS
    # ===========================

    aroon_period = IntParameter(
        10, 25, default=14, space="buy", optimize=True, load=True
    )
    aroon_crosswind = IntParameter(
        0, 3, default=2, space="buy", optimize=True, load=True
    )
    macd_crosswind = IntParameter(
        0, 3, default=2, space="buy", optimize=True, load=True
    )
    atr_multiplier = DecimalParameter(
        1.5, 3.5, default=1.8, decimals=1, space="sell", optimize=True, load=True
    )
    risk_reward = DecimalParameter(
        1.5, 3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True
    )
    leverage_multiplier = DecimalParameter(
        1.0, 10.0, default=6.0, decimals=1, space="buy", optimize=False, load=True
    )

    # ===========================
    # PHASE 1: MTF & DYNAMIC FILTERS
    # ===========================

    # 4H MTF Trend Confirmation Parameters
    mtf_ema_period = IntParameter(
        50, 100, default=50, space="buy", optimize=True, load=True
    )
    mtf_slope_lookback = IntParameter(
        3, 10, default=5, space="buy", optimize=False, load=True
    )

    # Dynamic ADX Threshold Parameters
    adx_base_threshold = IntParameter(
        20, 30, default=25, space="buy", optimize=True, load=True
    )
    adx_atr_coupling = DecimalParameter(
        0.0, 2.0, default=1.0, decimals=1, space="buy", optimize=True, load=True
    )
    adx_atr_lookback = IntParameter(
        30, 60, default=50, space="buy", optimize=False, load=True
    )

    def informative_pairs(self):
        return []

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
        Customize leverage for each new trade.
        This method reads leverage from the config file.

        :param pair: Pair that's currently analyzed
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param proposed_leverage: A leverage proposed by the bot.
        :param max_leverage: Max leverage allowed on this pair
        :param entry_tag: Optional entry_tag (buy_tag) if provided with the buy signal.
        :param side: 'long' or 'short' - indicating the direction of the proposed trade
        :return: A leverage amount, which is between 1.0 and max_leverage.
        """
        # Read leverage from config file
        leverage = self.config.get("leverage", 1.0)

        # Ensure it doesn't exceed max_leverage
        return min(leverage, max_leverage)

    # ===========================
    # MULTI-TIMEFRAME (4H) INDICATORS
    # ===========================

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Calculate 4H indicators for Multi-Timeframe trend confirmation.

        This aligns with Event-Driven Microservices architecture by providing
        higher timeframe context for entry decisions.
        """
        # 4H EMAs for trend alignment
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=self.mtf_ema_period.value)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        # 4H EMA slope (trend direction)
        dataframe["ema_slope"] = dataframe["ema_200"] - dataframe["ema_200"].shift(
            self.mtf_slope_lookback.value
        )

        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Aroon
        aroon = ta.AROON(dataframe, timeperiod=self.aroon_period.value)
        dataframe["aroonup"] = aroon["aroonup"]
        dataframe["aroondown"] = aroon["aroondown"]
        dataframe["aroon_osc"] = dataframe["aroonup"] - dataframe["aroondown"]

        # MACD
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]

        # ATR
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # EMA200 & Regime
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema_slope"] = dataframe["ema_200"] - dataframe["ema_200"].shift(5)
        dataframe["dist_to_ema"] = (
            dataframe["close"] - dataframe["ema_200"]
        ) / dataframe["ema_200"]

        # ADX & RSI & Volume
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()

        # ===========================
        # PHASE 1: DYNAMIC ADX THRESHOLD
        # ===========================
        # Normalize ATR to 0-1 range for volatility coupling
        atr_normalized = (
            dataframe["atr"]
            - dataframe["atr"].rolling(self.adx_atr_lookback.value).min()
        ) / (
            dataframe["atr"].rolling(self.adx_atr_lookback.value).max()
            - dataframe["atr"].rolling(self.adx_atr_lookback.value).min()
        )

        # Dynamic ADX threshold: Higher volatility = higher ADX requirement
        # Base threshold + (ATR coupling * normalized ATR * 10)
        dataframe["adx_dynamic_threshold"] = self.adx_base_threshold.value + (
            atr_normalized * self.adx_atr_coupling.value * 10
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # Logic: Aroon Cross + MACD Cross
        aroon_cross_long = qtpylib.crossed_above(
            dataframe["aroonup"], dataframe["aroondown"]
        )
        if self.aroon_crosswind.value >= 2:
            aroon_cross_long = aroon_cross_long | qtpylib.crossed_above(
                dataframe["aroonup"], dataframe["aroondown"]
            ).shift(1)

        macd_cross_long = qtpylib.crossed_above(
            dataframe["macd"], dataframe["macdsignal"]
        )

        aroon_osc_bullish = (dataframe["aroon_osc"] > 0) & (
            dataframe["aroon_osc"] > dataframe["aroon_osc"].shift(1)
        )
        volume_ok = dataframe["volume"] > dataframe["volume_ma"]

        # ===========================
        # PHASE 1: ENHANCED FILTERS
        # ===========================

        # TIER 1: Market Regime Filters (Must Pass)
        # 1. 4H MTF Trend Alignment
        mtf_bullish = (
            (dataframe["close"] > dataframe["ema_50_4h"])  # Price above 4H EMA50
            & (dataframe["ema_slope_4h"] > 0)  # 4H trend rising
        )

        # 2. Dynamic ADX Threshold (volatility-adjusted)
        strong_trend = dataframe["adx"] > dataframe["adx_dynamic_threshold"]

        # TIER 2: Entry Timing Filters (Must Pass)
        # 3. 1H Trend Alignment
        trend_1h_bullish = (
            (dataframe["close"] > dataframe["ema_200"])
            & (dataframe["ema_slope"] > 0)
            & (dataframe["dist_to_ema"] < 0.05)  # Don't buy tops
        )

        # TIER 3: Signal Confirmation (Must Pass)
        # 4. RSI Room to Grow
        rsi_ok = dataframe["rsi"] < 60

        # COMBINED FILTERS (Three-Tier Architecture)
        long_filters = (
            mtf_bullish  # TIER 1: 4H MTF alignment
            & strong_trend  # TIER 1: Dynamic ADX
            & trend_1h_bullish  # TIER 2: 1H trend
            & rsi_ok  # TIER 3: RSI confirmation
        )

        long_conditions = (
            aroon_cross_long
            & aroon_osc_bullish
            & macd_cross_long
            & volume_ok
            & long_filters
        )

        dataframe.loc[long_conditions, "enter_long"] = 1
        dataframe.loc[long_conditions, "enter_tag"] = "aroon_mtf_safe_trend"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

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
        return proposed_stake

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
        return self.leverage_multiplier.value

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
        Fixed Entry-Anchored Stop + Zombie Killer
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        # 1. Zombie Killer (Time Based)
        if not trade.is_short:
            trade_duration = (current_time - trade.open_date_utc).total_seconds() / 60
            if trade_duration > 360 and current_profit < -0.02:
                return -0.01

        # 2. Fixed ATR Stop
        try:
            entry_candle = dataframe.loc[dataframe["date"] == trade.open_date_utc]
            if entry_candle.empty:
                entry_candle = dataframe.loc[
                    dataframe["date"] < trade.open_date_utc
                ].iloc[-1:]

            if entry_candle.empty:
                return self.stoploss

            entry_atr = entry_candle["atr"].values[0]
            if pd.isna(entry_atr) or entry_atr <= 0:
                return self.stoploss

            # Calculate Fixed Stop Price
            # Long: Stop = Entry - (ATR * 1.8)
            stop_price = trade.open_rate - (entry_atr * self.atr_multiplier.value)

            # Distance from CURRENT price
            # Long: -(Current - Stop) / Current
            calculated_sl = -((current_rate - stop_price) / current_rate)

            return calculated_sl

        except Exception:
            return self.stoploss

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
        PHASE 1: Custom Exit for Longs with Risk/Reward based Take Profit

        Take Profit = Entry + (Stop Distance * Risk/Reward Ratio)

        This aligns with Event-Driven Microservices architecture by providing
        deterministic exit signals based on entry conditions.
        """
        # Only apply to long trades
        if trade.is_short:
            return None

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        if len(dataframe) < 1:
            return None

        # Get the ATR value at trade entry
        trade_date = trade.open_date_utc.replace(tzinfo=timezone.utc)

        try:
            entry_candle = dataframe[dataframe["date"] <= trade_date].iloc[-1]
            atr_value = entry_candle["atr"]
        except (IndexError, KeyError):
            return None

        if pd.isna(atr_value) or atr_value <= 0:
            return None

        # Calculate stop and take profit distances
        stop_distance = atr_value * self.atr_multiplier.value
        tp_distance = stop_distance * self.risk_reward.value

        # Take Profit: Entry + (ATR * multiplier * R:R)
        tp_price = trade.open_rate + tp_distance

        if current_rate >= tp_price:
            return f"take_profit_{self.risk_reward.value}R"

        return None
