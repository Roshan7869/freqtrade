"""
Execution Layer - Order Executor
================================
Executes orders on Binance and publishes fills to Kafka. (Async + Schema)
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

# sys.path handled by config.py
from shared.messaging.async_client import AsyncEventProducer, AsyncEventConsumer
from shared.schemas import TradeOrder, TradeFill
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OrderExecutor")


class OrderExecutor:
    def __init__(self):
        self.producer = AsyncEventProducer(
            bootstrap_servers=Config.KAFKA_BOOTSTRAP, client_id="order-executor"
        )

    async def start(self):
        await self.producer.start()

    async def on_order(self, order: TradeOrder):
        """Execute order on exchange."""
        logger.info(
            f"Executing Order: {order.action} {order.symbol} Qty:{order.quantity}"
        )

        # Simulate Async API Call (await binance.create_order...)
        await asyncio.sleep(0.1)

        fill = TradeFill(
            order_id="12345",
            symbol=order.symbol,
            action=order.action,
            price=100.5,  # Mock price
            quantity=order.quantity if order.quantity else 1.0,
            status="FILLED",
        )

        await self.producer.send("trade.fill", fill, key=order.symbol)
        logger.info(f"Fill Published: {fill.order_id}")


async def main():
    executor = OrderExecutor()
    await executor.start()

    # Typed Consumer
    consumer = AsyncEventConsumer(
        ["trade.order"],
        "execution-group",
        Config.KAFKA_BOOTSTRAP,
        event_type=TradeOrder,
    )

    await consumer.start()

    try:
        await consumer.consume(executor.on_order)
    except KeyboardInterrupt:
        await consumer.stop()
        await executor.producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
