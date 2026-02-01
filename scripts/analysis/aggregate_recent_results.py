import os
import json
from datetime import datetime, timedelta


def aggregate_results():
    results_dir = "user_data/backtest_results"
    one_hour_ago = datetime.now() - timedelta(hours=2)

    aggregated = []

    for filename in os.listdir(results_dir):
        if filename.endswith(".meta.json"):
            file_path = os.path.join(results_dir, filename)
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))

            if file_time > one_hour_ago:
                try:
                    with open(file_path, "r") as f:
                        data = json.load(f)
                        # The meta.json usually points to the actual result file or contains strategy keys
                        # We need to find the strategy names and their profits
                        for strat_name, info in data.get("strategy_comparison", []):
                            aggregated.append(
                                {
                                    "strategy": strat_name,
                                    "profit": info.get("profit_tot_percent", 0),
                                    "trades": info.get("trade_count", 0),
                                    "win_rate": info.get("win_rate", 0),
                                }
                            )

                        # If strategy_comparison is not there, check for a single strategy
                        if not data.get("strategy_comparison"):
                            # We might need to look into the .zip/json file, but let's try reading the .meta.json more carefully
                            pass
                except Exception as e:
                    print(f"Error reading {filename}: {e}")

    # Sort by profit
    aggregated.sort(key=lambda x: x["profit"], reverse=True)

    print("| Strategy | Total Profit % | Trade Count | Win Rate |")
    print("| :--- | :--- | :--- | :--- |")
    for res in aggregated:
        print(
            f"| {res['strategy']} | {res['profit']:.2f}% | {res['trades']} | {res['win_rate']:.2%}|"
        )


if __name__ == "__main__":
    aggregate_results()
