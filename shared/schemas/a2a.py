"""
A2A (Agent-to-Agent) Communication Schemas
===========================================
Pydantic models for structured inter-agent communication in the decision pipeline.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime
from enum import Enum


class MarketRegimeType(str, Enum):
    """Market regime classifications"""

    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    PANIC = "PANIC"
    UNKNOWN = "UNKNOWN"


class SignalDirection(str, Enum):
    """Trade direction"""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


# ============================================================================
# STAGE 1: RESEARCHER AGENT OUTPUT
# ============================================================================


class RegimeAssessment(BaseModel):
    """Output from Researcher Agent (DeepSeek R1)"""

    regime: MarketRegimeType = Field(..., description="Identified market regime")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level 0-1")
    reasoning: str = Field(
        ..., description="Chain-of-thought reasoning for regime classification"
    )

    # Market metrics that informed the decision
    trend_strength: float = Field(
        ..., ge=0.0, le=1.0, description="Normalized ADX/trend metric"
    )
    volatility_state: float = Field(
        ..., ge=0.0, le=1.0, description="Normalized volatility metric"
    )
    volume_intensity: float = Field(
        ..., ge=0.0, le=1.0, description="Normalized volume metric"
    )
    mean_reversion_probability: float = Field(
        ..., ge=0.0, le=1.0, description="Reversion likelihood"
    )

    # Recommendations for next stage
    suggested_strategies: List[str] = Field(
        default_factory=list, description="Strategy names to consider"
    )
    risk_level: int = Field(..., ge=1, le=10, description="Risk score 1-10")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "regime": "TRENDING_BULL",
                "confidence": 0.82,
                "reasoning": "Strong upward trend confirmed by ADX > 30, price above all MAs...",
                "trend_strength": 0.75,
                "volatility_state": 0.45,
                "volume_intensity": 0.68,
                "mean_reversion_probability": 0.15,
                "suggested_strategies": ["bull_wma", "momentum_breakout"],
                "risk_level": 6,
            }
        }


# ============================================================================
# STAGE 2: ANALYST AGENT OUTPUT
# ============================================================================


class SignalProposal(BaseModel):
    """Output from Analyst Agent (Qwen Coder)"""

    direction: SignalDirection
    pair: str = Field(..., description="Trading pair e.g. 'SOL/USDT:USDT'")
    entry_price: Optional[float] = Field(None, description="Suggested entry price")
    stop_loss: Optional[float] = Field(None, description="Calculated stop loss")
    take_profit: Optional[float] = Field(None, description="Calculated take profit")

    # Technical validation
    technical_score: float = Field(
        ..., ge=0.0, le=1.0, description="Technical alignment score"
    )
    indicators_used: List[str] = Field(
        default_factory=list, description="Indicators that triggered signal"
    )
    pattern_detected: Optional[str] = Field(None, description="Chart pattern if any")

    # Strategy-specific
    strategy_name: str = Field(..., description="Which strategy generated this signal")
    timeframe: str = Field(..., description="Timeframe analyzed e.g. '1h'")

    # Analyst reasoning
    verification_notes: str = Field(..., description="Why this signal is valid")
    warnings: List[str] = Field(
        default_factory=list, description="Any concerns or caveats"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
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
                "verification_notes": "MACD crossed above signal, RSI at 35, price above EMA12",
                "warnings": [],
            }
        }


# ============================================================================
# STAGE 3: EXECUTOR AGENT OUTPUT
# ============================================================================


class DraftOrder(BaseModel):
    """Output from Executor Agent (Llama 3.1)"""

    direction: SignalDirection
    pair: str

    # Order specification
    order_type: Literal["LIMIT", "MARKET"] = Field(..., description="Order type")
    price: Optional[float] = Field(None, description="Limit price if applicable")
    quantity: float = Field(..., gt=0, description="Amount to trade")
    quantity_usd: float = Field(..., gt=0, description="USD value of trade")

    # Risk management
    leverage: float = Field(..., ge=1.0, le=20.0, description="Leverage to use")
    stop_loss: float = Field(..., description="Final stop loss")
    take_profit: Optional[float] = Field(None, description="Final take profit")

    # Position sizing logic
    portfolio_allocation_pct: float = Field(
        ..., ge=0.0, le=100.0, description="% of portfolio"
    )
    risk_per_trade_pct: float = Field(
        ..., ge=0.0, le=5.0, description="Max risk % per trade"
    )

    # Execution details
    execution_strategy: str = Field(
        ..., description="How to execute (immediate, TWAP, etc.)"
    )
    entry_tag: str = Field(..., description="Freqtrade entry tag")

    # Executor reasoning
    sizing_justification: str = Field(..., description="Why this size/leverage?")
    execution_notes: str = Field(..., description="Special execution instructions")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
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
                "sizing_justification": "Bull regime confirmed, using 8x from orchestrator strategy",
                "execution_notes": "Place limit order, if not filled in 5min switch to market",
            }
        }


# ============================================================================
# STAGE 4: RISK GUARDIAN OUTPUT
# ============================================================================


class RiskVerificationStatus(str, Enum):
    """Risk check result"""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"


class RiskVerification(BaseModel):
    """Output from Risk Guardian Agent (Gemini 2.0)"""

    status: RiskVerificationStatus

    # Risk checks performed
    checks_passed: List[str] = Field(
        default_factory=list, description="Which risk rules passed"
    )
    checks_failed: List[str] = Field(
        default_factory=list, description="Which risk rules failed"
    )

    # Portfolio state
    current_total_exposure_pct: float = Field(
        ..., description="Current total exposure %"
    )
    post_trade_exposure_pct: float = Field(..., description="Exposure after this trade")
    current_drawdown_pct: float = Field(..., description="Current portfolio drawdown")

    # Risk metrics
    correlation_with_existing: Optional[float] = Field(
        None, description="Correlation with open positions"
    )
    max_risk_exceeded: bool = Field(..., description="Would exceed max risk?")

    # Modifications (if status = MODIFIED)
    modified_quantity: Optional[float] = Field(
        None, description="Reduced quantity if modified"
    )
    modified_leverage: Optional[float] = Field(
        None, description="Reduced leverage if modified"
    )

    # Risk guardian reasoning
    rejection_reason: Optional[str] = Field(
        None, description="Why rejected if applicable"
    )
    modification_reason: Optional[str] = Field(
        None, description="Why modified if applicable"
    )
    safety_notes: str = Field(..., description="Overall safety assessment")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "status": "APPROVED",
                "checks_passed": [
                    "max_drawdown",
                    "exposure_limit",
                    "correlation_check",
                ],
                "checks_failed": [],
                "current_total_exposure_pct": 35.0,
                "post_trade_exposure_pct": 40.0,
                "current_drawdown_pct": 2.5,
                "correlation_with_existing": 0.3,
                "max_risk_exceeded": False,
                "safety_notes": "All risk checks passed. Trade within acceptable parameters.",
            }
        }


# ============================================================================
# COMPLETE SWARM DECISION
# ============================================================================


class SwarmDecision(BaseModel):
    """Final aggregated decision from the 4-agent swarm"""

    # Original inputs
    pair: str
    timeframe: str

    # Agent outputs
    regime_assessment: RegimeAssessment
    signal_proposal: SignalProposal
    draft_order: DraftOrder
    risk_verification: RiskVerification

    # Final verdict
    should_execute: bool = Field(..., description="Final go/no-go decision")
    final_direction: SignalDirection
    final_order: Optional[Dict[str, Any]] = Field(
        None, description="Final order details if approved"
    )

    # Metadata
    decision_pipeline_duration_ms: float = Field(
        ..., description="Total time for 4-agent pipeline"
    )
    agents_involved: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "pair": "SOL/USDT:USDT",
                "timeframe": "1h",
                "should_execute": True,
                "final_direction": "BUY",
                "decision_pipeline_duration_ms": 1250.5,
                "agents_involved": [
                    "researcher",
                    "analyst",
                    "executor",
                    "risk_guardian",
                ],
            }
        }
