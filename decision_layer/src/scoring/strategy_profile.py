"""
Strategy Profile Schema
=======================
Defines the structure for strategy metadata used in the scoring engine.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class StrategyProfile(BaseModel):
    strategy_id: str

    # The ideal market vector this strategy was optimized for
    # [trend_strength, volatility_state, volume_intensity, mean_reversion_probability]
    ideal_regime_vector: List[float] = Field(..., min_items=4, max_items=4)

    # Performance Metrics (Rolling or Recent)
    win_rate_last_50_trades: float = Field(..., ge=0.0, le=1.0)
    sharpe_ratio_rolling: float
    max_drawdown_allowed: float = 0.20  # 20% DD limit
    current_drawdown: float = 0.0

    # Operational
    last_trade_time_hours_ago: float = 0.0
    correlation_group: Optional[str] = None  # For diversification
