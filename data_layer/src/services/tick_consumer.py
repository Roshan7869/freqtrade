"""
Data Layer - Tick Handler
=========================
Connects to Binance WebSocket and publishes ticks to Kafka (Async + Pydantic).
"""

import asyncio
import json
import logging
import os
import sys

import websockets

# sys.path handled by main.py or environment
from shared.messaging.async_client import AsyncEventProducer
from shared.schemas import MarketTick

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TickHandler")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")
from shared.trading_config import SYMBOLS


class TickHandler:
    def __init__(self):
        self.producer = AsyncEventProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP, client_id="tick-handler"
        )
        self.symbols = [s.lower().strip() for s in SYMBOLS]

    async def connect(self):
        await self.producer.start()  # Start Producer

        streams = "/".join([f"{s}@trade" for s in self.symbols])
        url = f"wss://stream.binance.com:9443/ws/{streams}"

        logger.info(f"Connecting to: {url}")

        while True:
            try:
                async with websockets.connect(url) as ws:
                    logger.info("Connected to Binance WebSocket")
                    async for msg in ws:
                        await self._process(msg)
            except Exception as e:
                logger.error(f"Connection error: {e}, reconnecting...")
                await asyncio.sleep(5)
            finally:
                # In endless loop we typically don't stop, but good practice
                pass

    async def _process(self, raw: str):
        try:
            data = json.loads(raw)
            if data.get("e") == "trade":
                # Map to Pydantic Schema
                tick = MarketTick(
                    symbol=data["s"],
                    price=float(data["p"]),
                    quantity=float(data["q"]),
                    is_buyer_maker=data["m"],
                    server_time=data["E"],
                )

                # Send (Non-blocking)
                await self.producer.send("market.tick", tick, key=tick.symbol)
        except Exception as e:
            logger.error(f"Error processing tick: {e}")


async def main():
    handler = TickHandler()
    try:
        await handler.connect()
    except KeyboardInterrupt:
        await handler.producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
