"""
Data Layer Entry Point
======================
Orchestrates Tick Consumer and Candle Aggregator.
"""

import asyncio
import argparse
import sys
import os
import logging

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.tick_consumer import main as run_ticks
from services.candle_aggregator import main as run_candles
from services.history_loader import main as run_history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DataLayer")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Layer Service")
    parser.add_argument(
        "service", choices=["ticks", "candles", "history", "all"], help="Service to run"
    )

    args = parser.parse_args()

    if args.service == "ticks":
        asyncio.run(run_ticks())
    elif args.service == "candles":
        # candle_aggregator currently uses sync main(), might need wrapper if async
        # Looking at file, it uses EventConsumer which is blocking consume.
        run_candles()
    elif args.service == "history":
        run_history()
    elif args.service == "all":
        # In a real microservice, we wouldn't run 'all' in one process usually,
        # but for simplicity we could use asyncio.gather if they were compatible.
        # Since candle aggregator is blocking, we can't easily run both without threads.
        logger.error(
            "Running 'all' services in one process is not supported yet. Run separate containers."
        )
        sys.exit(1)
