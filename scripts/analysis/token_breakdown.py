import json
import zipfile
import pandas as pd
from pathlib import Path

# Define backtest result files
results_dir = Path("user_data/backtest_results")
target_file = "backtest-result-2026-01-29_05-11-47.zip"

print(f"Analyzing: {target_file}")
print("=" * 100)

with zipfile.ZipFile(results_dir / target_file, "r") as z:
    # Find JSON file inside zip
    json_filename = [
        f for f in z.namelist() if f.endswith(".json") and not f.endswith("config.json")
    ][0]
    data = json.loads(z.read(json_filename))

    # Get strategy data
    strat_name = list(data["strategy"].keys())[0]
    strat_data = data["strategy"][strat_name]
    trades = pd.DataFrame(strat_data["trades"])

# Overall Stats
print(f"Strategy: {strat_name}")
print(f"Total Trades: {len(trades)}")
print(
    f"Total Profit: {strat_data.get('profit_total_pct', 0) * 100:.2f}% ({strat_data.get('profit_total_abs', 0):.2f} USDT)"
)
print(f"Max Drawdown: {strat_data.get('max_drawdown_account', 0) * 100:.2f}%")
print()

# Per-Token Analysis
print("PER-TOKEN PERFORMANCE (300 DAYS)")
print("=" * 100)
print(
    f"{'Token':<12} {'Trades':<8} {'Win Rate':<10} {'Profit %':<12} {'Profit (USDT)':<15} {'Max Drawdown %':<15}"
)
print("-" * 100)

for pair in trades["pair"].unique():
    pair_trades = trades[trades["pair"] == pair]
    token_name = pair.split("/")[0]

    count = len(pair_trades)
    wins = len(pair_trades[pair_trades["profit_abs"] > 0])
    win_rate = wins / count * 100

    profit_abs = pair_trades["profit_abs"].sum()
    profit_pct = (profit_abs / 333.33) * 100  # Assuming 1/3 explicit stake distribution

    # Calculate Max Drawdown for this pair (approximate from trade sequence)
    pair_trades = pair_trades.sort_values("close_date")
    pair_trades["cum_profit"] = pair_trades["profit_abs"].cumsum()
    pair_trades["peak"] = pair_trades["cum_profit"].cummax()
    pair_trades["drawdown"] = pair_trades["cum_profit"] - pair_trades["peak"]
    max_dd_abs = pair_trades["drawdown"].min()
    max_dd_pct = (max_dd_abs / 333.33) * 100 if max_dd_abs < 0 else 0.0

    print(
        f"{token_name:<12} {count:<8} {win_rate:<10.1f} {profit_pct:<12.2f} {profit_abs:<15.2f} {abs(max_dd_pct):<15.2f}"
    )

print("-" * 100)
print()

# Long vs Short per token
print("LONG vs SHORT BREAKDOWN PER TOKEN")
print("=" * 100)
for pair in trades["pair"].unique():
    token_name = pair.split("/")[0]
    pair_trades = trades[trades["pair"] == pair]

    longs = pair_trades[pair_trades["is_short"] == False]
    shorts = pair_trades[pair_trades["is_short"] == True]

    long_profit = longs["profit_abs"].sum()
    short_profit = shorts["profit_abs"].sum()

    print(f"{token_name}:")
    print(f"  Longs:  {len(longs)} trades, Profit: {long_profit:.2f} USDT")
    print(f"  Shorts: {len(shorts)} trades, Profit: {short_profit:.2f} USDT")
    print()
