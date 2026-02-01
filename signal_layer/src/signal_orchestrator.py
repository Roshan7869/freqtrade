"""
Signal Layer Entry Point
========================
Orchestrates Strategy Executor and Whale Signal Provider.
"""

import asyncio
import argparse
import sys
import os
import logging

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.strategy_executor import main as run_strategies
# whale_provider is a library, not a service with main loop currently,
# but if we wanted to run it as a service we would need a main loop.
# For now, let's assume strategy executor uses whale provider library?
# Or we might want to run a whale tracker service?
# The WORKFLOW_GUIDE says "Signal Layer: Runs Strategies & Whale Tracker".

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SignalLayer")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Signal Layer Service")
    parser.add_argument(
        "service",
        choices=["strategies", "all"],
        default="strategies",
        help="Service to run",
    )

    args = parser.parse_args()

    if args.service == "strategies" or args.service == "all":
        asyncio.run(run_strategies())
