"""
Analysis Layer - Main Entry Point
================================
Orchestrates market analysis using LLM agents and produces regime events.
"""

import logging
import os
import sys
from datetime import datetime, timezone

# Add 'src' to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.messaging import EventProducer, EventConsumer
from domain.regime.analyst import get_llm_market_analyst, MarketRegime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AnalysisLayer")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")
CACHE_TTL = 3600  # 1 hour


class AnalysisService:
    def __init__(self):
        self.producer = EventProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP, client_id="analysis-layer"
        )
        self.analyst = get_llm_market_analyst()
        self.cache = {}
        logger.info("Analysis Service Initialized")

    def on_candle(self, event: dict):
        """
        Handle market.candle event.
        """
        try:
            symbol = event.get("symbol")
            if not symbol:
                return

            timestamp = event.get("time", 0)
            cache_key = f"{symbol}_{timestamp // CACHE_TTL}"

            if cache_key in self.cache:
                return

            market_data = {
                "close": [event.get("close")],
                "volume": [event.get("volume")],
                "high": [event.get("high")],
                "low": [event.get("low")],
            }

            regime: MarketRegime = self.analyst.get_market_regime(
                pair=symbol, market_data=market_data
            )

            payload = {
                "symbol": symbol,
                "regime": regime.regime.value,
                "confidence": regime.confidence,
                "risk_score": regime.risk_score,
                "reasoning": regime.reasoning,
                "timestamp": timestamp,
                "analysis_time": datetime.now(timezone.utc).isoformat(),
            }

            self.producer.send("analysis.regime", payload, key=symbol)
            self.cache[cache_key] = regime

            logger.info(
                f"Analyzed {symbol}: {regime.regime.value} (Risk: {regime.risk_score})"
            )

        except Exception as e:
            logger.error(f"Error processing candle: {e}")


def main():
    service = AnalysisService()
    consumer = EventConsumer(["market.candle"], "analysis-group", KAFKA_BOOTSTRAP)

    logger.info("Starting Analysis Layer consumer...")
    consumer.consume(service.on_candle)


if __name__ == "__main__":
    main()
