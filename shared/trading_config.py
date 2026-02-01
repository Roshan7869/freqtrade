"""
TRADING CONFIGURATION - Single Source of Truth
===============================================
All strategies, data downloads, backtests, and live trading
read from this centralized configuration.

Modify values here to change behavior system-wide.
"""

import os

# =============================================================================
# CORE TRADING PARAMETERS
# =============================================================================

# Timeframe for all strategies (All strategies are designed for 1h)
TIMEFRAME = "1h"

# Leverage multiplier for futures trading
LEVERAGE = 12

# Principal/Stake amount in USDT (wallet balance for backtesting)
PRINCIPAL_USDT = 1000

# =============================================================================
# SYMBOL CONFIGURATION
# =============================================================================

# Primary trading symbols (Binance Futures format: BASE/QUOTE:SETTLE)
SYMBOLS = [
    "SOL/USDT:USDT",
    "DUSK/USDT:USDT",
]

# Additional symbols for multi-asset strategies (optional)
EXTENDED_SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "XRP/USDT:USDT",
    "DOGE/USDT:USDT",
]

# =============================================================================
# EXCHANGE CONFIGURATION
# =============================================================================

EXCHANGE = "binance"
TRADING_MODE = "futures"  # "spot" or "futures"
MARGIN_MODE = "isolated"  # "isolated" or "cross"

# =============================================================================
# BACKTEST SETTINGS
# =============================================================================

BACKTEST_DAYS = 30  # Default days of historical data for backtesting
DRY_RUN_WALLET = PRINCIPAL_USDT  # Simulated wallet for backtesting

# =============================================================================
# DATA DOWNLOAD SETTINGS
# =============================================================================

# Timeframes to download (for multi-timeframe analysis)
DOWNLOAD_TIMEFRAMES = [TIMEFRAME]  # Add more if needed: ["1h", "4h", "1d"]

# =============================================================================
# RISK MANAGEMENT
# =============================================================================

MAX_OPEN_TRADES = 3
STAKE_AMOUNT = "unlimited"  # or fixed value like 100
TRADABLE_BALANCE_RATIO = 0.99

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_freqtrade_config() -> dict:
    """Generate Freqtrade-compatible config dict."""
    return {
        "max_open_trades": MAX_OPEN_TRADES,
        "stake_currency": "USDT",
        "stake_amount": STAKE_AMOUNT,
        "tradable_balance_ratio": TRADABLE_BALANCE_RATIO,
        "timeframe": TIMEFRAME,
        "dry_run": True,
        "dry_run_wallet": DRY_RUN_WALLET,
        "trading_mode": TRADING_MODE,
        "margin_mode": MARGIN_MODE,
        "exchange": {
            "name": EXCHANGE,
            "key": os.getenv("BINANCE_API_KEY", ""),
            "secret": os.getenv("BINANCE_API_SECRET", ""),
            "pair_whitelist": SYMBOLS,
        },
        "exchange_config": {"leverage": LEVERAGE},
    }


def get_download_pairs() -> list:
    """Get list of pairs for data download."""
    return SYMBOLS


def get_timeframe() -> str:
    """Get the system-wide timeframe."""
    return TIMEFRAME


def get_leverage() -> int:
    """Get the system-wide leverage."""
    return LEVERAGE


def get_principal() -> float:
    """Get the starting principal in USDT."""
    return PRINCIPAL_USDT
