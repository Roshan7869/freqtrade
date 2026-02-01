"""
Swarm Orchestrator - 4-Agent Decision Pipeline
===============================================
Coordinates the sequential flow: Researcher -> Analyst -> Executor -> Risk Guardian
"""

import logging
import asyncio
from typing import Optional, Dict, List
from datetime import datetime

from shared.schemas.a2a import (
    RegimeAssessment,
    SignalProposal,
    DraftOrder,
    RiskVerification,
    SwarmDecision,
    SignalDirection,
    RiskVerificationStatus,
)
from analysis_layer.src.agents.researcher_agent import get_researcher_agent
from analysis_layer.src.agents.analyst_agent import get_analyst_agent
from analysis_layer.src.agents.executor_agent import get_executor_agent
from analysis_layer.src.agents.risk_guardian import get_risk_guardian
from analysis_layer.src.market_quant import MarketQuantAnalyzer

logger = logging.getLogger(__name__)


class SwarmOrchestrator:
    """
    Orchestrates the 4-agent swarm decision pipeline.

    Flow:
    1. MarketQuant calculates market state vector
    2. Researcher analyzes regime (DeepSeek R1)
    3. Analyst validates signal (Qwen Coder)
    4. Executor creates draft order (Llama 3.1)
    5. Risk Guardian final check (Gemini 2.0)
    """

    def __init__(self):
        self.market_quant = MarketQuantAnalyzer()
        self.researcher = get_researcher_agent()
        self.analyst = get_analyst_agent()
        self.executor = get_executor_agent()
        self.risk_guardian = get_risk_guardian()

        logger.info("🌊 Swarm Orchestrator initialized")
        logger.info(f"   Researcher: {'✅' if self.researcher.is_available else '❌'}")
        logger.info(f"   Analyst: {'✅' if self.analyst.is_available else '❌'}")
        logger.info(f"   Executor: {'✅' if self.executor.is_available else '❌'}")
        logger.info(
            f"   Risk Guardian: {'✅' if self.risk_guardian.is_available else '❌'}"
        )

    async def analyze_and_decide(
        self,
        pair: str,
        ohlcv_dataframe,
        timeframe: str = "1h",
        portfolio_balance: float = 10000.0,
        existing_exposure_pct: float = 0.0,
        risk_limits: Optional[Dict] = None,
        portfolio_state: Optional[Dict] = None,
    ) -> SwarmDecision:
        """
        Main method: Run the full 4-agent pipeline.

        Args:
            pair: Trading pair e.g. 'SOL/USDT:USDT'
            ohlcv_dataframe: Pandas DataFrame with OHLC data + indicators
            timeframe: Timeframe being analyzed
            portfolio_balance: Total portfolio USD value
            existing_exposure_pct: Current exposure %
            risk_limits: Risk rules dict
            portfolio_state: Portfolio state dict

        Returns:
            SwarmDecision with complete pipeline results
        """
        start_time = datetime.now()
        logger.info(f"\n{'=' * 70}")
        logger.info(f"🌊 SWARM DECISION PIPELINE: {pair} [{timeframe}]")
        logger.info(f"{'=' * 70}\n")

        # Initialize result vars
        regime_assessment = None
        signal_proposal = None
        draft_order = None
        risk_verification = None
        should_execute = False
        final_direction = SignalDirection.HOLD
        final_order = None

        try:
            # ================================================================
            # STAGE 0: Market Quantification
            # ================================================================
            logger.info("📊 STAGE 0: Market Quantification")
            market_vector = self.market_quant.analyze_market_state(ohlcv_dataframe)
            logger.info(
                f"   Trend: {market_vector['trend_strength']:.2f} | "
                f"Vol: {market_vector['volatility_state']:.2f} | "
                f"Volume: {market_vector['volume_intensity']:.2f}"
            )

            # Extract current data
            current_candle = ohlcv_dataframe.iloc[-1]
            current_price = float(current_candle["close"])
            recent_candles = (
                ohlcv_dataframe.tail(10).to_dict("records")
                if len(ohlcv_dataframe) >= 10
                else []
            )

            # ================================================================
            # STAGE 1: Researcher (DeepSeek R1)
            # ================================================================
            logger.info("\n🔬 STAGE 1: Researcher Agent (DeepSeek R1)")
            regime_assessment = await self.researcher.analyze_regime(
                pair=pair,
                market_vector=market_vector,
                recent_candles=recent_candles,
                current_price=current_price,
            )

            if not regime_assessment:
                logger.error("❌ Researcher failed - aborting pipeline")
                return self._create_decision(
                    pair,
                    timeframe,
                    regime_assessment,
                    signal_proposal,
                    draft_order,
                    risk_verification,
                    False,
                    SignalDirection.HOLD,
                    None,
                    start_time,
                    ["researcher"],
                )

            logger.info(
                f"   Regime: {regime_assessment.regime} "
                f"(confidence: {regime_assessment.confidence:.2f}, "
                f"risk: {regime_assessment.risk_level}/10)"
            )

            # ================================================================
            # STAGE 2: Analyst (Qwen Coder)
            # ================================================================
            logger.info("\n📊 STAGE 2: Analyst Agent (Qwen Coder)")

            # Extract indicators from dataframe
            indicators = {}
            indicator_cols = [
                "rsi",
                "adx",
                "macd",
                "macdsignal",
                "atr",
                "ema_fast",
                "ema_slow",
                "bb_lower",
                "bb_upper",
                "bb_mid",
            ]
            for col in indicator_cols:
                if col in current_candle:
                    indicators[col] = float(current_candle[col])

            signal_proposal = await self.analyst.verify_and_propose_signal(
                pair=pair,
                regime_assessment=regime_assessment,
                indicators=indicators,
                current_price=current_price,
                timeframe=timeframe,
            )

            if not signal_proposal:
                logger.error("❌ Analyst failed - aborting pipeline")
                return self._create_decision(
                    pair,
                    timeframe,
                    regime_assessment,
                    signal_proposal,
                    draft_order,
                    risk_verification,
                    False,
                    SignalDirection.HOLD,
                    None,
                    start_time,
                    ["researcher", "analyst"],
                )

            logger.info(
                f"   Signal: {signal_proposal.direction} @ ${signal_proposal.entry_price} "
                f"(score: {signal_proposal.technical_score:.2f})"
            )

            # If signal is HOLD, stop here
            if signal_proposal.direction == SignalDirection.HOLD:
                logger.info("   → Signal is HOLD - pipeline complete")
                return self._create_decision(
                    pair,
                    timeframe,
                    regime_assessment,
                    signal_proposal,
                    None,
                    None,
                    False,
                    SignalDirection.HOLD,
                    None,
                    start_time,
                    ["researcher", "analyst"],
                )

            # ================================================================
            # STAGE 3: Executor (Llama 3.1)
            # ================================================================
            logger.info("\n⚡ STAGE 3: Executor Agent (Llama 3.1)")

            draft_order = await self.executor.create_draft_order(
                signal=signal_proposal,
                regime=regime_assessment,
                portfolio_balance=portfolio_balance,
                existing_exposure_pct=existing_exposure_pct,
            )

            if not draft_order:
                logger.error("❌ Executor failed - aborting pipeline")
                return self._create_decision(
                    pair,
                    timeframe,
                    regime_assessment,
                    signal_proposal,
                    draft_order,
                    risk_verification,
                    False,
                    SignalDirection.HOLD,
                    None,
                    start_time,
                    ["researcher", "analyst", "executor"],
                )

            logger.info(
                f"   Order: {draft_order.direction} {draft_order.quantity:.2f} "
                f"@ {draft_order.leverage}x (${draft_order.quantity_usd:.2f})"
            )

            # ================================================================
            # STAGE 4: Risk Guardian (Gemini 2.0)
            # ================================================================
            logger.info("\n🛡️ STAGE 4: Risk Guardian (Gemini 2.0)")

            risk_verification = await self.risk_guardian.verify_order(
                draft_order=draft_order,
                risk_limits=risk_limits,
                portfolio_state=portfolio_state,
            )

            if not risk_verification:
                logger.error("❌ Risk Guardian failed - aborting pipeline")
                return self._create_decision(
                    pair,
                    timeframe,
                    regime_assessment,
                    signal_proposal,
                    draft_order,
                    risk_verification,
                    False,
                    SignalDirection.HOLD,
                    None,
                    start_time,
                    ["researcher", "analyst", "executor", "risk_guardian"],
                )

            logger.info(f"   Verdict: {risk_verification.status}")

            # ================================================================
            # FINAL DECISION
            # ================================================================
            logger.info("\n✅ FINAL DECISION:")

            if risk_verification.status == RiskVerificationStatus.APPROVED:
                should_execute = True
                final_direction = draft_order.direction
                final_order = {
                    "pair": draft_order.pair,
                    "direction": draft_order.direction,
                    "order_type": draft_order.order_type,
                    "price": draft_order.price,
                    "quantity": draft_order.quantity,
                    "leverage": draft_order.leverage,
                    "stop_loss": draft_order.stop_loss,
                    "take_profit": draft_order.take_profit,
                    "entry_tag": draft_order.entry_tag,
                }
                logger.info(f"   ✅ APPROVED - Execute {final_direction}")

            elif risk_verification.status == RiskVerificationStatus.MODIFIED:
                should_execute = True
                final_direction = draft_order.direction
                final_order = {
                    "pair": draft_order.pair,
                    "direction": draft_order.direction,
                    "order_type": draft_order.order_type,
                    "price": draft_order.price,
                    "quantity": risk_verification.modified_quantity
                    or draft_order.quantity,
                    "leverage": risk_verification.modified_leverage
                    or draft_order.leverage,
                    "stop_loss": draft_order.stop_loss,
                    "take_profit": draft_order.take_profit,
                    "entry_tag": draft_order.entry_tag + "_modified",
                }
                logger.info(f"   ⚠️ MODIFIED - Execute with reduced size")

            else:  # REJECTED
                should_execute = False
                final_direction = SignalDirection.HOLD
                final_order = None
                logger.info(f"   ❌ REJECTED - {risk_verification.rejection_reason}")

            # Create final decision
            duration = (datetime.now() - start_time).total_seconds() * 1000
            decision = self._create_decision(
                pair,
                timeframe,
                regime_assessment,
                signal_proposal,
                draft_order,
                risk_verification,
                should_execute,
                final_direction,
                final_order,
                start_time,
                ["researcher", "analyst", "executor", "risk_guardian"],
            )

            logger.info(f"\n🏁 Pipeline completed in {duration:.0f}ms")
            logger.info(f"{'=' * 70}\n")

            return decision

        except Exception as e:
            logger.error(f"❌ Swarm pipeline error: {e}", exc_info=True)
            return self._create_decision(
                pair,
                timeframe,
                regime_assessment,
                signal_proposal,
                draft_order,
                risk_verification,
                False,
                SignalDirection.HOLD,
                None,
                start_time,
                ["error"],
            )

    def _create_decision(
        self,
        pair: str,
        timeframe: str,
        regime: Optional[RegimeAssessment],
        signal: Optional[SignalProposal],
        order: Optional[DraftOrder],
        verification: Optional[RiskVerification],
        should_execute: bool,
        final_direction: SignalDirection,
        final_order: Optional[Dict],
        start_time: datetime,
        agents_involved: List[str],
    ) -> SwarmDecision:
        """Create a SwarmDecision object"""

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Create mock objects for None values
        if regime is None:
            from shared.schemas.a2a import MarketRegimeType

            regime = RegimeAssessment(
                regime=MarketRegimeType.UNKNOWN,
                confidence=0.0,
                reasoning="Pipeline failed",
                trend_strength=0.0,
                volatility_state=0.0,
                volume_intensity=0.0,
                mean_reversion_probability=0.0,
                suggested_strategies=[],
                risk_level=10,
            )

        if signal is None:
            signal = SignalProposal(
                direction=SignalDirection.HOLD,
                pair=pair,
                technical_score=0.0,
                strategy_name="None",
                timeframe=timeframe,
                verification_notes="Pipeline failed",
            )

        if order is None:
            order = DraftOrder(
                direction=SignalDirection.HOLD,
                pair=pair,
                order_type="MARKET",
                quantity=0.0,
                quantity_usd=0.0,
                leverage=1.0,
                stop_loss=0.0,
                portfolio_allocation_pct=0.0,
                risk_per_trade_pct=0.0,
                execution_strategy="NONE",
                entry_tag="none",
                sizing_justification="Pipeline failed",
                execution_notes="Pipeline failed",
            )

        if verification is None:
            verification = RiskVerification(
                status=RiskVerificationStatus.REJECTED,
                current_total_exposure_pct=0.0,
                post_trade_exposure_pct=0.0,
                current_drawdown_pct=0.0,
                max_risk_exceeded=True,
                safety_notes="Pipeline failed",
            )

        return SwarmDecision(
            pair=pair,
            timeframe=timeframe,
            regime_assessment=regime,
            signal_proposal=signal,
            draft_order=order,
            risk_verification=verification,
            should_execute=should_execute,
            final_direction=final_direction,
            final_order=final_order,
            decision_pipeline_duration_ms=duration_ms,
            agents_involved=agents_involved,
        )


# Singleton
_swarm_orchestrator = None


def get_swarm_orchestrator() -> SwarmOrchestrator:
    """Get singleton Swarm Orchestrator"""
    global _swarm_orchestrator
    if _swarm_orchestrator is None:
        _swarm_orchestrator = SwarmOrchestrator()
    return _swarm_orchestrator
