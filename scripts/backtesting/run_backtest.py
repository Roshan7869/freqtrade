"""
Run Backtest Script
===================
Runs backtesting using centralized config for timeframe, leverage, and principal.
Usage: python scripts/run_backtest.py --strategy StrategyName [--days 30]
"""

import argparse
import subprocess
import sys
import os
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.trading_config import (
    SYMBOLS,
    TIMEFRAME,
    LEVERAGE,
    PRINCIPAL_USDT,
    BACKTEST_DAYS,
    get_freqtrade_config,
)


def generate_config_file(output_path: str):
    """Generate Freqtrade config JSON from centralized config."""
    config = get_freqtrade_config()

    config["api_server"] = {
        "enabled": False,
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8080,
        "username": "freqtrader",
        "password": "SuperSecurePassword",
    }
    config["telegram"] = {"enabled": False, "token": "", "chat_id": ""}
    config["pairlists"] = [{"method": "StaticPairList"}]

    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)

    return output_path


def run_backtest(strategy: str, days: int = None):
    """Run backtesting using Docker."""
    days = days or BACKTEST_DAYS

    # Calculate timerange
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    timerange = f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"

    # Generate temp config
    config_path = os.path.join(os.path.dirname(__file__), "temp_config.json")
    generate_config_file(config_path)

    base_path = os.path.dirname(os.path.dirname(__file__))

    cmd = f"""docker run --rm \\
        -v {base_path}/user_data:/freqtrade/user_data \\
        -v {config_path}:/freqtrade/user_data/config.json \\
        freqtradeorg/freqtrade:stable backtesting \\
        --config /freqtrade/user_data/config.json \\
        --strategy {strategy} \\
        --timerange {timerange} \\
        -i {TIMEFRAME} \\
        --enable-protections"""

    print("=" * 60)
    print(f"BACKTEST: {strategy}")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"Leverage: {LEVERAGE}x")
    print(f"Principal: {PRINCIPAL_USDT} USDT")
    print(f"Pairs: {SYMBOLS}")
    print(f"Period: {timerange} ({days} days)")
    print("=" * 60)

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")

    return result.returncode == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument("--strategy", required=True, help="Strategy class name")
    parser.add_argument("--days", type=int, default=BACKTEST_DAYS, help="Days of data")
    args = parser.parse_args()

    success = run_backtest(args.strategy, args.days)
    sys.exit(0 if success else 1)
