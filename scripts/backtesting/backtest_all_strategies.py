"""
Backtest All Strategies Script
===============================
Runs backtests for all 15 Quant Tactics strategies on SOL/USDT
"""

import subprocess
import json
from datetime import datetime

# List of all strategies
STRATEGIES = [
    "RSIDCAMomentumScalerStrategy",
    "ALMAMACDMomentumCrossStrategy",
    "TripleMAStrategy",
    "RSISMAMomentumStrategy",
    "SupertrendEMAMomentumStrategy",
    "StochasticMomentumDipBuyerStrategy",
    "ParabolicSARMomentumStrategy",
    "MomentumBreakoutStrategy",
    "DualCCIPullbackStrategy",
    "IchimokuCloudTrendStrategy",
    "FibonacciEMATrendStrategy",
    "EMA8_13_21_MACDStrategy",
    "ADXSMAChannelStrategy",
    "ADXOBVMomentumStrategy",
    "AroonMomentumStrategy",
]

# Timerange: 8 months (May 23, 2025 to Jan 23, 2026)
TIMERANGE = "20250523-20260123"
PAIR = "SOL/USDT:USDT"

results = []

print(f"Starting backtest for {len(STRATEGIES)} strategies on {PAIR}")
print(f"Timerange: {TIMERANGE}")
print(f"Leverage: 12x")
print("=" * 80)

for i, strategy in enumerate(STRATEGIES, 1):
    print(f"\n[{i}/{len(STRATEGIES)}] Backtesting {strategy}...")

    cmd = [
        "docker-compose",
        "-f",
        "infrastructure/docker-compose.backtest.yml",
        "run",
        "--rm",
        "freqtrade-backtest",
        "backtesting",
        "--strategy",
        strategy,
        "--timerange",
        TIMERANGE,
        "--export",
        "trades",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd="c:/Users/USER/Desktop/Algotrading",
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout per strategy
        )

        if result.returncode == 0:
            print(f"✓ {strategy} completed successfully")
            results.append({"strategy": strategy, "status": "success"})
        else:
            print(f"✗ {strategy} failed")
            print(f"Error: {result.stderr[:200]}")
            results.append(
                {"strategy": strategy, "status": "failed", "error": result.stderr[:200]}
            )

    except subprocess.TimeoutExpired:
        print(f"✗ {strategy} timed out")
        results.append({"strategy": strategy, "status": "timeout"})
    except Exception as e:
        print(f"✗ {strategy} error: {str(e)}")
        results.append({"strategy": strategy, "status": "error", "error": str(e)})

print("\n" + "=" * 80)
print("BACKTEST SUMMARY")
print("=" * 80)

successful = sum(1 for r in results if r["status"] == "success")
failed = len(results) - successful

print(f"Total: {len(results)}")
print(f"Successful: {successful}")
print(f"Failed: {failed}")

# Save results
with open("backtest_results_summary.json", "w") as f:
    json.dump(
        {
            "timestamp": datetime.now().isoformat(),
            "pair": PAIR,
            "timerange": TIMERANGE,
            "leverage": 12,
            "results": results,
        },
        f,
        indent=2,
    )

print(f"\nResults saved to backtest_results_summary.json")
print("\nRun 'python scripts/analyze_trades.py' to analyze detailed results")
