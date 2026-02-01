"""
Intelligent Layer - LLM Market Analyst
======================================
High-level interface for LLM market regime analysis.
Integrated with Forest Knight's Volume Profile & Behavioral Psychology.

Author: 3-Layer Architecture Refactor (Enhanced)
"""

import logging
import sys
import os
import json
from pathlib import Path

# Setup path for Docker/local compatibility
_docker_path = "/freqtrade/user_data/strategies"
if _docker_path not in sys.path:
    sys.path.insert(0, _docker_path)
_strategies_dir = str(Path(__file__).parent.parent.resolve())
if _strategies_dir not in sys.path:
    sys.path.insert(0, _strategies_dir)

from typing import Optional, Dict, Any
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class MarketRegimeType(str, Enum):
    """Market regime classifications"""

    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"


@dataclass
class MarketRegime:
    """Market regime analysis result"""

    regime: MarketRegimeType
    confidence: float
    risk_score: int
    suggested_leverage: float
    suggested_action: str
    reasoning: str
    timestamp: datetime
    trend_strength: str = "MODERATE"
    volatility: str = "MEDIUM"


class LLMMarketAnalyst:
    """
    High-level interface for LLM-powered market analysis.
    Injected with 'Volume Profile Edge' philosophy.
    """

    def __init__(self):
        self.is_enabled = False
        self._regime_cache = {}

        try:
            from analysis_layer.src.adapters.llm import get_multi_agent_llm

            self._llm = get_multi_agent_llm()
            # Check if any keys are configured in the underlying LLM
            self.is_enabled = any(self._llm.api_keys.values())
            if self.is_enabled:
                logger.info("✅ LLM Market Analyst initialized (VPE Enhanced)")
        except Exception as e:
            logger.warning(f"⚠️ LLM layer not available: {e}")
            self._llm = None

    def get_market_regime(
        self, pair: str, market_data: Dict[str, Any], timeframe: str = "1h"
    ) -> MarketRegime:
        """Get current market regime analysis with hourly caching"""
        if not self.is_enabled:
            return self._get_fallback_regime()

        # Hourly cache
        current_hour = datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        )
        cache_key = f"{pair}_{current_hour.isoformat()}"

        if cache_key in self._regime_cache:
            logger.debug(f"Using cached regime for {pair}")
            return self._regime_cache[cache_key]

        # Call LLM
        try:
            regime_result = self._analyze_via_llm_agent(pair, timeframe, market_data)
            self._regime_cache[cache_key] = regime_result
            logger.info(
                f"LLM Regime for {pair}: {regime_result.regime.value} (confidence: {regime_result.confidence:.2%})"
            )
            return regime_result
        except Exception as e:
            logger.error(f"LLM analysis failed for {pair}: {e}")
            return self._get_fallback_regime()

    def _analyze_via_llm_agent(
        self, pair: str, timeframe: str, market_data: Dict[str, Any]
    ) -> MarketRegime:
        """Construct VPE-enhanced prompt and query the Analyst Agent"""

        # Forest Knight / VPE Philosophy Context
        context_prompt = """
        You are an expert Market Analyst following the Volume Profile Edge and Auction Market Theory.
        
        CORE PHILOSOPHY:
        1. Market Truth: Markets move based on competition. Prices are 'sticky' at high-volume nodes (HVN) and 'slippery' in low-volume areas (LVA).
        2. Behavioral Psychology: Traders react emotionally. When price returns to widespread entry levels (Point of Control), trapped traders exit, causing reactions.
        3. The 50-80% Rule: On volatile candles with long wicks, expect a retest of 50-80% of the wick.
        4. Volatility Warning: High volume doesn't always mean movement; it can mean a 'battle' or consolidation build-up.
        
        TASK:
        Analyze the provided market data chunks (Open/High/Low/Close/Volume) and determine the current market regime.
        
        OUTPUT FORMAT (JSON ONLY):
        {
            "regime": "TRENDING_BULL" | "TRENDING_BEAR" | "RANGING" | "HIGH_VOLATILITY",
            "confidence": 0.0 to 1.0,
            "risk_score": 1 to 10,
            "suggested_leverage": 1.0 to 20.0,
            "suggested_action": "BUY" | "SELL" | "WAIT" | "HOLD",
            "reasoning": "Concise explanation citing Volume Profile concepts (e.g. 'Price accepted above Value Area', 'Rejected from POC').",
            "trend_strength": "WEAK" | "MODERATE" | "STRONG",
            "volatility": "LOW" | "MEDIUM" | "HIGH"
        }
        """

        # Summarize data for prompt (take last 20 candles to fit context)
        # Assuming market_data contains lists
        data_summary = ""
        try:
            close = market_data.get("close", [])[-20:]
            vol = market_data.get("volume", [])[-20:]
            data_summary = f"Recent Close Prices: {close}\nRecent Volumes: {vol}"
        except:
            data_summary = "Data parsing error"

        full_prompt = (
            f"{context_prompt}\n\nMarket Data ({pair} {timeframe}):\n{data_summary}"
        )

        # Async run in sync context (since Freqtrade strategies are sync)
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            response = loop.run_until_complete(self._llm.query("analyst", full_prompt))
            content = response.content

            # Extract JSON
            import re

            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))

                return MarketRegime(
                    regime=MarketRegimeType(data.get("regime", "RANGING")),
                    confidence=float(data.get("confidence", 0.5)),
                    risk_score=int(data.get("risk_score", 5)),
                    suggested_leverage=float(data.get("suggested_leverage", 10.0)),
                    suggested_action=data.get("suggested_action", "WAIT"),
                    reasoning=data.get("reasoning", "Parsed from LLM"),
                    timestamp=datetime.now(timezone.utc),
                    trend_strength=data.get("trend_strength", "MODERATE"),
                    volatility=data.get("volatility", "MEDIUM"),
                )
            else:
                raise ValueError("No JSON found in response")

        except Exception as e:
            logger.error(f"Error querying LLM: {e}")
            raise
        finally:
            loop.close()

    def _get_fallback_regime(self) -> MarketRegime:
        """Conservative fallback when LLM unavailable"""
        return MarketRegime(
            regime=MarketRegimeType.RANGING,
            confidence=0.3,
            risk_score=5,
            suggested_leverage=10.0,
            suggested_action="WAIT",
            reasoning="LLM unavailable - using defaults",
            timestamp=datetime.now(timezone.utc),
        )


# Singleton
_llm_market_analyst = None


def get_llm_market_analyst() -> LLMMarketAnalyst:
    """Get or create the singleton LLMMarketAnalyst instance"""
    global _llm_market_analyst
    if _llm_market_analyst is None:
        _llm_market_analyst = LLMMarketAnalyst()
    return _llm_market_analyst
