import json
import zipfile
import pandas as pd
from pathlib import Path
from datetime import datetime
import os

# Define backtest result directory
results_dir = Path("user_data/backtest_results")


def scan_strategies():
    print(f"Scanning {results_dir} for backtest results...")

    strategy_results = []

    # List all zip files
    zip_files = list(results_dir.glob("*.zip"))

    if not zip_files:
        print("No backtest ZIP files found.")
        return

    print(f"Found {len(zip_files)} backtest files. Processing...")

    for zip_path in zip_files:
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                # Find the main JSON file (usually matches the zip name w/o extension)
                json_files = [
                    f
                    for f in z.namelist()
                    if f.endswith(".json") and not f.endswith("_config.json")
                ]

                if not json_files:
                    continue

                # Usually the first one is the main result
                result_file = json_files[0]

                with z.open(result_file) as f:
                    data = json.load(f)

                # Extract Strategy Name (key of 'strategy')
                if "strategy" not in data:
                    continue

                strategy_name = list(data["strategy"].keys())[0]
                strat_data = data["strategy"][strategy_name]

                # Extract Metrics
                profit_pct = strat_data.get("profit_total_pct", 0)
                if profit_pct == 0 and "profit_total" in strat_data:
                    profit_pct = strat_data["profit_total"]  # Handle different formats

                trades_count = strat_data.get("total_trades", 0)

                # Calculate win rate if not explicit
                wins = strat_data.get("wins", 0)
                win_rate = (wins / trades_count * 100) if trades_count > 0 else 0

                # Drawdown
                drawdown = strat_data.get("max_drawdown_account", 0) * 100

                # Date of backtest (from filename or metadata)
                # Filename format: backtest-result-YYYY-MM-DD_HH-MM-SS.zip
                timestamp_str = zip_path.stem.replace("backtest-result-", "")
                try:
                    date_obj = datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
                except ValueError:
                    date_obj = datetime.min

                strategy_results.append(
                    {
                        "Strategy": strategy_name,
                        "File": zip_path.name,
                        "Date": date_obj,
                        "Profit %": profit_pct * 100
                        if abs(profit_pct) < 10
                        else profit_pct,  # Normalize? usually profit_total is decimal e.g. -0.43 for -43%
                        "Trades": trades_count,
                        "Win Rate %": win_rate,
                        "Drawdown %": drawdown,
                    }
                )

        except Exception as e:
            # print(f"Error reading {zip_path.name}: {e}")
            pass

    # Convert to DataFrame
    if not strategy_results:
        print("No valid strategy results found.")
        return

    df = pd.DataFrame(strategy_results)

    # Sort by Strategy and Date (descending) to get latest
    df = df.sort_values(by=["Strategy", "Date"], ascending=[True, False])

    # Keep only the latest result for each strategy
    latest_df = df.drop_duplicates(subset=["Strategy"], keep="first")

    # Sort leaderboard by Profit
    leaderboard = latest_df.sort_values(by="Profit %", ascending=False)

    print("\n" + "=" * 80)
    print("STRATEGY PERFORMANCE LEADERBOARD (LATEST RUN PER STRATEGY)")
    print("=" * 80)
    # Format for nicer printing
    print_df = leaderboard[
        ["Strategy", "Profit %", "Win Rate %", "Drawdown %", "Trades", "Date"]
    ]
    print(
        print_df.to_string(
            index=False,
            formatters={
                "Profit %": "{:,.2f}%".format,
                "Win Rate %": "{:,.1f}%".format,
                "Drawdown %": "{:,.2f}%".format,
                "Date": lambda x: x.strftime("%Y-%m-%d %H:%M"),
            },
        )
    )
    print("\n" + "=" * 80)

    # Find winning strategies
    winners = leaderboard[leaderboard["Profit %"] > 0]
    if not winners.empty:
        print("\nWINNING STRATEGIES FOUND:")
        for _, row in winners.iterrows():
            print(f"- {row['Strategy']}: {row['Profit %']:.2f}%")
    else:
        print("\nNo winning strategies found in scanned backtests.")


if __name__ == "__main__":
    scan_strategies()
