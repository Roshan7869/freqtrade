import json
import zipfile
import glob
import os
import pandas as pd
from datetime import datetime

# Find latest zip file
list_of_files = glob.glob("user_data/backtest_results/backtest-result-*.zip")
latest_file = max(list_of_files, key=os.path.getctime)
print(f"Reading: {latest_file}")

with zipfile.ZipFile(latest_file, "r") as z:
    # Find the json file inside
    json_files = [f for f in z.namelist() if f.endswith(".json") and "meta" not in f]
    if not json_files:
        print("No JSON result file found in zip.")
        exit(1)

    with z.open(json_files[0]) as f:
        data = json.load(f)

# Extract trades for AroonMomentumEngine_Shorts
strategy_name = "AroonMomentumEngine_Shorts"
if strategy_name not in data["strategy"]:
    print(f"Strategy {strategy_name} not found in results.")
    # Try finding any strategy
    strategy_name = list(data["strategy"].keys())[0]
    print(f"Using strategy: {strategy_name}")

trades = data["strategy"][strategy_name]["trades"]
print(f"Found {len(trades)} trades.")

# Print details
for trade in trades:
    pair = trade["pair"]
    open_date = trade["open_date"]
    close_date = trade["close_date"]
    profit_pct = trade["profit_ratio"] * 100
    profit_abs = trade["profit_abs"]
    print(
        f"Pair: {pair}, Open: {open_date}, Close: {close_date}, Profit: {profit_pct:.2f}% (${profit_abs:.2f})"
    )
