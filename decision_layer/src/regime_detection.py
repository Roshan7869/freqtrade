import pandas as pd
import pandas_ta as ta


class MarketRegime:
    """
    Enum-like class to define standard market regimes.
    """

    BULL_TREND = "TRENDING_BULL"
    BEAR_TREND = "TRENDING_BEAR"
    SIDEWAYS = "RANGING"
    PANIC = "PANIC"


class RegimeDetector:
    """
    Standalone class to detect market regimes based on technical indicators.
    Can be used by StrategyOrchestratorStrategy or external analysis scripts.
    """

    @staticmethod
    def calculate_regime_indicators(dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates the necessary indicators for regime detection if they are missing.
        Modifies the dataframe in-place.
        """
        # SMA 200 for Trend Direction
        if "sma_200" not in dataframe.columns:
            dataframe["sma_200"] = ta.sma(dataframe["close"], length=200)

        # ADX for Trend Strength
        if "adx" not in dataframe.columns:
            adx_df = ta.adx(
                dataframe["high"], dataframe["low"], dataframe["close"], length=14
            )
            if adx_df is not None and not adx_df.empty:
                dataframe["adx"] = adx_df["ADX_14"]
            else:
                dataframe["adx"] = 0

        # ATR for Panic Detection
        if "atr" not in dataframe.columns:
            dataframe["atr"] = ta.atr(
                dataframe["high"], dataframe["low"], dataframe["close"], length=14
            )

        if "atr_ma" not in dataframe.columns:
            # Rolling mean of ATR to detect spikes
            dataframe["atr_ma"] = dataframe["atr"].rolling(window=20).mean()

        return dataframe

    @staticmethod
    def identify_regime(row) -> str:
        """
        Classifies a single row (candle) into a regime.
        Logic:
        - PANIC: ATR > 2 * ATR_MA (Volatility Shock)
        - BULL: Close > SMA200 & ADX > 20
        - BEAR: Close < SMA200 & ADX > 20
        - SIDEWAYS: ADX < 20 (Weak Trend)
        """
        if (
            pd.isnull(row["sma_200"])
            or pd.isnull(row["adx"])
            or pd.isnull(row.get("atr"))
        ):
            return MarketRegime.SIDEWAYS

        # 1. Check Panic First (Priority)
        # Using .get because early rows might be NaN for rolling MA
        atr = row.get("atr", 0)
        atr_ma = row.get("atr_ma", 0)

        if atr_ma > 0 and atr > (atr_ma * 2.0):
            return MarketRegime.PANIC

        # 2. Check Trend
        is_bullish_trend = row["close"] > row["sma_200"]
        is_strong_trend = row["adx"] > 20.0  # Relaxed from 25

        if is_strong_trend:
            if is_bullish_trend:
                return MarketRegime.BULL_TREND
            else:
                return MarketRegime.BEAR_TREND
        else:
            return MarketRegime.SIDEWAYS

    @classmethod
    def get_regime(cls, dataframe: pd.DataFrame, candle_index: int = -1) -> str:
        """
        Helper to get the regime for a specific candle (default: latest).
        """
        if dataframe.empty:
            return MarketRegime.SIDEWAYS

        if (
            "sma_200" not in dataframe.columns
            or "adx" not in dataframe.columns
            or "atr_ma" not in dataframe.columns
        ):
            dataframe = cls.calculate_regime_indicators(dataframe)

        try:
            row = dataframe.iloc[candle_index]
            return cls.identify_regime(row)
        except IndexError:
            return MarketRegime.SIDEWAYS
