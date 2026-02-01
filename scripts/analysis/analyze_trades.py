import json
import os
import sys
from pathlib import Path
from collections import defaultdict


def analyze_trades():
    results_dir = Path("user_data/backtest_results")

    # Find latest json result (excluding meta.json)
    files = list(results_dir.glob("backtest-result-*.json"))
    json_files = [f for f in files if not f.name.endswith(".meta.json")]

    if not json_files:
        print("No result file found.")
        return

    latest_file = max(json_files, key=os.path.getmtime)
    print(f"Analyzing: {latest_file.name}")

    with open(latest_file, "r") as f:
        data = json.load(f)

    trades = []
    # Check for direct trades list or inside strategy key
    if (
        "freqtrade-v1" in data
    ):  # new format? usually it's list of dicts or dict with strategy key
        # Depending on export format. The internal json has everything.
        pass

    # Standard backtest result structure
    # data['strategy']['StrategyOrchestratorStrategy']['trades'] usually contains the list

    strat_data = data.get("strategy", {}).get("StrategyOrchestratorStrategy", {})
    trades = strat_data.get("trades", [])

    if not trades:
        print("No trades found in the result file.")
        return

    print(f"Total Trades: {len(trades)}")

    strategy_counts = defaultdict(int)

    for trade in trades:
        # Our Orchestrator puts the tag as: orch_REGIME_tag
        # or sometimes just the tag from the child strategy if not properly prefixed
        tag = trade.get("enter_tag", "unknown")

        # Try to deduce strategy/regime from tag
        if "orch_" in tag:
            parts = tag.split("_")
            # format: orch_REGIME_...
            # e.g. orch_TRENDING_BULL_buy_signal
            if len(parts) >= 3:
                regime = (
                    f"{parts[1]}_{parts[2]}"
                    if parts[2] in ["BULL", "BEAR"]
                    else parts[1]
                )
                strategy_counts[regime] += 1
            else:
                strategy_counts[tag] += 1
        elif "llm_" in tag:  # LLM Strategy tags
            strategy_counts["LLM_Regime"] += 1
        else:
            strategy_counts[tag] += 1

    print("\nTrades by Strategy/Regime:")
    for strat, count in strategy_counts.items():
        print(f"  {strat}: {count}")


if __name__ == "__main__":
    analyze_trades()
