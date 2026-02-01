"""
Execution Layer Configuration
============================
Centralized config.
"""

import os
import sys

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class Config:
    KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")
    # Fallback to EXCHANGE_KEY if specific BINANCE key is not set
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY") or os.getenv("EXCHANGE_KEY", "")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET") or os.getenv(
        "EXCHANGE_SECRET", ""
    )
    EXCHANGE = os.getenv("EXCHANGE", "binance")
    TRADING_MODE = os.getenv("TRADING_MODE", "futures")
