import json
import os
from collections import defaultdict


def analyze_performance_and_select_champions():
    """
    Reads strategy_performance_db.json, ranks strategies by regime,
    and selects the best one for 'TRENDING_BULL', 'TRENDING_BEAR', and 'RANGING'.
    Outputs the result to user_data/best_strategies.json.
    """

    # Paths
    db_path = "user_data/strategy_performance_db.json"
    output_path = "user_data/best_strategies.json"

    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    strategies = data.get("strategies", {})

    # Containers to hold candidates for each regime
    # Structure: regime -> list of (strategy_name, profit_pct, win_rate, trades)
    candidates = defaultdict(list)

    target_regimes = ["TRENDING_BULL", "TRENDING_BEAR", "RANGING"]

    print(f"Analyzing {len(strategies)} strategies for regimes: {target_regimes}...")

    for strat_name, strat_data in strategies.items():
        by_regime = strat_data.get("by_regime", {})

        for regime in target_regimes:
            if regime in by_regime:
                metrics = by_regime[regime].get("metrics", {})
                profit = metrics.get("profit_total_pct", -999)
                trades = metrics.get("total_trades", 0)
                win_rate = metrics.get("win_rate", 0)

                # Filter: Must have minimal activity to be considered "Reliable"
                # For Bear markets, maybe fewer trades are okay, but let's say at least 2
                if trades >= 2:
                    candidates[regime].append(
                        {
                            "name": strat_name,
                            "profit": profit,
                            "trades": trades,
                            "win_rate": win_rate,
                        }
                    )

    # Select Champions
    champions = {}

    for regime in target_regimes:
        regime_candidates = candidates[regime]

        if not regime_candidates:
            print(f"Warning: No valid candidates found for {regime}")
            champions[regime] = None
            continue

        # Sort by Profit primarily
        # We could also use a combined score, but for now Profit is King
        sorted_candidates = sorted(
            regime_candidates, key=lambda x: x["profit"], reverse=True
        )

        best = sorted_candidates[0]
        print(f"Reviewing Candidates for {regime}:")
        for c in sorted_candidates[:3]:  # Show top 3
            print(f"  - {c['name']}: {c['profit']:.2f}% ({c['trades']} trades)")

        champions[regime] = best["name"]
        print(f"CHAMPION for {regime}: {best['name']} ({best['profit']:.2f}%)\n")

    # Save to file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(champions, f, indent=4)

    print(f"Saved champions to {output_path}")


if __name__ == "__main__":
    analyze_performance_and_select_champions()
