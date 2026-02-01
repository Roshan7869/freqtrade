"""
PnL Cycle Analyzer
==================
Simulates account growth for specific tokens with fixed starting capital.
Target: $100 per token (SOL, DOGE, XRP).
"""

import os
import sys
import json
import logging
import zipfile
import pandas as pd
from datetime import datetime
from pathlib import Path

# Setup paths
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
results_dir = project_root / "user_data" / "backtest_results"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PnLAnalyzer")

TARGET_STRATEGIES = [
    "EMA8_13_21_MACDStrategy",
    "AroonMACDStrategy",
    "TripleMAStrategy",
    "Stockbee_EP_Strategy",
]

TARGET_PAIRS = ["SOL/USDT:USDT", "DOGE/USDT:USDT", "XRP/USDT:USDT"]

STARTING_CAPITAL_PER_TOKEN = 100.0  # USDT


def load_best_trades(strategy_name):
    """Scan recent backtest files (JSON and ZIP) to find trades"""
    all_files = list(results_dir.glob("backtest-result-*.json")) + list(
        results_dir.glob("backtest-result-*.zip")
    )

    files = sorted(all_files, key=lambda f: f.stat().st_mtime, reverse=True)

    for file_path in files:
        if "meta" in file_path.name:
            continue

        try:
            data = None
            if file_path.suffix == ".zip":
                with zipfile.ZipFile(file_path, "r") as z:
                    candidates = [
                        n
                        for n in z.namelist()
                        if n.endswith(".json") and "meta" not in n
                    ]
                    if candidates:
                        with z.open(candidates[0]) as f:
                            data = json.load(f)
            else:
                with open(file_path, "r") as f:
                    data = json.load(f)

            if not data or "strategy" not in data:
                continue

            if strategy_name in data["strategy"]:
                strat_data = data["strategy"][strategy_name]
                trades = strat_data.get("trades", [])
                if trades:
                    logger.info(
                        f"Found {len(trades)} trades for {strategy_name} in {file_path.name}"
                    )
                    return trades

        except Exception as e:
            continue

    return []


def run_simulation(strategy_name):
    trades = load_best_trades(strategy_name)
    if not trades:
        print(f"Skipping {strategy_name} (No trades found)")
        return

    print(f"\n{'=' * 60}")
    print(f"PnL ANALYSIS: {strategy_name}")
    print(f"{'=' * 60}")

    grand_total_profit = 0
    grand_final_balance = 0
    grand_start_balance = 0

    for pair in TARGET_PAIRS:
        pair_trades = [t for t in trades if t["pair"] == pair]
        pair_trades.sort(key=lambda x: x["open_date"])

        balance = STARTING_CAPITAL_PER_TOKEN
        peak_balance = balance
        max_drawdown = 0.0

        print(f"\n Pair: {pair} (Start: ${STARTING_CAPITAL_PER_TOKEN})")
        grand_start_balance += STARTING_CAPITAL_PER_TOKEN

        if not pair_trades:
            print("   No trades executed.")
            grand_final_balance += balance
            continue

        for t in pair_trades:
            profit_ratio = t["profit_ratio"]
            pnl_amount = balance * profit_ratio
            balance += pnl_amount

            if balance > peak_balance:
                peak_balance = balance

            dd = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0
            if dd > max_drawdown:
                max_drawdown = dd

        total_return_pct = (
            (balance - STARTING_CAPITAL_PER_TOKEN) / STARTING_CAPITAL_PER_TOKEN
        ) * 100
        net_profit = balance - STARTING_CAPITAL_PER_TOKEN

        print(f"   Final Balance: ${balance:.2f}")
        print(f"   Net Profit:    ${net_profit:.2f} ({total_return_pct:.1f}%)")
        print(f"   Max Drawdown:  {max_drawdown * 100:.1f}%")
        print(f"   Trade Count:   {len(pair_trades)}")

        grand_total_profit += net_profit
        grand_final_balance += balance

    print(f"\n{'-' * 60}")
    print(f"TOTAL PORTFOLIO PERFORMANCE ({strategy_name})")
    print(f"   Start Capital: ${grand_start_balance:.2f}")
    print(f"   End Capital:   ${grand_final_balance:.2f}")
    print(f"   Total Profit:  ${grand_total_profit:.2f}")

    if grand_start_balance > 0:
        roi = (grand_total_profit / grand_start_balance) * 100
        print(f"   Total ROI:     {roi:.1f}%")
    print(f"{'=' * 60}\n")


def main():
    print("Starting PnL Cycle Analysis...")
    for strat in TARGET_STRATEGIES:
        run_simulation(strat)


if __name__ == "__main__":
    main()
