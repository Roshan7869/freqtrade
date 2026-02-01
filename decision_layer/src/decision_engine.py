"""
Decision Layer - Decision Engine
================================
Synthesizes signals from strategies, whale tracker, and LLM analysis
to produce final trade decisions. (Async + Schema)
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from collections import defaultdict

# sys.path handled by Docker or environment in production

if __name__ == "__main__":
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

from shared.messaging.async_client import AsyncEventProducer, AsyncEventConsumer
from shared.schemas import StrategySignal, WhaleSignal, TradeOrder
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DecisionEngine")


class DecisionEngine:
    def __init__(self):
        self.producer = AsyncEventProducer(
            bootstrap_servers=Config.KAFKA_BOOTSTRAP, client_id="decision-engine"
        )
        self.signals = defaultdict(list)
        self.regime = {}

    async def start(self):
        await self.producer.start()

    async def on_signal(self, signal):
        """Process incoming signals (Pydantic models)."""
        symbol = signal.symbol

        # Buffer signal
        self.signals[symbol].append(signal)
        logger.info(f"Received signal: {signal.source} {signal.action} for {symbol}")

        # Check buffer (Simple Count Logic for Demo)
        if len(self.signals[symbol]) >= 2:
            decision = await self._make_decision(symbol)
            if decision:
                await self.producer.send("trade.order", decision, key=symbol)
                logger.info(f"Decision Produced: {decision.action} {symbol}")
            self.signals[symbol] = []

    async def _make_decision(self, symbol: str):
        signals = self.signals[symbol]
        buy_votes = sum(
            1
            for s in signals
            if s.action == "BUY"
            or (hasattr(s, "signal_type") and s.signal_type == "BUY")
        )
        sell_votes = sum(
            1
            for s in signals
            if s.action == "SELL"
            or (hasattr(s, "signal_type") and s.signal_type == "SELL")
        )

        action = None
        if buy_votes > sell_votes:
            action = "BUY"
        elif sell_votes > buy_votes:
            action = "SELL"

        if action:
            return TradeOrder(symbol=symbol, action=action)
        return None


async def main():
    engine = DecisionEngine()
    await engine.start()

    # We consume raw dicts here because we listen to multiple topics with different schemas
    # Ideally AsyncEventConsumer should support Union[StrategySignal, WhaleSignal]
    # For simplicity, we handle raw and dispatch
    consumer = AsyncEventConsumer(
        ["signal.strategy", "signal.whale"], "decision-group", Config.KAFKA_BOOTSTRAP
    )

    await consumer.start()

    try:
        async for msg in consumer.consumer:
            # Manual dispatch based on topic
            try:
                import json

                data = json.loads(msg.value)

                if msg.topic == "signal.strategy":
                    signal = StrategySignal(**data)
                    await engine.on_signal(signal)
                elif msg.topic == "signal.whale":
                    # Map Whale signal structure to comparable format
                    signal = WhaleSignal(**data)
                    # Mapping logic if needed, signal_type handles BUY/SELL
                    await engine.on_signal(signal)

            except Exception as e:
                logger.error(f"Error processing {msg.topic}: {e}")

    except KeyboardInterrupt:
        await consumer.stop()
        await engine.producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
