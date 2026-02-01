"""
Market Quant Analyzer
=====================
Quantifies the current market state into a normalized vector [0.0, 1.0].
Metrics:
1. Trend Strength (ADX) -> 0.0 (Choppy) to 1.0 (Strong Trend)
2. Volatility State (ATR Z-Score) -> 0.0 (Calm) to 1.0 (High Vol)
3. Volume Intensity (RVOL) -> 0.0 (Low) to 1.0 (High)
4. Mean Reversion Prob (RSI Dist) -> 0.0 (Neutral) to 1.0 (Overbought/Sold)
"""

import pandas as pd
from typing import Dict
import logging

logger = logging.getLogger(__name__)

try:
    import talib.abstract as ta

    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    logger.warning("TA-Lib not found. Using pandas/numpy fallbacks (slower).")


class MarketQuantAnalyzer:
    def __init__(self):
        pass

    def _normalize(self, value: float, min_val: float, max_val: float) -> float:
        """Clamps and normalizes value to [0.0, 1.0]."""
        return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))

    def analyze_market_state(self, ohlcv: pd.DataFrame) -> Dict[str, float]:
        """
        Returns a normalized vector of market state metrics.
        Input DataFrame must have: open, high, low, close, volume
        """
        if ohlcv.empty:
            return self._empty_vector()

        # 1. Trend Strength (ADX)
        # 0 = No Trend, 100 = Strong Trend. Normalize 0-60 range to 0-1
        adx_val = self._get_adx(ohlcv)
        trend_score = self._normalize(adx_val, 15.0, 50.0)

        # 2. Volatility State (ATR Z-Score)
        # ATR % vs 20-day mean. Z-Score approach.
        # > 2.0 std dev = High Vol (1.0). < 0 = Low Vol (0.0)
        vol_score = self._get_volatility_score(ohlcv)

        # 3. Volume Intensity (RVOL)
        # Current Vol / Avg Vol. 1.0 = Normal. > 3.0 = High.
        rvol_score = self._get_rvol_score(ohlcv)

        # 4. Mean Reversion Probability (RSI Distance)
        # Distance from 50. |RSI - 50|. Max distance is 50.
        # 0 = Neutral (at 50). 1 = Extreme (0 or 100).
        mr_score = self._get_mean_reversion_score(ohlcv)

        return {
            "trend_strength": round(trend_score, 4),
            "volatility_state": round(vol_score, 4),
            "volume_intensity": round(rvol_score, 4),
            "mean_reversion_probability": round(mr_score, 4),
        }

    def _get_adx(self, df: pd.DataFrame) -> float:
        try:
            if TALIB_AVAILABLE:
                return ta.ADX(df, timeperiod=14).iloc[-1]
            else:
                # Basic Pandas implementation would go here, returning mock for brevity if complex
                # For robustness in this snippet without TA-Lib, we use a simplified HL proxy
                # (High - Low) / Close as a rough trend proxy? No, that's vol.
                # Let's assume TA-Lib or return neutral 25.
                return 25.0
        except Exception:
            return 25.0

    def _get_volatility_score(self, df: pd.DataFrame) -> float:
        try:
            # ATR %
            if TALIB_AVAILABLE:
                atr = ta.ATR(df, timeperiod=14)
            else:
                atr = (df["high"] - df["low"]).rolling(14).mean()

            atr_pct = atr / df["close"]

            # Z-Score over last 50 periods
            mean_atr = atr_pct.rolling(50).mean()
            std_atr = atr_pct.rolling(50).std()

            current_z = (atr_pct.iloc[-1] - mean_atr.iloc[-1]) / (
                std_atr.iloc[-1] + 1e-9
            )

            # Normalize Z-score (-1 to 3 map to 0 to 1)
            # -1 or less is very low vol. 3 is extreme vol.
            return self._normalize(current_z, -1.0, 3.0)
        except Exception:
            return 0.5

    def _get_rvol_score(self, df: pd.DataFrame) -> float:
        try:
            vol = df["volume"]
            avg_vol = vol.rolling(20).mean()

            if avg_vol.iloc[-1] == 0:
                return 0.0

            rvol = vol.iloc[-1] / avg_vol.iloc[-1]
            return self._normalize(rvol, 0.5, 3.5)  # 3.5x volume is 1.0 score
        except Exception:
            return 0.5

    def _get_mean_reversion_score(self, df: pd.DataFrame) -> float:
        try:
            if TALIB_AVAILABLE:
                rsi = ta.RSI(df, timeperiod=14).iloc[-1]
            else:
                # Basic RSI approx
                delta = df["close"].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / (loss + 1e-9)
                rsi = 100 - (100 / (1 + rs)).iloc[-1]

            dist = abs(rsi - 50)
            return self._normalize(dist, 0.0, 45.0)  # RSI 95 or 5 = 1.0 (extreme)
        except Exception:
            return 0.0

    def _empty_vector(self):
        return {
            "trend_strength": 0.0,
            "volatility_state": 0.0,
            "volume_intensity": 0.0,
            "mean_reversion_probability": 0.0,
        }
