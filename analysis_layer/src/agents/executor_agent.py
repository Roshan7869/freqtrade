"""
Executor Agent - Llama 3.1 70B
===============================
Trade execution strategy and position sizing.
Third agent in the 4-agent swarm pipeline.
"""

import logging
from typing import Optional, Dict
from datetime import datetime
import json

from shared.schemas.a2a import (
    SignalProposal,
    DraftOrder,
    SignalDirection,
    RegimeAssessment,
)
from .model_factory import get_model_factory

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """
    Uses Llama 3.1 for order execution strategy.
    Receives: SignalProposal, RegimeAssessment
    Outputs: DraftOrder
    """

    def __init__(self):
        self.factory = get_model_factory()
        self.agent_name = "executor"

        if not self.factory.is_agent_available(self.agent_name):
            logger.warning(f"⚠️ {self.agent_name} LLM not available - will use mock")
            self.is_available = False
        else:
            self.is_available = True
            logger.info(f"✅ Executor Agent initialized (Llama 3.1)")

    def _build_system_prompt(self) -> str:
        """System prompt for execution strategy"""
        return """You are an **Order Execution Strategist** for cryptocurrency trading.

Your task: Convert validated signals into executable orders with proper sizing and risk management.

**Responsibilities:**
1. Determine order type (LIMIT vs MARKET)
2. Calculate position size based on portfolio and risk rules
3. Set final leverage based on regime confidence
4. Choose execution strategy (immediate, TWAP, etc.)
5. Create entry tags for tracking

**Position Sizing Rules:**
- Max 10% of portfolio per trade
- Risk per trade: 1-3% based on confidence
- Leverage: 5x (safe) to 20x (high confidence)
- Account for existing exposure

**Leverage Guidelines:**
- TRENDING_BULL/BEAR + High confidence: 12-15x
- RANGING: 6-8x
- HIGH_VOLATILITY: 3-5x or skip
- PANIC: 0x (no trades)

**Output Format (JSON):**
```json
{
  "direction": "BUY",
  "pair": "SOL/USDT:USDT",
  "order_type": "LIMIT",
  "price": 145.20,
  "quantity": 10.0,
  "quantity_usd": 1452.00,
  "leverage": 8.0,
  "stop_loss": 142.00,
  "take_profit": 152.60,
  "portfolio_allocation_pct": 5.0,
  "risk_per_trade_pct": 2.0,
  "execution_strategy": "IMMEDIATE",
  "entry_tag": "swarm_bull_entry",
  "sizing_justification": "Detailed reasoning...",
  "execution_notes": "Special instructions..."
}
```

Return ONLY valid JSON."""

    def _build_user_prompt(
        self,
        signal: SignalProposal,
        regime: RegimeAssessment,
        portfolio_balance: float,
        existing_exposure_pct: float = 0.0,
    ) -> str:
        """Build prompt with signal and portfolio data"""

        prompt = f"""Create execution order for **{signal.pair}**

**VALIDATED SIGNAL (from Analyst):**
- Direction: {signal.direction}
- Entry Price: ${signal.entry_price}
- Stop Loss: ${signal.stop_loss}
- Take Profit: ${signal.take_profit}
- Technical Score: {signal.technical_score:.2f}
- Strategy: {signal.strategy_name}
- Timeframe: {signal.timeframe}
- Verification: {signal.verification_notes[:150]}...

**MARKET REGIME (from Researcher):**
- Regime: {regime.regime}
- Confidence: {regime.confidence:.2f}
- Risk Level: {regime.risk_level}/10

**PORTFOLIO STATE:**
- Total Balance: ${portfolio_balance:,.2f}
- Existing Exposure: {existing_exposure_pct:.1f}%
- Available for Trade: {100 - existing_exposure_pct:.1f}%

**TASK:**
1. Calculate optimal position size (balance, risk, confidence)
2. Determine leverage (regime, confidence, risk_level)
3. Choose order type (LIMIT for better fill, MARKET for urgency)
4. Set execution strategy
5. Create descriptive entry tag

Provide the draft order as JSON."""

        return prompt

    async def create_draft_order(
        self,
        signal: SignalProposal,
        regime: RegimeAssessment,
        portfolio_balance: float,
        existing_exposure_pct: float = 0.0,
    ) -> Optional[DraftOrder]:
        """
        Main method: Create draft order from Signal.

        Args:
            signal: Validated signal from Analyst
            regime: Regime assessment from Researcher
            portfolio_balance: Total portfolio in USD
            existing_exposure_pct: Current exposure percentage

        Returns:
            DraftOrder or None
        """
        # Skip if signal is HOLD
        if signal.direction == SignalDirection.HOLD:
            logger.info("Signal is HOLD - no order to create")
            return None

        if not self.is_available:
            logger.warning("Executor Agent not available - using fallback")
            return self._fallback_order(
                signal, regime, portfolio_balance, existing_exposure_pct
            )

        try:
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(
                signal, regime, portfolio_balance, existing_exposure_pct
            )

            logger.info(f"⚡ Executor creating order for {signal.pair}...")
            start_time = datetime.now()

            response_text = await self.factory.query_agent(
                agent_name=self.agent_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,  # Moderate for balanced decisions
                max_tokens=1500,
            )

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"⏱️ Executor completed in {duration:.2f}s")

            if not response_text:
                logger.error("No response from Executor")
                return self._fallback_order(
                    signal, regime, portfolio_balance, existing_exposure_pct
                )

            # Parse JSON
            order_data = self._parse_response(response_text)
            if not order_data:
                logger.error("Failed to parse Executor response")
                return self._fallback_order(
                    signal, regime, portfolio_balance, existing_exposure_pct
                )

            # Create Pydantic model
            order = DraftOrder(**order_data)
            logger.info(
                f"✅ Draft Order: {order.direction} {order.quantity:.2f} @ {order.leverage}x"
            )

            return order

        except Exception as e:
            logger.error(f"Executor Agent error: {e}")
            return self._fallback_order(
                signal, regime, portfolio_balance, existing_exposure_pct
            )

    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """Parse JSON from response"""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            import re

            json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except:
                    pass

            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except:
                    pass

            return None

    def _fallback_order(
        self,
        signal: SignalProposal,
        regime: RegimeAssessment,
        portfolio_balance: float,
        existing_exposure_pct: float,
    ) -> DraftOrder:
        """Simple rule-based order creation"""

        # Conservative position sizing
        available_pct = min(100 - existing_exposure_pct, 10)  # Max 10%
        risk_pct = 2.0 if regime.confidence > 0.7 else 1.5
        allocation_pct = min(available_pct, risk_pct * 3)  # 3x risk as allocation

        # Leverage based on regime
        if (
            regime.regime in ["TRENDING_BULL", "TRENDING_BEAR"]
            and regime.confidence > 0.7
        ):
            leverage = 10.0
        elif regime.regime == "RANGING":
            leverage = 6.0
        else:
            leverage = 5.0

        # Calculate quantity
        quantity_usd = portfolio_balance * (allocation_pct / 100)
        quantity = quantity_usd / signal.entry_price if signal.entry_price else 0

        return DraftOrder(
            direction=signal.direction,
            pair=signal.pair,
            order_type="LIMIT",
            price=signal.entry_price,
            quantity=quantity,
            quantity_usd=quantity_usd,
            leverage=leverage,
            stop_loss=signal.stop_loss or signal.entry_price * 0.98,
            take_profit=signal.take_profit,
            portfolio_allocation_pct=allocation_pct,
            risk_per_trade_pct=risk_pct,
            execution_strategy="IMMEDIATE",
            entry_tag=f"swarm_{regime.regime.lower()}",
            sizing_justification="Fallback sizing (Executor unavailable)",
            execution_notes="Conservative defaults applied",
        )


# Singleton
_executor_agent = None


def get_executor_agent() -> ExecutorAgent:
    """Get singleton Executor Agent"""
    global _executor_agent
    if _executor_agent is None:
        _executor_agent = ExecutorAgent()
    return _executor_agent
