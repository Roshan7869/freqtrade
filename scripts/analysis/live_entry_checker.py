import json
import subprocess
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone


def live_entry_checker():
    # 1. Get pairs from market_scan_pairs.txt
    if not os.path.exists("market_scan_pairs.txt"):
        print("market_scan_pairs.txt not found. Run get_market_trending.py first.")
        return

    with open("market_scan_pairs.txt", "r") as f:
        pairs_str = f.read().strip()
    pairs_list = pairs_str.split(",")

    print(f"--- LIVE ENTRY CHECKER ---")
    print(f"Checking {len(pairs_list)} trending tokens for IMMEDIATE entries...")

    # 2. Download latest data (20 days for warmup)
    cmd_download = [
        "docker-compose",
        "-f",
        "infrastructure/docker-compose.backtest.yml",
        "run",
        "--rm",
        "freqtrade-backtest",
        "download-data",
        "--pairs",
        *pairs_list,
        "--days",
        "20",
        "--timeframes",
        "1h",
        "--trading-mode",
        "futures",
        "--exchange",
        "binance",
        "--erase",
    ]

    print("Fetching latest market data for signal analysis...")
    subprocess.run(cmd_download, cwd="c:/Users/USER/Desktop/Algotrading")

    # Define timerange for 'Current' signals (last 12 hours to be sure)
    start_time = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime("%Y%m%d")

    cmd_backtest = [
        "docker-compose",
        "-f",
        "infrastructure/docker-compose.backtest.yml",
        "run",
        "--rm",
        "freqtrade-backtest",
        "backtesting",
        "--config",
        "/freqtrade/user_data/config_backtest.json",
        "--strategy",
        "AroonMACDStrategy",
        "--timerange",
        f"{start_time}-",
        "--pairs",
        *pairs_list,
        "--export",
        "trades",
        "--export-filename",
        "/freqtrade/user_data/backtest_results/live_signals.json",
    ]

    print(f"Analyzing signals since {start_time} (last 6 hours)...")
    subprocess.run(cmd_backtest, cwd="c:/Users/USER/Desktop/Algotrading")

    # 4. Parse detected active entries
    results_path = Path("user_data/backtest_results/live_signals.json")
    if not results_path.exists():
        print("\n[!] No immediate entries detected in the current 1h candles.")
        return

    with open(results_path, "r") as f:
        data = json.load(f)

    strategy_data = data.get("strategy", {}).get("AroonMACDStrategy", {})
    trades = strategy_data.get("trades", [])

    if not trades:
        print("\n[!] No tokens have triggered a NEW entry in the last 6 hours.")
        print("Market is currently between signals for these trending tokens.")
        return

    print("\n🚀 --- ACTIVE / JUST ENTERED SIGNALS --- 🚀")
    print(
        f"{'TOKEN':<15} | {'SIDE':<5} | {'ENTRY TIME (UTC)':<20} | {'PRICE':<10} | {'STATUS'}"
    )
    print("-" * 75)

    # Sort to show newest first
    trades.sort(key=lambda x: x["open_date"], reverse=True)

    for t in trades:
        # Check if the trade is still 'fresh' (last 2 hours)
        is_fresh = (
            "FRESH ENTRY! 🔥"
            if (
                datetime.fromisoformat(t["open_date"].replace("Z", "+00:00"))
                > datetime.now(timezone.utc) - timedelta(hours=2)
            )
            else "Recent Move"
        )

        print(
            f"{t['pair'].split('/')[0]:<15} | {t['side']:<5} | {t['open_date']:<20} | {t['open_rate']:<10.4f} | {is_fresh}"
        )

    print("\nAdvice: Focus on 'FRESH ENTRY' tokens. Momentum is just starting.")


if __name__ == "__main__":
    live_entry_checker()
