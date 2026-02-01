"""
Data Layer - Candle Aggregator
==============================
Aggregates ticks into OHLCV candles and publishes to Kafka.
"""

import logging
import os
import sys
from datetime import datetime
from collections import defaultdict

# sys.path handled by main.py or environment
from shared.messaging import EventProducer, EventConsumer
from shared.trading_config import TIMEFRAME

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CandleAggregator")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")


def timeframe_to_ms(tf: str) -> int:
    unit = tf[-1]
    value = int(tf[:-1])
    if unit == "s":
        return value * 1000
    if unit == "m":
        return value * 60 * 1000
    if unit == "h":
        return value * 60 * 60 * 1000
    if unit == "d":
        return value * 24 * 60 * 60 * 1000
    return 3600000


class CandleAggregator:
    def __init__(self, timeframe_ms: int = None):
        self.producer = EventProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP, client_id="candle-aggregator"
        )
        self.timeframe_ms = timeframe_ms or timeframe_to_ms(TIMEFRAME)
        self.candles = defaultdict(dict)

    def on_tick(self, tick: dict):
        symbol = tick["symbol"]
        price = tick["price"]
        qty = tick["quantity"]
        ts = tick["timestamp"]

        candle_time = (ts // self.timeframe_ms) * self.timeframe_ms

        if (
            symbol not in self.candles
            or self.candles[symbol].get("time") != candle_time
        ):
            # New candle
            if symbol in self.candles and self.candles[symbol]:
                # Publish completed candle
                self.producer.send("market.candle", self.candles[symbol], key=symbol)
                logger.info(f"Published candle: {symbol}")

            self.candles[symbol] = {
                "symbol": symbol,
                "time": candle_time,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": qty,
            }
        else:
            c = self.candles[symbol]
            c["high"] = max(c["high"], price)
            c["low"] = min(c["low"], price)
            c["close"] = price
            c["volume"] += qty


def main():
    aggregator = CandleAggregator()
    consumer = EventConsumer(["market.tick"], "candle-group", KAFKA_BOOTSTRAP)

    logger.info("Starting Candle Aggregator...")
    consumer.consume(aggregator.on_tick)


if __name__ == "__main__":
    main()
