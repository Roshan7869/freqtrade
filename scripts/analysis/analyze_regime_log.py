import re
from collections import defaultdict


def analyze_log():
    log_path = "user_data/backtest_debug.log"

    # Stats containers
    regime_counts = defaultdict(int)
    strategy_signals = defaultdict(int)
    confirmed_trades = []

    print(f"Parsing {log_path}...")

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            # Parse Regime Counts (from logs like "DEBUG: Bull Regime: 188 candles")
            # Note: These logs are per batch, so we sum them up to get a relative distribution weight
            if "DEBUG:" in line and "Regime:" in line and "candles" in line:
                match = re.search(r"DEBUG: (\w+) Regime: (\d+) candles", line)
                if match:
                    regime = match.group(1)
                    count = int(match.group(2))
                    regime_counts[regime] += count

            # Parse Strategy Signals (from logs like "DEBUG: Bull Strategy Signals: 54")
            if "DEBUG:" in line and "Strategy" in line and "Signals" in line:
                match = re.search(r"DEBUG: (\w+) Strategy.*: (\d+)", line)
                if match:
                    strat = match.group(1)
                    count = int(match.group(2))
                    strategy_signals[strat] += count

            # Long specific for Range
            if "DEBUG:" in line and "Range Strategy Entry" in line:
                match = re.search(r"DEBUG: Range Strategy Entry (\w+): (\d+)", line)
                if match:
                    side = match.group(1)
                    count = int(match.group(2))
                    strategy_signals[f"Range_{side}"] += count

            # Parse Confirmed Trades
            if "DEBUG: Trade Entry Confirmed!" in line:
                # Format: DEBUG: Trade Entry Confirmed! DUSK/USDT:USDT long bull_wma
                match = re.search(
                    r"DEBUG: Trade Entry Confirmed! (\S+) (\S+) (\S+)", line
                )
                if match:
                    trade_info = {
                        "pair": match.group(1),
                        "side": match.group(2),
                        "tag": match.group(3),
                    }
                    confirmed_trades.append(trade_info)

    # --- REPORT GENERATION ---
    print("\n" + "=" * 50)
    print("       REGIME-AWARE ORCHESTRATOR REPORT")
    print("=" * 50 + "\n")

    # 1. Regime Distribution
    total_candles = sum(regime_counts.values())
    print(f"--- Market Regime Distribution (Candle Weight) ---")
    if total_candles > 0:
        for regime, count in regime_counts.items():
            pct = (count / total_candles) * 100
            print(f"{regime:<10}: {pct:>6.1f}% ({count} candle blocks)")
    else:
        print("No regime data found in logs.")

    # 2. Strategy Signal Generation (Opportunity Flow)
    print(f"\n--- Strategy Signal Generation (Potential Enries) ---")
    print(f"(How many times did each sub-strategy say 'GO'?)")
    for strat, count in strategy_signals.items():
        print(f"{strat:<15}: {count} signals")

    # 3. Executed Trades (The Filtered Reality)
    print(f"\n--- Executed Trades (Passed All Checks) ---")
    if confirmed_trades:
        for i, t in enumerate(confirmed_trades, 1):
            print(f"{i}. {t['pair']} ({t['side']}) via {t['tag']}")
    else:
        print("No trades executed.")

    print("\n" + "=" * 50)


if __name__ == "__main__":
    analyze_log()
