import json
import zipfile
import pandas as pd
from pathlib import Path
from datetime import datetime

# Configuration
results_dir = Path("user_data/backtest_results")
target_file = "backtest-result-2026-01-29_05-11-47.zip"

print(f"Analyzing Long Failures in: {target_file}")
print("=" * 100)

with zipfile.ZipFile(results_dir / target_file, "r") as z:
    json_filename = [
        f for f in z.namelist() if f.endswith(".json") and not f.endswith("config.json")
    ][0]
    data = json.loads(z.read(json_filename))

    strat_name = list(data["strategy"].keys())[0]
    trades = pd.DataFrame(data["strategy"][strat_name]["trades"])

# Filter for LONG trades only
long_trades = trades[trades["is_short"] == False].copy()

if long_trades.empty:
    print("No long trades found to analyze.")
    exit()

# Parse datetime
long_trades["open_date_dt"] = pd.to_datetime(long_trades["open_date"])
long_trades["close_date_dt"] = pd.to_datetime(long_trades["close_date"])
long_trades["duration_mins"] = (
    long_trades["close_date_dt"] - long_trades["open_date_dt"]
).dt.total_seconds() / 60

# Separate Winners and Losers
winners = long_trades[long_trades["profit_abs"] > 0]
losers = long_trades[long_trades["profit_abs"] <= 0]

print(f"Total Long Trades: {len(long_trades)}")
print(f"Winners: {len(winners)}")
print(f"Losers: {len(losers)}")
print(f"Win Rate: {len(winners) / len(long_trades) * 100:.2f}%")
print()

print("DURATION ANALYSIS")
print(
    f"Avg Duration (Winners): {winners['duration_mins'].mean():.1f} min ({winners['duration_mins'].mean() / 60:.1f} hours)"
)
print(
    f"Avg Duration (Losers):  {losers['duration_mins'].mean():.1f} min ({losers['duration_mins'].mean() / 60:.1f} hours)"
)
print("-" * 50)

# Analyzing Losers
print("TOP 10 WORST LONG TRADES")
# Sort by absolute loss (ascending because losses are negative)
worst_trades = losers.sort_values("profit_abs", ascending=True).head(10)

print(
    f"{'Pair':<12} {'Open Date':<20} {'Dur(h)':<8} {'Profit %':<10} {'Loss($)':<10} {'Exit Reason':<15}"
)
for _, row in worst_trades.iterrows():
    print(
        f"{row['pair'].split('/')[0]:<12} {row['open_date_dt'].strftime('%Y-%m-%d %H')}:00 {row['duration_mins'] / 60:<8.1f} {row['profit_ratio'] * 100:<10.2f} {row['profit_abs']:<10.2f} {row['exit_reason']:<15}"
    )

print("\n" + "=" * 50)
print("HYPOTHESIS CHECK")
print("1. Are we holding losers too long? (Compare Durations)")
print("2. Are we getting stopped out instantly? (Short duration losers)")
print("3. Which pairs are the worst offenders?")
pair_losses = losers.groupby("pair")["profit_abs"].sum().sort_values()
print("\nLosses by Pair:")
print(pair_losses)
