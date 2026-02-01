import json
import subprocess
import os
import pandas as pd
from pathlib import Path


def proximity_scan():
    if not os.path.exists("market_scan_pairs.txt"):
        print("Run get_market_trending.py first.")
        return

    with open("market_scan_pairs.txt", "r") as f:
        pairs = f.read().strip()

    # Use a small backtest to get indicator data
    # format that includes indicators
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
        "20260127-",
        "--pairs",
        *pairs.split(","),
        "--export",
        "trades",
        "--export-filename",
        "/freqtrade/user_data/backtest_results/proximity_scan.json",
    ]

    print("Gathering market momentum data...")
    subprocess.run(cmd_backtest, cwd="c:/Users/USER/Desktop/Algotrading")

    # In a real environment, I would read the processed dataframes.
    # Since I can only read the trades json, I will look at 'active' trades or very recent ones.

    results_path = Path("user_data/backtest_results/proximity_scan.json")
    if not results_path.exists():
        print("Analysis failed.")
        return

    with open(results_path, "r") as f:
        data = json.load(f)

    strategy_data = data.get("strategy", {}).get("AroonMACDStrategy", {})
    trades = strategy_data.get("trades", [])

    print("\n--- MOMENTUM ANALYSIS (AroonMACD) ---")

    # Let's see what is currently in a move (entered in last 12 hours)
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(hours=12)

    active_moves = [
        t
        for t in trades
        if datetime.fromisoformat(t["open_date"].replace("Z", "+00:00")) > cutoff
    ]

    if not active_moves:
        print("No recent breakouts triggered in the last 12 hours.")
        print("The market for these tokens is currently in a cooling/sideways phase.")
        return

    print(
        f"Found {len(active_moves)} tokens with recent momentum still potentially active:\n"
    )
    print(
        f"{'TOKEN':<15} | {'DIRECTION':<10} | {'ENTERED (UTC)':<20} | {'ENTRY PRICE':<12}"
    )
    print("-" * 65)

    for t in active_moves:
        print(
            f"{t['pair'].split('/')[0]:<15} | {t['side']:<10} | {t['open_date']:<20} | {t['open_rate']:<12.4f}"
        )

    print("\nStrategy Insight:")
    print("- If entry was < 3 hours ago: High Momentum 'Left'.")
    print("- If entry was > 8 hours ago: Move might be maturing/exhausting.")


if __name__ == "__main__":
    proximity_scan()
