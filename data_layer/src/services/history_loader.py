"""
Download Data Script
====================
Downloads historical data for backtesting using centralized config.
Usage: python scripts/download_data.py [--days 30]
"""

import argparse
import subprocess
import sys
import os
import json

# sys.path handled by main.py
from shared.trading_config import (
    SYMBOLS,
    TIMEFRAME,
    BACKTEST_DAYS,
    get_freqtrade_config,
)


def generate_config_file(output_path: str):
    """Generate Freqtrade config JSON from centralized config."""
    config = get_freqtrade_config()
    # ... (rest of config generation same as before, simplified for brevity in this replace block if unchanged)
    # Actually I should keep the content intact or just replace the top and bottom.

    # Add required fields for Freqtrade
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


def download_data(days: int = None):
    """Download historical data using Docker."""
    days = days or BACKTEST_DAYS

    # Calculate paths relative to project root
    # We assume we are running from data_layer/src/main.py, so cwd might be project root or src
    # Safer to find project root relative to this file
    current_file = os.path.abspath(__file__)
    # data_layer/src/services/history_loader.py -> up 3 levels to project root
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    )

    config_path = os.path.join(project_root, "user_data", "temp_config_gen.json")
    generate_config_file(config_path)

    pairs = " ".join([f"-p {p}" for p in SYMBOLS])

    # Windows path handling for Docker if needed, but assuming standard Python paths

    cmd = f"""docker run --rm \\
        -v "{os.path.join(project_root, "user_data")}":/freqtrade/user_data \\
        freqtradeorg/freqtrade:stable download-data \\
        --config /freqtrade/user_data/temp_config_gen.json \\
        --days {days} -t {TIMEFRAME} {pairs}"""

    print(f"Downloading {days} days of data for {SYMBOLS} at {TIMEFRAME}...")
    print(f"Command: {cmd}")

    # Execute
    result = subprocess.run(cmd, shell=True)  # Removed capture_output to show progress
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Download historical data")
    parser.add_argument("--days", type=int, default=BACKTEST_DAYS, help="Days of data")
    # Parse args only if run directly or pass emptylist if called from code without args?
    # actually main() is called from orchestrator without args, so we should rely on defaults or sys.argv
    # If run from main.py, sys.argv might contain 'history' etc. which confuses parser.
    # Better to make get_args optional or parse specific args.

    # Simplification: If called from module, we use defaults.
    if len(sys.argv) > 1 and sys.argv[0].endswith("history_loader.py"):
        args = parser.parse_args()
        days = args.days
    else:
        days = BACKTEST_DAYS

    success = download_data(days)
    return success


if __name__ == "__main__":
    main()
