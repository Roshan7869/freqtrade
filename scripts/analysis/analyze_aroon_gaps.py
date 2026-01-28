"""
AroonMACDStrategy Gap Analysis
===============================
Identifies efficiency gaps between short-term (7-day) and long-term (300-day) backtests.
"""

import json
import zipfile
import sys
from pathlib import Path

# Setup paths
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
results_dir = project_root / "user_data" / "backtest_results"


def extract_backtest_data(zip_path):
    """Extract JSON data from backtest ZIP file"""
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            candidates = [
                n for n in z.namelist() if n.endswith(".json") and "meta" not in n
            ]
            if candidates:
                with z.open(candidates[0]) as f:
                    return json.load(f)
    except Exception as e:
        print(f"Error reading zip {zip_path}: {e}")
    return None


def analyze_strategy_performance(data, label):
    """Extract and display key metrics"""
    if not data or "strategy" not in data:
        print(f"No data for {label}")
        return None

    if "AroonMACDStrategy" not in data["strategy"]:
        print(f"AroonMACDStrategy not found in {label}")
        return None

    strat = data["strategy"]["AroonMACDStrategy"]

    print(f"\n{'=' * 60}")
    print(f"{label}")
    print(f"{'=' * 60}")

    print(
        f"Period: {strat.get('backtest_start', 'N/A')} to {strat.get('backtest_end', 'N/A')}"
    )

    total_trades = strat.get("total_trades", 0)
    wins = strat.get("wins", 0)

    print(f"Total Trades: {total_trades}")
    print(f"Win Rate: {(wins / total_trades * 100) if total_trades > 0 else 0:.1f}%")
    print(f"Total Profit %: {strat.get('profit_total_pct', 0):.2f}%")
    print(f"Max Drawdown: {strat.get('max_drawdown', 0):.2f}%")

    return strat


def identify_gaps(data_7day, data_300day):
    """Compare and identify efficiency gaps"""
    print(f"\n{'=' * 60}")
    print("GAP ANALYSIS")
    print(f"{'=' * 60}\n")

    if not data_7day or not data_300day:
        return

    s7 = data_7day["strategy"]["AroonMACDStrategy"]
    s300 = data_300day["strategy"]["AroonMACDStrategy"]

    profit_7day = s7.get("profit_total_pct", 0)
    profit_300day = s300.get("profit_total_pct", 0)

    print("GAP #1: PROFIT PERFORMANCE")
    print(f"  7-Day: {profit_7day:.2f}%")
    print(f"  300-Day: {profit_300day:.2f}%")

    freq_7day = s7.get("total_trades", 0) / 7
    freq_300day = s300.get("total_trades", 0) / 300

    print(f"\nGAP #2: DAILY TRADE FREQUENCY")
    print(f"  7-Day: {freq_7day:.2f}")
    print(f"  300-Day: {freq_300day:.2f}")


def main():
    zip_7day = results_dir / "backtest-result-2026-01-28_06-07-49.zip"
    zip_300day = results_dir / "backtest-result-2026-01-28_14-22-55.zip"

    data_7day = extract_backtest_data(zip_7day)
    data_300day = extract_backtest_data(zip_300day)

    analyze_strategy_performance(data_7day, "7-DAY BACKTEST")
    analyze_strategy_performance(data_300day, "300-DAY BACKTEST")

    identify_gaps(data_7day, data_300day)


if __name__ == "__main__":
    main()
