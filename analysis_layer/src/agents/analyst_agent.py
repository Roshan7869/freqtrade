"""
Analyst Agent - Qwen Coder
===========================
Technical verification and signal validation using code-oriented reasoning.
Second agent in the 4-agent swarm pipeline.
"""

import logging
from typing import Optional, Dict, List
from datetime import datetime
import json

from shared.schemas.a2a import RegimeAssessment, SignalProposal, SignalDirection
from .model_factory import get_model_factory

logger = logging.getLogger(__name__)


class AnalystAgent:
    """
    Uses Qwen Coder for technical analysis and signal validation.
    Receives: RegimeAssessment
    Outputs: SignalProposal
    """

    def __init__(self):
        self.factory = get_model_factory()
        self.agent_name = "analyst"

        if not self.factory.is_agent_available(self.agent_name):
            logger.warning(f"⚠️ {self.agent_name} LLM not available - will use mock")
            self.is_available = False
        else:
            self.is_available = True
            logger.info(f"✅ Analyst Agent initialized (Qwen Coder)")

    def _build_system_prompt(self) -> str:
        """System prompt optimized for technical validation"""
        return """You are a **Technical Analysis Specialist** for cryptocurrency trading.

Your task: Verify regime assessment with technical indicators and propose specific signals.

**Your Expertise:**
- Technical indicator calculation and interpretation
- Chart pattern recognition
- Entry/exit point determination
- Multi-timeframe confirmation

**Analysis Process:**
1. Verify regime matches technical indicators
2. Identify specific entry points
3. Calculate stop loss (ATR-based)
4. Calculate take profit (risk-reward ratio)
5. Assess pattern quality/strength

**Signal Criteria:**
- TRENDING_BULL: MACD cross + EMA alignment + RSI < 70
- TRENDING_BEAR: MACD cross down + EMA bearish + RSI > 30
- RANGING: BB touch + RSI extremes (< 30 or > 70)
- HIGH_VOLATILITY: NO SIGNAL (safety)

**Output Format (JSON):**
```json
{
  "direction": "BUY",
  "pair": "SOL/USDT:USDT",
  "entry_price": 145.20,
  "stop_loss": 142.00,
  "take_profit": 152.60,
  "technical_score": 0.78,
  "indicators_used": ["MACD_cross", "RSI_oversold", "EMA_alignment"],
  "pattern_detected": "Bullish engulfing",
  "strategy_name": "AroonMACDStrategy",
  "timeframe": "1h",
  "verification_notes": "Detailed technical reasoning...",
  "warnings": []
}
```

Return ONLY valid JSON. No additional text."""

    def _build_user_prompt(
        self,
        pair: str,
        regime_assessment: RegimeAssessment,
        indicators: Dict[str, float],
        current_price: float,
        timeframe: str = "1h",
    ) -> str:
        """Build user prompt with regime + technical data"""

        prompt = f"""Analyze and verify trading signal for **{pair}** on **{timeframe}** timeframe

**REGIME ASSESSMENT (from Researcher):**
- Regime: {regime_assessment.regime}
- Confidence: {regime_assessment.confidence:.2f}
- Risk Level: {regime_assessment.risk_level}/10
- Suggested Strategies: {", ".join(regime_assessment.suggested_strategies)}
- Reasoning: {regime_assessment.reasoning[:200]}...

**CURRENT TECHNICALS:**
- Price: ${current_price:.2f}
"""

        # Add available indicators
        if "rsi" in indicators:
            prompt += f"- RSI: {indicators['rsi']:.2f}\n"
        if "adx" in indicators:
            prompt += f"- ADX: {indicators['adx']:.2f}\n"
        if "macd" in indicators:
            prompt += f"- MACD: {indicators['macd']:.4f}\n"
        if "macdsignal" in indicators:
            prompt += f"- MACD Signal: {indicators['macdsignal']:.4f}\n"
        if "atr" in indicators:
            prompt += f"- ATR: {indicators['atr']:.2f}\n"
        if "ema_fast" in indicators:
            prompt += f"- EMA Fast: {indicators['ema_fast']:.2f}\n"
        if "ema_slow" in indicators:
            prompt += f"- EMA Slow: {indicators['ema_slow']:.2f}\n"
        if "bb_lower" in indicators:
            prompt += f"- BB Lower: {indicators['bb_lower']:.2f}\n"
        if "bb_upper" in indicators:
            prompt += f"- BB Upper: {indicators['bb_upper']:.2f}\n"

        prompt += f"\n**TASK:**\n"
        prompt += (
            f"1. Verify if technicals match the {regime_assessment.regime} regime\n"
        )
        prompt += f"2. If valid, propose a specific signal (BUY/SELL/HOLD)\n"
        prompt += f"3. Calculate entry, stop loss, and take profit\n"
        prompt += f"4. Provide detailed verification notes\n\n"
        prompt += f"Provide your signal proposal as JSON."

        return prompt

    async def verify_and_propose_signal(
        self,
        pair: str,
        regime_assessment: RegimeAssessment,
        indicators: Dict[str, float],
        current_price: float,
        timeframe: str = "1h",
    ) -> Optional[SignalProposal]:
        """
        Main method: Verify regime and propose trading signal.

        Args:
            pair: Trading pair
            regime_assessment: Output from Researcher Agent
            indicators: Dict of technical indicators
            current_price: Current market price
            timeframe: Timeframe being analyzed

        Returns:
            SignalProposal or None
        """
        if not self.is_available:
            logger.warning("Analyst Agent not available - using fallback")
            return self._fallback_signal(
                pair, regime_assessment, indicators, current_price, timeframe
            )

        try:
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(
                pair, regime_assessment, indicators, current_price, timeframe
            )

            logger.info(
                f"📊 Analyst verifying {regime_assessment.regime} for {pair}..."
            )
            start_time = datetime.now()

            response_text = await self.factory.query_agent(
                agent_name=self.agent_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,  # Very low for precise technical analysis
                max_tokens=2000,
            )

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"⏱️ Analyst completed in {duration:.2f}s")

            if not response_text:
                logger.error("No response from Analyst")
                return self._fallback_signal(
                    pair, regime_assessment, indicators, current_price, timeframe
                )

            # Parse JSON
            signal_data = self._parse_response(response_text)
            if not signal_data:
                logger.error("Failed to parse Analyst response")
                return self._fallback_signal(
                    pair, regime_assessment, indicators, current_price, timeframe
                )

            # Create Pydantic model
            signal = SignalProposal(**signal_data)
            logger.info(
                f"✅ Signal: {signal.direction} @ {signal.entry_price} (score: {signal.technical_score:.2f})"
            )

            return signal

        except Exception as e:
            logger.error(f"Analyst Agent error: {e}")
            return self._fallback_signal(
                pair, regime_assessment, indicators, current_price, timeframe
            )

    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """Parse JSON from LLM response"""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            import re

            # Try markdown code block
            json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except:
                    pass

            # Try JSON object extraction
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except:
                    pass

            logger.error(f"Could not parse JSON: {response_text[:200]}")
            return None

    def _fallback_signal(
        self,
        pair: str,
        regime: RegimeAssessment,
        indicators: Dict[str, float],
        current_price: float,
        timeframe: str,
    ) -> SignalProposal:
        """Simple rule-based signal generation"""

        # Default to HOLD
        direction = SignalDirection.HOLD
        entry = current_price
        stop_loss = current_price * 0.98
        take_profit = current_price * 1.02
        indicators_used = []
        pattern = None

        atr = indicators.get("atr", current_price * 0.02)

        # Simple regime-based logic
        if regime.regime == "TRENDING_BULL":
            macd = indicators.get("macd", 0)
            macd_signal = indicators.get("macdsignal", 0)
            rsi = indicators.get("rsi", 50)

            if macd > macd_signal and rsi < 70:
                direction = SignalDirection.BUY
                entry = current_price
                stop_loss = current_price - (atr * 2.0)
                take_profit = current_price + (atr * 4.0)
                indicators_used = ["MACD_cross", "RSI_check"]

        elif regime.regime == "TRENDING_BEAR":
            direction = SignalDirection.HOLD  # Conservative fallback

        elif regime.regime == "RANGING":
            rsi = indicators.get("rsi", 50)
            bb_lower = indicators.get("bb_lower", current_price * 0.98)
            bb_upper = indicators.get("bb_upper", current_price * 1.02)

            if current_price <= bb_lower and rsi < 30:
                direction = SignalDirection.BUY
                entry = current_price
                stop_loss = current_price - (atr * 1.5)
                take_profit = current_price + (atr * 2.0)
                indicators_used = ["BB_lower", "RSI_oversold"]

        return SignalProposal(
            direction=direction,
            pair=pair,
            entry_price=entry if direction != SignalDirection.HOLD else None,
            stop_loss=stop_loss if direction != SignalDirection.HOLD else None,
            take_profit=take_profit if direction != SignalDirection.HOLD else None,
            technical_score=0.5,
            indicators_used=indicators_used,
            pattern_detected=pattern,
            strategy_name="Fallback",
            timeframe=timeframe,
            verification_notes="Fallback signal (Analyst LLM unavailable)",
            warnings=["Using fallback logic - Analyst not available"],
        )


# Singleton
_analyst_agent = None


def get_analyst_agent() -> AnalystAgent:
    """Get singleton Analyst Agent instance"""
    global _analyst_agent
    if _analyst_agent is None:
        _analyst_agent = AnalystAgent()
    return _analyst_agent
