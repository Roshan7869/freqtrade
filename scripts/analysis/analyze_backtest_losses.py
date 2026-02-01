import json
import zipfile
import pandas as pd
from pathlib import Path

# Define backtest result files
results_dir = Path("user_data/backtest_results")

# Find the 300-day backtest (the one before the 5-day which is 04-28-49)
# Looking for 04-24-07 which is the 300-day one
backtest_300day = "backtest-result-2026-01-29_04-24-07.zip"
backtest_5day = "backtest-result-2026-01-29_04-28-49.zip"


def analyze_backtest(zip_file):
    """Extract and analyze backtest results"""
    results = {}

    with zipfile.ZipFile(results_dir / zip_file, "r") as z:
        # List all files in the zip
        files = z.namelist()

        # Find the JSON file with results
        json_file = [f for f in files if f.endswith(".json")][0]

        with z.open(json_file) as f:
            data = json.load(f)

        # Extract key metrics
        strategy_data = data["strategy"][list(data["strategy"].keys())[0]]
        results["total_trades"] = strategy_data["total_trades"]
        results["wins"] = strategy_data["wins"]
        results["losses"] = strategy_data["losses"]
        results["profit_total"] = strategy_data["profit_total"]
        results["profit_pct"] = strategy_data["profit_total_pct"]

        # Load trades if available
        if "trades" in data:
            trades_df = pd.DataFrame(data["trades"])
            results["trades"] = trades_df

            # Categorize trades
            long_trades = trades_df[trades_df["is_short"] == False]
            short_trades = trades_df[trades_df["is_short"] == True]

            results["long_count"] = len(long_trades)
            results["short_count"] = len(short_trades)
            results["long_profit"] = (
                long_trades["profit_abs"].sum() if len(long_trades) > 0 else 0
            )
            results["short_profit"] = (
                short_trades["profit_abs"].sum() if len(short_trades) > 0 else 0
            )

            # Analyze loss patterns
            losing_trades = trades_df[trades_df["profit_abs"] < 0]
            results["losing_trades"] = losing_trades
            results["avg_loss"] = (
                losing_trades["profit_abs"].mean() if len(losing_trades) > 0 else 0
            )
            results["max_loss"] = (
                losing_trades["profit_abs"].min() if len(losing_trades) > 0 else 0
            )

            # Analyze average trade duration
            trades_df["duration_hours"] = (
                pd.to_datetime(trades_df["close_date"])
                - pd.to_datetime(trades_df["open_date"])
            ).dt.total_seconds() / 3600
            results["avg_duration_winners"] = trades_df[trades_df["profit_abs"] > 0][
                "duration_hours"
            ].mean()
            results["avg_duration_losers"] = trades_df[trades_df["profit_abs"] < 0][
                "duration_hours"
            ].mean()

    return results


print("=" * 80)
print("AROON MACD STRATEGY LOSS ANALYSIS")
print("=" * 80)
print()

# Analyze 300-day backtest
print("300-DAY BACKTEST ANALYSIS")
print("-" * 80)
try:
    results_300 = analyze_backtest(backtest_300day)

    print(f"Total Trades: {results_300['total_trades']}")
    print(f"Win Rate: {results_300['wins'] / results_300['total_trades'] * 100:.1f}%")
    print(f"Total Profit: {results_300['profit_pct']:.2f}%")
    print()
    print(
        f"Long Trades: {results_300['long_count']} (Profit: {results_300['long_profit']:.2f} USDT)"
    )
    print(
        f"Short Trades: {results_300['short_count']} (Profit: {results_300['short_profit']:.2f} USDT)"
    )
    print()
    print(f"Average Loss: {results_300['avg_loss']:.2f} USDT")
    print(f"Maximum Single Loss: {results_300['max_loss']:.2f} USDT")
    print(f"Average Winner Duration: {results_300['avg_duration_winners']:.1f} hours")
    print(f"Average Loser Duration: {results_300['avg_duration_losers']:.1f} hours")
    print()

    # Analyze worst losing trades
    worst_10 = results_300["losing_trades"].nsmallest(10, "profit_abs")[
        ["pair", "open_date", "close_date", "profit_abs", "is_short"]
    ]
    print("Top 10 Worst Losing Trades:")
    print(worst_10.to_string(index=False))
    print()

except Exception as e:
    print(f"Error analyzing 300-day backtest: {e}")

print()
print("=" * 80)
print("5-DAY BACKTEST ANALYSIS")
print("-" * 80)
try:
    results_5 = analyze_backtest(backtest_5day)

    print(f"Total Trades: {results_5['total_trades']}")
    print(f"Win Rate: {results_5['wins'] / results_5['total_trades'] * 100:.1f}%")
    print(f"Total Profit: {results_5['profit_pct']:.2f}%")
    print()
    print(
        f"Long Trades: {results_5['long_count']} (Profit: {results_5['long_profit']:.2f} USDT)"
    )
    print(
        f"Short Trades: {results_5['short_count']} (Profit: {results_5['short_profit']:.2f} USDT)"
    )
    print()

except Exception as e:
    print(f"Error analyzing 5-day backtest: {e}")

print()
print("=" * 80)
print("KEY FINDINGS")
print("=" * 80)
print("1. Compare long vs short performance")
print("2. Check if losers hold longer than winners (sign of not cutting losses)")
print("3. Identify if losses are concentrated in specific pairs/timeframes")
