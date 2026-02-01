"""
Scoring Engine Demo
===================
Simulates the entire flow:
1. Generate Mock Market State
2. Generate 100 Mock Strategies
3. Score and Optimize Portfolio
"""

import sys
import os
import random
import numpy as np

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
# src -> scoring -> decision_layer -> project_root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.insert(0, project_root)

from decision_layer.src.scoring.strategy_profile import StrategyProfile
from decision_layer.src.scoring.scoring_engine import StrategyScorer, PortfolioOptimizer


def generate_mock_strategies(count=100):
    strategies = []
    regimes = [
        ("Trend", [0.8, 0.4, 0.6, 0.5]),
        ("MeanRev", [0.2, 0.6, 0.5, 0.9]),
        ("Chop", [0.1, 0.2, 0.3, 0.5]),
        ("HighVol", [0.5, 0.9, 0.8, 0.5]),
    ]

    for i in range(count):
        regime_name, vector = random.choice(regimes)

        # Add some noise to vector
        noisy_vector = [
            min(1.0, max(0.0, v + random.uniform(-0.1, 0.1))) for v in vector
        ]

        strat = StrategyProfile(
            strategy_id=f"Strat_{i}_{regime_name}",
            ideal_regime_vector=noisy_vector,
            win_rate_last_50_trades=random.uniform(0.30, 0.70),
            sharpe_ratio_rolling=random.uniform(0.5, 2.5),
            max_drawdown_allowed=0.20,
            current_drawdown=random.uniform(0.0, 0.25),  # Some will be dead
            correlation_group=regime_name if random.random() > 0.5 else None,
        )
        strategies.append(strat)
    return strategies


def main():
    print("==========================================")
    print("STRATEGY SCORING ENGINE DEMO")
    print("==========================================")

    # 1. Define Current Market (e.g. Strong Bull Trend)
    # Trend=0.9, Vol=0.4, VolIntensity=0.7, MR=0.2
    market_vector = [0.9, 0.4, 0.7, 0.2]
    print(f"\nCurrent Market Vector: {market_vector}")
    print("(High Trend, Moderate Volatility)")

    # 2. Generate Strategies
    strategies = generate_mock_strategies(100)
    print(f"Generated {len(strategies)} strategies.")

    # 3. Optimize
    scorer = StrategyScorer()
    optimizer = PortfolioOptimizer(scorer)

    print("\nRunning Optimizer...")
    selected = optimizer.select_top_strategies(strategies, market_vector, top_n=3)

    print("\n==========================================")
    print("SELECTED PORTFOLIO")
    print("==========================================")

    for i, item in enumerate(selected):
        s = item["strategy"]
        score = item["score"]
        print(f"Rank {i + 1}: {s.strategy_id}")
        print(f"  > Score: {score:.4f}")
        print(f"  > Regime Vector: {[round(x, 2) for x in s.ideal_regime_vector]}")
        print(
            f"  > Performance: WR={s.win_rate_last_50_trades:.2f}, Sharpe={s.sharpe_ratio_rolling:.2f}"
        )
        print(f"  > Safety: DD={s.current_drawdown:.2f}/{s.max_drawdown_allowed:.2f}")
        print("------------------------------------------")


if __name__ == "__main__":
    main()
