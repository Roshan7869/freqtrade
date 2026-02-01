from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# Base Event
class BaseEvent(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_config = ConfigDict(populate_by_name=True)


# 1. Market Data Events
class MarketTick(BaseEvent):
    symbol: str
    price: float
    quantity: float
    is_buyer_maker: bool
    server_time: int  # Exchange timestamp


class MarketCandle(BaseEvent):
    symbol: str
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


# 2. Signal Events
class WhaleSignal(BaseEvent):
    blockchain: str
    symbol: str
    amount_usd: float
    signal_type: Literal["BUY", "SELL"]
    confidence: float
    source: Literal["whale_tracker"] = "whale_tracker"


class StrategySignal(BaseEvent):
    strategy_name: str
    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    price: float
    confidence: float = 0.5
    source: Literal["strategy"] = "strategy"


# 3. Trading Events
class TradeOrder(BaseEvent):
    symbol: str
    action: Literal["BUY", "SELL"]
    quantity: Optional[float] = None  # None = use risk manager sizing
    leverage: int = 1
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    price: Optional[float] = None


class TradeFill(BaseEvent):
    order_id: str
    symbol: str
    action: Literal["BUY", "SELL"]
    price: float
    quantity: float
    commission: float = 0.0
    status: Literal["FILLED", "PARTIALLY_FILLED"]
