import json
import subprocess
import os
from pathlib import Path


def run_scanner():
    # Load pairs from the previous step
    if not os.path.exists("market_scan_pairs.txt"):
        print("market_scan_pairs.txt not found. Run get_market_trending.py first.")
        return

    with open("market_scan_pairs.txt", "r") as f:
        pairs = f.read().strip()

    print(f"Scanning {len(pairs.split(','))} pairs for AroonMACDStrategy signals...")

    # Run backtest for the last 2 days
    # We use a 5-day range to ensure data warmup for indicators (Aroon needs 400 candles on 1h, which is ~16 days)
    # Wait, 400 candles on 1h is 400 hours = 16.6 days.
    # Let me check the startup_candle_count in the strategy. It says 400.
    # If I only download 5 days, it might not work.
    # I should have downloaded more. Let me check the download command again.
    # I used --days 5. That's not enough for 400 startup candles on 1h.
    # I'll download 20 days instead to be safe.

    cmd_download = [
        "docker-compose",
        "-f",
        "infrastructure/docker-compose.backtest.yml",
        "run",
        "--rm",
        "freqtrade-backtest",
        "download-data",
        "--pairs",
        *pairs.split(","),
        "--days",
        "25",
        "--timeframes",
        "1h",
        "--trading-mode",
        "futures",
        "--exchange",
        "binance",
        "--erase",
    ]

    print("Redownloading more data for indicator warmup (25 days)...")
    subprocess.run(cmd_download, cwd="c:/Users/USER/Desktop/Algotrading")

    # Now run backtest
    # Timerange: 2 days ago to now.
    # Example format: 20260126-

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
        "20260126-",
        "--pairs",
        *pairs.split(","),
        "--export",
        "trades",
        "--export-filename",
        "/freqtrade/user_data/backtest_results/live_scan.json",
    ]

    print("Running backtest analysis...")
    subprocess.run(cmd_backtest, cwd="c:/Users/USER/Desktop/Algotrading")

    # Read the results
    results_path = Path("user_data/backtest_results/live_scan.json")
    if not results_path.exists():
        print("No trades found or backtest failed to export.")
        return

    with open(results_path, "r") as f:
        data = json.load(f)

    strategy_data = data.get("strategy", {}).get("AroonMACDStrategy", {})
    trades = strategy_data.get("trades", [])

    if not trades:
        print("\nNo entry signals found in the last 2 days for these tokens.")
        return

    print("\n--- DETECTED ENTRY SIGNALS (AroonMACDStrategy) ---")
    print(f"{'Pair':<20} | {'Side':<6} | {'Entry Time':<20} | {'Entry Price':<12}")
    print("-" * 65)

    # Sort by time to show most recent first
    trades.sort(key=lambda x: x["open_date"], reverse=True)

    for t in trades:
        print(
            f"{t['pair']:<20} | {t['side']:<6} | {t['open_date']:<20} | {t['open_rate']:<12.5f}"
        )


if __name__ == "__main__":
    run_scanner()
