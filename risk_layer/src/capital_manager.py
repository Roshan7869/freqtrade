"""
Risk Layer - Capital Manager
============================
Manages position sizing using Kelly Criterion.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.messaging import EventProducer, EventConsumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CapitalManager")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")


class CapitalManager:
    def __init__(self):
        self.producer = EventProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP, client_id="capital-manager"
        )
        self.positions = {}
        self.pnl_history = []

    def on_fill(self, fill: dict):
        """Track fills and update position state."""
        symbol = fill["symbol"]

        if symbol not in self.positions:
            self.positions[symbol] = {"quantity": 0, "avg_price": 0}

        # Update position tracking
        logger.info(f"Position update: {symbol} {fill}")

    def calculate_kelly(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Calculate Kelly fraction."""
        if avg_loss == 0:
            return 0.02
        kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
        return min(0.25, kelly * 0.5)  # Half-Kelly, capped at 25%


def main():
    manager = CapitalManager()
    consumer = EventConsumer(["trade.fill"], "risk-group", KAFKA_BOOTSTRAP)

    logger.info("Starting Capital Manager...")
    consumer.consume(manager.on_fill)


if __name__ == "__main__":
    main()
