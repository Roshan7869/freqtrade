"""
Signal Layer - Strategy Executor
================================
Runs all strategies in parallel and publishes signals via Kafka (Async + Schema).
"""

import asyncio
import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor

# sys.path handled by main.py
from shared.messaging.async_client import AsyncEventProducer, AsyncEventConsumer
from shared.schemas import MarketCandle, StrategySignal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StrategyExecutor")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")


class StrategyExecutor:
    def __init__(self):
        self.producer = AsyncEventProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP, client_id="strategy-executor"
        )
        self.strategies = ["AroonMACD", "ALMA_MACD"]  # Placeholder

    async def start(self):
        await self.producer.start()

    async def on_candle(self, candle: MarketCandle):
        """Process incoming candle (Pydantic model)."""
        symbol = candle.symbol

        # In a real system, we'd offload CPU work to a ProcessPoolExecutor here
        # loop = asyncio.get_running_loop()
        # signals = await loop.run_in_executor(self.pool, self._run_strategies, candle)

        for strategy_name in self.strategies:
            signal = self._run_strategy(strategy_name, candle)
            if signal:
                await self.producer.send("signal.strategy", signal, key=symbol)
                logger.info(
                    f"Signal Produced: {signal.action} {symbol} by {strategy_name}"
                )

    def _run_strategy(self, name: str, candle: MarketCandle):
        # Placeholder logic
        # In reality, this would check indicators
        return None  # Return StrategySignal if buy/sell


async def main():
    executor = StrategyExecutor()
    await executor.start()

    consumer = AsyncEventConsumer(
        ["market.candle"], "strategy-group", KAFKA_BOOTSTRAP, event_type=MarketCandle
    )

    await consumer.start()
    logger.info("Strategy Executor Started (Async)")

    try:
        await consumer.consume(executor.on_candle)
    except KeyboardInterrupt:
        await consumer.stop()
        await executor.producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
