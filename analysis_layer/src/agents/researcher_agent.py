"""
Researcher Agent - DeepSeek R1
===============================
Performs deep chain-of-thought reasoning for market regime classification.
This is the first agent in the 4-agent swarm pipeline.
"""

import logging
from typing import Optional, Dict, List
from datetime import datetime
import json

from shared.schemas.a2a import RegimeAssessment, MarketRegimeType
from .model_factory import get_model_factory

logger = logging.getLogger(__name__)


class ResearcherAgent:
    """
    Uses DeepSeek R1 for deep reasoning about market conditions.
    Outputs: RegimeAssessment with regime classification and confidence.
    """

    def __init__(self):
        self.factory = get_model_factory()
        self.agent_name = "researcher"

        if not self.factory.is_agent_available(self.agent_name):
            logger.warning(f"⚠️ {self.agent_name} LLM not available - will use mock")
            self.is_available = False
        else:
            self.is_available = True
            logger.info(f"✅ Researcher Agent initialized (DeepSeek R1)")

    def _build_system_prompt(self) -> str:
        """System prompt optimized for regime reasoning"""
        return """You are a **Market Regime Analyst** for cryptocurrency trading.

Your task: Analyze market data and classify the current regime using deep reasoning.

**Available Regimes:**
1. TRENDING_BULL - Strong upward trend, momentum continues
2. TRENDING_BEAR - Strong downward trend, selling pressure
3. RANGING - Sideways movement, mean reversion likely
4. HIGH_VOLATILITY - Erratic price action, high uncertainty
5. PANIC - Extreme volatility, risk-off mode

**Analysis Framework:**
1. Trend Analysis (ADX, SMA, directional movement)
2. Volatility Assessment (ATR, Bollinger Band width)
3. Volume Patterns (RVOL, unusual activity)
4. Mean Reversion Signals (RSI distance from 50)

**Output Requirements:**
- Provide deep chain-of-thought reasoning
- Consider multiple timeframes if data available
- Be conservative with confidence scores
- Suggest appropriate strategies for the regime
- Assign risk level 1-10 (1=safe, 10=dangerous)

**Response Format (JSON):**
```json
{
  "regime": "TRENDING_BULL",
  "confidence": 0.75,
  "reasoning": "Your detailed chain-of-thought...",
  "trend_strength": 0.65,
  "volatility_state": 0.40,
  "volume_intensity": 0.55,
  "mean_reversion_probability": 0.20,
  "suggested_strategies": ["bull_wma", "momentum_breakout"],
  "risk_level": 5
}
```

Return ONLY valid JSON. No additional text."""

    def _build_user_prompt(
        self,
        pair: str,
        market_vector: Dict[str, float],
        recent_candles: Optional[List[Dict]] = None,
        current_price: Optional[float] = None,
    ) -> str:
        """Build the user prompt with market data"""

        prompt = f"""Analyze the market regime for **{pair}**

**Market Quantification Vector:**
- Trend Strength: {market_vector.get("trend_strength", 0.5):.4f} (0=choppy, 1=strong)
- Volatility State: {market_vector.get("volatility_state", 0.5):.4f} (0=calm, 1=high)
- Volume Intensity: {market_vector.get("volume_intensity", 0.5):.4f} (0=low, 1=high)
- Mean Reversion Prob: {market_vector.get("mean_reversion_probability", 0.5):.4f} (0=neutral, 1=extreme)
"""

        if current_price:
            prompt += f"\n**Current Price:** ${current_price:.2f}\n"

        if recent_candles and len(recent_candles) > 0:
            # Add recent price action context
            prompt += "\n**Recent Price Action (last 5 candles):**\n"
            for i, candle in enumerate(recent_candles[-5:], 1):
                prompt += f"{i}. O:{candle.get('open', 0):.2f} H:{candle.get('high', 0):.2f} L:{candle.get('low', 0):.2f} C:{candle.get('close', 0):.2f} V:{candle.get('volume', 0):.0f}\n"

        prompt += "\nProvide your regime assessment as JSON."

        return prompt

    async def analyze_regime(
        self,
        pair: str,
        market_vector: Dict[str, float],
        recent_candles: Optional[List[Dict]] = None,
        current_price: Optional[float] = None,
    ) -> Optional[RegimeAssessment]:
        """
        Main method: Analyze market and return regime assessment.

        Args:
            pair: Trading pair (e.g., 'SOL/USDT:USDT')
            market_vector: Dict with trend_strength, volatility_state, etc.
            recent_candles: Optional list of recent OHLCV data
            current_price: Optional current price

        Returns:
            RegimeAssessment or None if analysis fails
        """
        if not self.is_available:
            logger.warning("Researcher Agent not available - using fallback")
            return self._fallback_assessment(market_vector)

        try:
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(
                pair, market_vector, recent_candles, current_price
            )

            # Query DeepSeek R1
            logger.info(f"🔬 Researcher analyzing {pair}...")
            start_time = datetime.now()

            response_text = await self.factory.query_agent(
                agent_name=self.agent_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,  # Lower temp for consistent reasoning
                max_tokens=3000,  # Long enough for detailed reasoning
            )

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"⏱️ Researcher completed in {duration:.2f}s")

            if not response_text:
                logger.error("No response from Researcher")
                return self._fallback_assessment(market_vector)

            # Parse JSON response
            assessment_data = self._parse_response(response_text)
            if not assessment_data:
                logger.error("Failed to parse Researcher response")
                return self._fallback_assessment(market_vector)

            # Create Pydantic model
            assessment = RegimeAssessment(**assessment_data)
            logger.info(
                f"✅ Regime: {assessment.regime} (confidence: {assessment.confidence:.2f})"
            )

            return assessment

        except Exception as e:
            logger.error(f"Researcher Agent error: {e}")
            return self._fallback_assessment(market_vector)

    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """Parse JSON from LLM response"""
        try:
            # Try direct JSON parse
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            import re

            json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except:
                    pass

            # Try to extract JSON object
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except:
                    pass

            logger.error(f"Could not parse JSON from response: {response_text[:200]}")
            return None

    def _fallback_assessment(self, market_vector: Dict[str, float]) -> RegimeAssessment:
        """Fallback regime classification using simple rules"""
        trend_strength = market_vector.get("trend_strength", 0.5)
        volatility_state = market_vector.get("volatility_state", 0.5)
        volume_intensity = market_vector.get("volume_intensity", 0.5)
        mean_reversion = market_vector.get("mean_reversion_probability", 0.5)

        # Simple rule-based classification
        if volatility_state > 0.7:
            regime = MarketRegimeType.HIGH_VOLATILITY
            risk_level = 8
            strategies = []
        elif trend_strength > 0.6:
            if mean_reversion < 0.3:  # Not in extreme
                regime = MarketRegimeType.TRENDING_BULL
                strategies = ["bull_wma", "momentum_breakout"]
            else:
                regime = MarketRegimeType.TRENDING_BEAR
                strategies = ["bear_wma_short"]
            risk_level = 6
        else:
            regime = MarketRegimeType.RANGING
            strategies = ["range_aroon"]
            risk_level = 4

        return RegimeAssessment(
            regime=regime,
            confidence=0.5,  # Low confidence for fallback
            reasoning="Fallback assessment (Researcher LLM unavailable)",
            trend_strength=trend_strength,
            volatility_state=volatility_state,
            volume_intensity=volume_intensity,
            mean_reversion_probability=mean_reversion,
            suggested_strategies=strategies,
            risk_level=risk_level,
        )


# Singleton instance
_researcher_agent = None


def get_researcher_agent() -> ResearcherAgent:
    """Get singleton Researcher Agent instance"""
    global _researcher_agent
    if _researcher_agent is None:
        _researcher_agent = ResearcherAgent()
    return _researcher_agent
