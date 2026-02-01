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
)

import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class AroonMomentumEngine_Shorts(IStrategy):
    """
    Aroon Momentum Engine Strategy

    Based on Quant Tactics methodology:
    - Trend Detection: Aroon Indicator (14-period)
    - Momentum Confirmation: MACD (12, 26, 9)
    - Risk Management: ATR-based dynamic stops (2.5x multiplier)
    - Target: 2:1 Reward-to-Risk ratio

    Performance Benchmark: 291% return on ARB/USDT (8-month in-sample + 4-month out-of-sample)
    """

    # Strategy interface version
    INTERFACE_VERSION = 3

    # Optimal timeframe
    timeframe = "1h"

    # Can this strategy go short?
    can_short: bool = True

    # ROI handled by custom exit AND time-based decay
    # 0 min: 20%, 60 min: 10%, 24h: 1% (Kill stale trades)
    minimal_roi = {"0": 0.20, "60": 0.10, "1440": 0.01}

    # Stoploss (backup, primary is ATR-based dynamic stop)
    stoploss = -0.25  # -25% hard stop

    # Trailing stop
    trailing_stop = False  # We use fixed TP/SL based on ATR

    # Run "populate_indicators" only for new candle
    process_only_new_candles = True

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 100

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

    # Aroon period
    aroon_period = IntParameter(
        low=10,
        high=25,
        default=14,
        space="buy",
        optimize=True,
        load=True,
    )

    # Aroon crosswind (lookback for non-simultaneous crosses)
    aroon_crosswind = IntParameter(
        low=0,
        high=3,
        default=2,
        space="buy",
        optimize=True,
        load=True,
    )

    # MACD crosswind (lookback for non-simultaneous crosses)
    macd_crosswind = IntParameter(
        low=0,
        high=3,
        default=2,
        space="buy",
        optimize=True,
        load=True,
    )

    # ATR multiplier for stop loss (REDUCED from 2.5 to 1.8 to cut losses faster)
    atr_multiplier = DecimalParameter(
        low=1.5,
        high=3.5,
        default=1.8,
        decimals=1,
        space="sell",
        optimize=True,
        load=True,
    )

    # Risk/Reward ratio
    risk_reward = DecimalParameter(
        low=1.5,
        high=3.0,
        default=2.0,
        decimals=1,
        space="sell",
        optimize=True,
        load=True,
    )

    def informative_pairs(self):
        """Define additional informative pair/interval combinations."""
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

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Calculate all technical indicators required for the strategy.

        Indicators:
        - Aroon Up/Down (trend direction)
        - Aroon Oscillator (trend strength)
        - MACD (momentum confirmation)
        - ATR (volatility for dynamic stops)
        """

        # Aroon Indicator (14-period default)
        aroon = ta.AROON(dataframe, timeperiod=self.aroon_period.value)
        dataframe["aroonup"] = aroon["aroonup"]
        dataframe["aroondown"] = aroon["aroondown"]

        # Aroon Oscillator (Aroon Up - Aroon Down)
        dataframe["aroon_osc"] = dataframe["aroonup"] - dataframe["aroondown"]

        # MACD (12, 26, 9)
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # ATR (14-period for dynamic stop loss)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # EMA200 & Regime Filter
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        # Slope: Current EMA - EMA 5 candles ago
        dataframe["ema_slope"] = dataframe["ema_200"] - dataframe["ema_200"].shift(5)
        # Distance to EMA (Extension check)
        dataframe["dist_to_ema"] = (
            dataframe["close"] - dataframe["ema_200"]
        ) / dataframe["ema_200"]

        # ADX (Trend Strength)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # Volume (basic filter + Moving Average)
        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry signal generation based on Aroon + MACD confluence.

        LONG Entry Conditions:
        1. Aroon Up crosses ABOVE Aroon Down (within crosswind lookback)
        2. Aroon Oscillator > 0 AND increasing
        3. MACD crosses ABOVE Signal line (within crosswind lookback)

        SHORT Entry Conditions:
        1. Aroon Down crosses ABOVE Aroon Up (within crosswind lookback)
        2. Aroon Oscillator < 0 AND decreasing
        3. MACD crosses BELOW Signal line (within crosswind lookback)
        """

        # Initialize entry columns
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # ===========================
        # LONG ENTRY LOGIC
        # ===========================

        # Aroon crossover detection (with crosswind tolerance)
        aroon_cross_long = qtpylib.crossed_above(
            dataframe["aroonup"], dataframe["aroondown"]
        ) | qtpylib.crossed_above(dataframe["aroonup"], dataframe["aroondown"]).shift(1)
        if self.aroon_crosswind.value >= 2:
            aroon_cross_long = aroon_cross_long | qtpylib.crossed_above(
                dataframe["aroonup"], dataframe["aroondown"]
            ).shift(2)
        if self.aroon_crosswind.value >= 3:
            aroon_cross_long = aroon_cross_long | qtpylib.crossed_above(
                dataframe["aroonup"], dataframe["aroondown"]
            ).shift(3)

        # MACD crossover detection (with crosswind tolerance)
        macd_cross_long = qtpylib.crossed_above(
            dataframe["macd"], dataframe["macdsignal"]
        ) | qtpylib.crossed_above(dataframe["macd"], dataframe["macdsignal"]).shift(1)
        if self.macd_crosswind.value >= 2:
            macd_cross_long = macd_cross_long | qtpylib.crossed_above(
                dataframe["macd"], dataframe["macdsignal"]
            ).shift(2)
        if self.macd_crosswind.value >= 3:
            macd_cross_long = macd_cross_long | qtpylib.crossed_above(
                dataframe["macd"], dataframe["macdsignal"]
            ).shift(3)

        # Aroon Oscillator momentum check
        aroon_osc_bullish = (
            (dataframe["aroon_osc"] > 0)
            & (dataframe["aroon_osc"] > dataframe["aroon_osc"].shift(1))  # Increasing
        )

        # Volume filter (Volume > SMA20)
        volume_ok = dataframe["volume"] > dataframe["volume_ma"]

        # EXPERT LONG FILTERS:
        # 1. Trend Direction: Price > EMA200
        # 2. Regime: EMA Slope > 0 (Rising trend)
        # 3. Extension: Price < 10% above EMA (Don't buy tops)
        # 4. Strength: ADX > 20 (Trend exists) AND ADX < 40 (Not exhausted)

        long_filters = (
            (dataframe["close"] > dataframe["ema_200"])
            & (dataframe["ema_slope"] > 0)
            & (dataframe["dist_to_ema"] < 0.10)
            & (dataframe["adx"] > 20)
            & (dataframe["adx"] < 40)
        )

        # Combine all long conditions
        long_conditions = (
            aroon_cross_long
            & aroon_osc_bullish
            & macd_cross_long
            & volume_ok
            & long_filters
        )

        dataframe.loc[long_conditions, "enter_long"] = 0  # DISABLE LONGS
        dataframe.loc[long_conditions, "enter_tag"] = "long_disabled"

        # ===========================
        # SHORT ENTRY LOGIC
        # ===========================

        # Aroon crossover detection (with crosswind tolerance)
        aroon_cross_short = qtpylib.crossed_above(
            dataframe["aroondown"], dataframe["aroonup"]
        ) | qtpylib.crossed_above(dataframe["aroondown"], dataframe["aroonup"]).shift(1)
        if self.aroon_crosswind.value >= 2:
            aroon_cross_short = aroon_cross_short | qtpylib.crossed_above(
                dataframe["aroondown"], dataframe["aroonup"]
            ).shift(2)
        if self.aroon_crosswind.value >= 3:
            aroon_cross_short = aroon_cross_short | qtpylib.crossed_above(
                dataframe["aroondown"], dataframe["aroonup"]
            ).shift(3)

        # MACD crossover detection (with crosswind tolerance)
        macd_cross_short = qtpylib.crossed_below(
            dataframe["macd"], dataframe["macdsignal"]
        ) | qtpylib.crossed_below(dataframe["macd"], dataframe["macdsignal"]).shift(1)
        if self.macd_crosswind.value >= 2:
            macd_cross_short = macd_cross_short | qtpylib.crossed_below(
                dataframe["macd"], dataframe["macdsignal"]
            ).shift(2)
        if self.macd_crosswind.value >= 3:
            macd_cross_short = macd_cross_short | qtpylib.crossed_below(
                dataframe["macd"], dataframe["macdsignal"]
            ).shift(3)

        # Aroon Oscillator momentum check
        aroon_osc_bearish = (
            (dataframe["aroon_osc"] < 0)
            & (dataframe["aroon_osc"] < dataframe["aroon_osc"].shift(1))  # Decreasing
        )

        # Combine all short conditions
        short_conditions = (
            aroon_cross_short & aroon_osc_bearish & macd_cross_short & volume_ok
        )

        dataframe.loc[short_conditions, "enter_short"] = 1
        dataframe.loc[short_conditions, "enter_tag"] = "aroon_macd_short"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit signals (optional - primary exits are via custom_stoploss and custom_exit).
        """
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
        """
        Customize stake amount based on user-defined leverage multiplier.
        """
        # Use the leverage_multiplier parameter
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
        """
        Set leverage based on user-defined parameter.
        """
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
        Dynamic stop loss based on ATR at entry.

        LONG: Stop = Entry Price - (ATR * multiplier)
        SHORT: Stop = Entry Price + (ATR * multiplier)
        """

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        if len(dataframe) < 1:
            return self.stoploss

        # Get the ATR value at trade entry
        trade_date = trade.open_date_utc.replace(tzinfo=timezone.utc)

        # Find the candle closest to trade entry
        try:
            entry_candle = dataframe[dataframe["date"] <= trade_date].iloc[-1]
            atr_value = entry_candle["atr"]
        except (IndexError, KeyError):
            return self.stoploss

        if pd.isna(atr_value) or atr_value <= 0:
            return self.stoploss

        # Calculate stop loss distance
        stop_distance = atr_value * self.atr_multiplier.value

        # Convert to percentage
        if trade.is_short:
            # For shorts: stop is ABOVE entry
            stop_price = trade.open_rate + stop_distance
            stop_loss_pct = -((stop_price - current_rate) / current_rate)
        else:
            # For longs: stop is BELOW entry
            stop_price = trade.open_rate - stop_distance
            stop_loss_pct = -((current_rate - stop_price) / current_rate)

        # Ensure stop loss is negative and not too tight
        return max(stop_loss_pct, self.stoploss)

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
        Custom exit logic for take profit based on Risk/Reward ratio.

        Take Profit = Entry + (Stop Distance * Risk/Reward Ratio)
        """

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

        if trade.is_short:
            # For shorts: TP is BELOW entry
            tp_price = trade.open_rate - tp_distance
            if current_rate <= tp_price:
                return "take_profit_2R"
        else:
            # For longs: TP is ABOVE entry
            tp_price = trade.open_rate + tp_distance
            if current_rate >= tp_price:
                return "take_profit_2R"

        return None
