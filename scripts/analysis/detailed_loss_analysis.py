import json
import zipfile
import pandas as pd
from pathlib import Path

# Define backtest result files
results_dir = Path("user_data/backtest_results")
backtest_300day = "backtest-result-2026-01-29_04-24-07.zip"

print("=" * 100)
print("AROONMACD STRATEGY - DETAILED LOSS ANALYSIS (300-DAY BACKTEST)")
print("=" * 100)
print()

with zipfile.ZipFile(results_dir / backtest_300day, "r") as z:
    data = json.loads(z.read("backtest-result-2026-01-29_04-24-07.json"))
    strat = data["strategy"]["AroonMomentumEngine"]
    trades = pd.DataFrame(strat["trades"])

# Basic stats
print(f"Total Trades: {len(trades)}")
print(f"Win Rate: {len(trades[trades['profit_abs'] > 0]) / len(trades) * 100:.1f}%")
print(f"Total Profit: {strat['profit_total'] * 100:.2f}%")
print()

# Long vs Short Analysis
longs = trades[trades["is_short"] == False]
shorts = trades[trades["is_short"] == True]

print("LONG vs SHORT PERFORMANCE:")
print("-" * 100)
print(
    f"{'Type':<10} {'Count':<10} {'Win Rate':<12} {'Profit (USDT)':<18} {'Profit %':<12} {'Avg Profit/Trade'}"
)
print("-" * 100)

for trade_type, df in [("LONG", longs), ("SHORT", shorts)]:
    count = len(df)
    win_rate = len(df[df["profit_abs"] > 0]) / count * 100 if count > 0 else 0
    total_profit = df["profit_abs"].sum()
    total_pct = total_profit / 1000 * 100  # Assuming 1000 USDT starting capital
    avg_profit = total_profit / count if count > 0 else 0
    print(
        f"{trade_type:<10} {count:<10} {win_rate:<12.1f} {total_profit:<18.2f} {total_pct:<12.2f} {avg_profit:.2f}"
    )

print()
print()

# Pair-wise Analysis
print("PAIR-WISE PERFORMANCE:")
print("-" * 100)
print(
    f"{'Pair':<18} {'Trades':<10} {'Win Rate':<12} {'Profit (USDT)':<18} {'Best Trade':<15} {'Worst Trade'}"
)
print("-" * 100)

for pair in trades["pair"].unique():
    pair_trades = trades[trades["pair"] == pair]
    count = len(pair_trades)
    win_rate = len(pair_trades[pair_trades["profit_abs"] > 0]) / count * 100
    total_profit = pair_trades["profit_abs"].sum()
    best = pair_trades["profit_abs"].max()
    worst = pair_trades["profit_abs"].min()
    print(
        f"{pair:<18} {count:<10} {win_rate:<12.1f} {total_profit:<18.2f} {best:<15.2f} {worst:.2f}"
    )

print()
print()

# Duration Analysis
trades["duration_hours"] = trades["trade_duration"] / 60  # Convert minutes to hours
winners = trades[trades["profit_abs"] > 0]
losers = trades[trades["profit_abs"] < 0]

print("TRADE DURATION ANALYSIS:")
print("-" * 100)
print(
    f"Winners avg duration: {winners['duration_hours'].mean():.1f} hours ({winners['duration_hours'].mean() / 24:.1f} days)"
)
print(
    f"Losers avg duration: {losers['duration_hours'].mean():.1f} hours ({losers['duration_hours'].mean() / 24:.1f} days)"
)
print(
    f"Ratio (Loser/Winner): {losers['duration_hours'].mean() / winners['duration_hours'].mean():.2f}x"
)
print()
if losers["duration_hours"].mean() > winners["duration_hours"].mean() * 1.3:
    print(
        "⚠️ CRITICAL: Losers hold LONGER than winners - strategy is not cutting losses fast enough!"
    )
else:
    print("✓ OK: Winners and losers have similar durations")
print()

# Worst Losing Trades
print()
print("TOP 10 WORST LOSING TRADES:")
print("-" * 100)
worst_10 = losers.nsmallest(10, "profit_abs")[
    [
        "pair",
        "open_date",
        "close_date",
        "profit_abs",
        "profit_ratio",
        "is_short",
        "exit_reason",
    ]
]
print(worst_10.to_string(index=False))
print()

# Exit Reason Analysis
print()
print("EXIT REASON BREAKDOWN:")
print("-" * 100)
exit_reasons = (
    trades.groupby("exit_reason").agg({"profit_abs": ["count", "sum", "mean"]}).round(2)
)
print(exit_reasons)
print()

# Key Findings
print()
print("=" * 100)
print("KEY FINDINGS & ROOT CAUSES:")
print("=" * 100)

# Issue 1: Long vs Short imbalance
long_profit_pct = longs["profit_abs"].sum() / 1000 * 100
short_profit_pct = shorts["profit_abs"].sum() / 1000 * 100

print(f"\\n1. LONG vs SHORT IMBALANCE")
print(f"   Long  Profit: {long_profit_pct:.1f}%")
print(f"   Short Profit: {short_profit_pct:.1f}%")
if long_profit_pct < -20:
    print(f"   ❌ CRITICAL: Longs are hemorrhaging money")
    print(
        f"   ROOT CAUSE: Strategy enters longs against the trend or in ranging markets"
    )
    print(
        f"   FIX REQUIRED: Add EMA200 trend filter - only long when price > EMA200(4h)"
    )

# Issue 2: Duration analysis
ratio = losers["duration_hours"].mean() / winners["duration_hours"].mean()
print(f"\\n2. TRADE DURATION")
print(f"   Loser/Winner Duration Ratio: {ratio:.2f}x")
if ratio > 1.5:
    print(f"   ❌ CRITICAL: Losers hold {ratio:.1f}x longer")
    print(f"   ROOT CAUSE: ATR stoploss (2.5x) is too wide")
    print(f"   FIX REQUIRED: Reduce ATR multiplier from 2.5 to 1.5-2.0")

# Issue 3: Win rate vs profitability paradox
win_rate = len(winners) / len(trades) * 100
avg_win = winners["profit_abs"].mean()
avg_loss = losers["profit_abs"].mean()
loss_win_ratio = abs(avg_loss / avg_win)

print(f"\\n3. WIN/LOSS RATIO")
print(f"   Win Rate: {win_rate:.1f}%")
print(f"   Avg Win:  {avg_win:.2f} USDT")
print(f"   Avg Loss: {avg_loss:.2f} USDT")
print(f"   Loss/Win Ratio: {loss_win_ratio:.2f}x")

if win_rate > 65 and loss_win_ratio > 3:
    print(
        f"   ❌ PARADOX: High win rate but losses are {loss_win_ratio:.1f}x larger than wins!"
    )
    print(f"   ROOT CAUSE: The 2:1 risk/reward target is NOT working")
    print(
        f"   FIX REQUIRED: Review custom_exit logic - exits may be triggering too early"
    )

print()
print("=" * 100)
print("RECOMMENDED FIXES (in priority order):")
print("=" * 100)
print("1. Add EMA200 trend filter for long entries")
print("2. Reduce ATR multiplier from 2.5x to 1.8x")
print("3. Review and fix take-profit logic in custom_exit")
print("=" * 100)
