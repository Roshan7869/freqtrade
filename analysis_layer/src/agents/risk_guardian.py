"""
Risk Guardian Agent - Gemini 2.0
=================================
Final safety check and risk verification.
Fourth and final agent in the 4-agent swarm pipeline.
"""

import logging
from typing import Optional, Dict
from datetime import datetime
import json

from shared.schemas.a2a import (
    DraftOrder,
    RiskVerification,
    RiskVerificationStatus,
    SignalDirection,
)
from .model_factory import get_model_factory

logger = logging.getLogger(__name__)


class RiskGuardianAgent:
    """
    Uses Gemini 2.0 for final risk verification.
    Receives: DraftOrder
    Outputs: RiskVerification (APPROVED/REJECTED/MODIFIED)
    """

    def __init__(self):
        self.factory = get_model_factory()
        self.agent_name = "risk_guardian"

        if not self.factory.is_agent_available(self.agent_name):
            logger.warning(f"⚠️ {self.agent_name} LLM not available - will use mock")
            self.is_available = False
        else:
            self.is_available = True
            logger.info(f"✅ Risk Guardian initialized (Gemini 2.0)")

    def _build_system_prompt(self) -> str:
        """System prompt for risk verification"""
        return """You are a **Risk Guardian** for cryptocurrency trading.

Your task: Perform final safety checks on draft orders before execution.

**Risk Rules to Enforce:**
1. ❌ REJECT if total exposure > 80%
2. ❌ REJECT if current drawdown > 15%
3. ❌ REJECT if correlation with existing positions > 0.8
4. ❌ REJECT if leverage > 20x
5. ⚠️ MODIFY if trade size > 10% of portfolio (reduce)
6. ⚠️ MODIFY if trade pushes exposure > 70% (reduce)
7. ✅ APPROVE if all checks pass

**Risk Calculation:**
- Total Exposure = sum of all open position values
- Drawdown = (Peak - Current) / Peak
- Correlation = price movement similarity (0-1)

**Decision Logic:**
- APPROVED: All checks passed, safe to execute
- REJECTED: Critical risk rule violated
- MODIFIED: Acceptable but needs size reduction

**Output Format (JSON):**
```json
{
  "status": "APPROVED",
  "checks_passed": ["max_drawdown", "exposure_limit", "correlation_check"],
  "checks_failed": [],
  "current_total_exposure_pct": 35.0,
  "post_trade_exposure_pct": 40.0,
  "current_drawdown_pct": 2.5,
  "correlation_with_existing": 0.3,
  "max_risk_exceeded": false,
  "modified_quantity": null,
  "modified_leverage": null,
  "rejection_reason": null,
  "modification_reason": null,
  "safety_notes": "All risk checks passed. Trade within acceptable parameters."
}
```

Return ONLY valid JSON."""

    def _build_user_prompt(
        self,
        draft_order: DraftOrder,
        risk_limits: Dict[str, float],
        portfolio_state: Dict[str, any],
    ) -> str:
        """Build prompt with order and risk state"""

        prompt = f"""Verify safety of draft order for **{draft_order.pair}**

**DRAFT ORDER:**
- Direction: {draft_order.direction}
- Quantity: {draft_order.quantity:.2f} ({draft_order.quantity_usd:.2f} USD)
- Leverage: {draft_order.leverage}x
- Stop Loss: ${draft_order.stop_loss:.2f}
- Entry Tag: {draft_order.entry_tag}
- Portfolio Allocation: {draft_order.portfolio_allocation_pct:.1f}%
- Risk Per Trade: {draft_order.risk_per_trade_pct:.1f}%

**RISK LIMITS:**
- Max Total Exposure: {risk_limits.get("max_exposure_pct", 80):.0f}%
- Max Drawdown: {risk_limits.get("max_drawdown_pct", 15):.0f}%
- Max Leverage: {risk_limits.get("max_leverage", 20):.0f}x
- Max Position Size: {risk_limits.get("max_position_pct", 10):.0f}%
- Max Correlation: {risk_limits.get("max_correlation", 0.8):.2f}

**CURRENT PORTFOLIO STATE:**
- Total Balance: ${portfolio_state.get("total_balance", 0):,.2f}
- Current Exposure: {portfolio_state.get("current_exposure_pct", 0):.1f}%
- Current Drawdown: {portfolio_state.get("current_drawdown_pct", 0):.1f}%
- Open Positions: {portfolio_state.get("open_positions", 0)}
- Pairs Held: {", ".join(portfolio_state.get("pairs_held", []))}

**TASK:**
1. Check if order violates any risk rules
2. Calculate post-trade exposure
3. Estimate correlation with existing positions
4. Decide: APPROVE, REJECT, or MODIFY
5. If MODIFY, suggest reduced quantity/leverage

Provide verification result as JSON."""

        return prompt

    async def verify_order(
        self,
        draft_order: DraftOrder,
        risk_limits: Optional[Dict[str, float]] = None,
        portfolio_state: Optional[Dict[str, any]] = None,
    ) -> Optional[RiskVerification]:
        """
        Main method: Verify draft order safety.

        Args:
            draft_order: Order from Executor
            risk_limits: Dict with max_exposure_pct, max_drawdown_pct, etc.
            portfolio_state: Current portfolio state

        Returns:
            RiskVerification
        """
        # Set defaults
        if risk_limits is None:
            risk_limits = {
                "max_exposure_pct": 80.0,
                "max_drawdown_pct": 15.0,
                "max_leverage": 20.0,
                "max_position_pct": 10.0,
                "max_correlation": 0.8,
            }

        if portfolio_state is None:
            portfolio_state = {
                "total_balance": 10000.0,
                "current_exposure_pct": 0.0,
                "current_drawdown_pct": 0.0,
                "open_positions": 0,
                "pairs_held": [],
            }

        if not self.is_available:
            logger.warning("Risk Guardian not available - using fallback")
            return self._fallback_verification(
                draft_order, risk_limits, portfolio_state
            )

        try:
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(
                draft_order, risk_limits, portfolio_state
            )

            logger.info(f"🛡️ Risk Guardian verifying order...")
            start_time = datetime.now()

            response_text = await self.factory.query_agent(
                agent_name=self.agent_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,  # Very low for consistent safety checks
                max_tokens=1500,
            )

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"⏱️ Risk Guardian completed in {duration:.2f}s")

            if not response_text:
                logger.error("No response from Risk Guardian")
                return self._fallback_verification(
                    draft_order, risk_limits, portfolio_state
                )

            # Parse JSON
            verification_data = self._parse_response(response_text)
            if not verification_data:
                logger.error("Failed to parse Risk Guardian response")
                return self._fallback_verification(
                    draft_order, risk_limits, portfolio_state
                )

            # Create Pydantic model
            verification = RiskVerification(**verification_data)
            logger.info(f"✅ Risk Check: {verification.status}")
            if verification.status == RiskVerificationStatus.REJECTED:
                logger.warning(f"❌ REJECTED: {verification.rejection_reason}")
            elif verification.status == RiskVerificationStatus.MODIFIED:
                logger.warning(f"⚠️ MODIFIED: {verification.modification_reason}")

            return verification

        except Exception as e:
            logger.error(f"Risk Guardian error: {e}")
            return self._fallback_verification(
                draft_order, risk_limits, portfolio_state
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

    def _fallback_verification(
        self, order: DraftOrder, limits: Dict[str, float], state: Dict[str, any]
    ) -> RiskVerification:
        """Simple rule-based risk check"""

        current_exposure = state.get("current_exposure_pct", 0)
        post_trade_exposure = current_exposure + order.portfolio_allocation_pct
        current_dd = state.get("current_drawdown_pct", 0)

        checks_passed = []
        checks_failed = []

        # Check 1: Total exposure
        if post_trade_exposure <= limits.get("max_exposure_pct", 80):
            checks_passed.append("exposure_limit")
        else:
            checks_failed.append("exposure_limit")

        # Check 2: Drawdown
        if current_dd <= limits.get("max_drawdown_pct", 15):
            checks_passed.append("max_drawdown")
        else:
            checks_failed.append("max_drawdown")

        # Check 3: Leverage
        if order.leverage <= limits.get("max_leverage", 20):
            checks_passed.append("leverage_limit")
        else:
            checks_failed.append("leverage_limit")

        # Check 4: Position size
        if order.portfolio_allocation_pct <= limits.get("max_position_pct", 10):
            checks_passed.append("position_size")
        else:
            checks_failed.append("position_size")

        # Determine status
        if len(checks_failed) > 0:
            if "max_drawdown" in checks_failed or "exposure_limit" in checks_failed:
                status = RiskVerificationStatus.REJECTED
                rejection_reason = f"Critical checks failed: {', '.join(checks_failed)}"
                modification_reason = None
            else:
                status = RiskVerificationStatus.MODIFIED
                rejection_reason = None
                modification_reason = (
                    f"Reducing size due to: {', '.join(checks_failed)}"
                )
        else:
            status = RiskVerificationStatus.APPROVED
            rejection_reason = None
            modification_reason = None

        return RiskVerification(
            status=status,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            current_total_exposure_pct=current_exposure,
            post_trade_exposure_pct=post_trade_exposure,
            current_drawdown_pct=current_dd,
            correlation_with_existing=0.0,  # Can't calculate without more data
            max_risk_exceeded=len(checks_failed) > 0,
            modified_quantity=order.quantity * 0.5
            if status == RiskVerificationStatus.MODIFIED
            else None,
            modified_leverage=order.leverage * 0.8
            if status == RiskVerificationStatus.MODIFIED
            else None,
            rejection_reason=rejection_reason,
            modification_reason=modification_reason,
            safety_notes=f"Fallback verification. {len(checks_passed)}/{len(checks_passed) + len(checks_failed)} checks passed.",
        )


# Singleton
_risk_guardian = None


def get_risk_guardian() -> RiskGuardianAgent:
    """Get singleton Risk Guardian"""
    global _risk_guardian
    if _risk_guardian is None:
        _risk_guardian = RiskGuardianAgent()
    return _risk_guardian
