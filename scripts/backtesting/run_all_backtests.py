"""
Comprehensive Backtest Runner - All 24 Strategies
Runs sequentially and captures results to markdown report
"""

import subprocess
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

# All 24 strategies with correct timeframes
STRATEGIES = [
    ("DAVEY_01_EURO_NIGHT_ADAPTED", "2h"),
    ("DAVEY_02_EURO_DAY_ADAPTED", "1h"),
    ("DAVEY_03_WC_2005_DAILY", "1d"),
    ("ForestKnight_VPE_Strategy", "1h"),
    ("Stockbee_EP_Strategy", "5m"),
    ("ChrisVerma_GapShort_Strategy", "5m"),
    ("QuantTactics_Supertrend_Strategy", "1h"),
    ("QuantTactics_DCA_RSI_Strategy", "30m"),
    ("MarcoAcetoni_LiquidityTrap_Strategy", "5m"),
    ("ALMA_MACDStrategy", "1h"),
    ("AroonMACDStrategy", "1h"),
    ("AwesomeMACDRSIStrategy", "1h"),
    ("Donchian_ADX_CHOPStrategy", "1h"),
    ("EdriExtremePointsStrategy", "1h"),
    ("LLM_Regime_Strategy", "1h"),
    ("MeanReversionBBStrategy", "1h"),
    ("MeanReversionSqueezeStrategy", "1h"),
    ("TEMA_ADX_CMOStrategy", "1h"),
    ("UnifiedTrendStrategy", "1h"),
    ("VWAPDMIStrategy", "1h"),
    ("WMA_MACDStrategy", "1h"),
    ("WhaleMomentumStrategy", "1h"),
    ("WilliamsRSI_MACDStrategy", "1h"),
    ("StrategyOrchestratorStrategy", "1h"),
]

end = datetime.now()
start = end - timedelta(days=120)
timerange = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"

results = []


def extract_key_metrics(output):
    """Extract key metrics from backtest output"""
    metrics = {
        "trades": 0,
        "win_rate": 0.0,
        "profit_pct": 0.0,
        "profit_abs": 0.0,
        "max_dd": 0.0,
        "avg_duration": "0:00",
        "sharpe": 0.0,
    }

    try:
        # Total trades
        match = re.search(r"Total/Daily Avg Trades\s+\|\s+(\d+)", output)
        if match:
            metrics["trades"] = int(match.group(1))

        # Win rate (from TOTAL row in summary)
        match = re.search(
            r"TOTAL\s+\|\s+\d+\s+\|\s+[-\d.]+\s+\|\s+[-\d.]+\s+\|\s+([-\d.]+)", output
        )
        if match:
            metrics["profit_pct"] = float(match.group(1))

        # Absolute profit
        match = re.search(r"Absolute profit\s+\|\s+([-\d.]+)\s+USDT", output)
        if match:
            metrics["profit_abs"] = float(match.group(1))

        # Max Drawdown
        match = re.search(
            r"Absolute drawdown\s+\|\s+[-\d.]+\s+USDT\s+\(([-\d.]+)%\)", output
        )
        if match:
            metrics["max_dd"] = float(match.group(1))

        # Sharpe
        match = re.search(r"Sharpe\s+\|\s+([-\d.]+)", output)
        if match:
            metrics["sharpe"] = float(match.group(1))

        # Win rate from strategy summary
        match = re.search(
            r"Win\s+Draw\s+Loss\s+Win%\s+\|\s+\d+\s+\d+\s+\d+\s+([\d.]+)", output
        )
        if match:
            metrics["win_rate"] = float(match.group(1))

    except Exception as e:
        print(f"  Warning: Error extracting metrics: {e}")

    return metrics


print("=" * 80)
print(" COMPREHENSIVE BACKTEST - ALL 24 STRATEGIES")
print(f" Timerange: {timerange}")
print(f" Pairs: SOL/USDT, XRP/USDT, DOGE/USDT")
print(f" Leverage: 18x (configured in config.json)")
print("=" * 80)

for i, (strategy, timeframe) in enumerate(STRATEGIES, 1):
    print(f"\n[{i}/24] Testing {strategy} ({timeframe})...")

    cmd = [
        "docker",
        "exec",
        "freqtrade",
        "freqtrade",
        "backtesting",
        "--strategy",
        strategy,
        "--timeframe",
        timeframe,
        "--timerange",
        timerange,
        "--config",
        "/freqtrade/user_data/config.json",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode == 0:
            metrics = extract_key_metrics(result.stdout)
            metrics["strategy"] = strategy
            metrics["timeframe"] = timeframe
            metrics["status"] = "SUCCESS"
            results.append(metrics)

            print(
                f"  OK - Trades: {metrics['trades']}, Profit: {metrics['profit_pct']:.2f}%, Win: {metrics['win_rate']:.1f}%"
            )
        else:
            print(f"  FAILED - {result.stderr[:100]}")
            results.append(
                {
                    "strategy": strategy,
                    "timeframe": timeframe,
                    "status": "FAILED",
                    "trades": 0,
                    "profit_pct": 0,
                    "win_rate": 0,
                }
            )
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT")
        results.append(
            {
                "strategy": strategy,
                "timeframe": timeframe,
                "status": "TIMEOUT",
                "trades": 0,
            }
        )
    except Exception as e:
        print(f"  ERROR - {str(e)[:100]}")
        results.append(
            {
                "strategy": strategy,
                "timeframe": timeframe,
                "status": "ERROR",
                "trades": 0,
            }
        )

# Generate Report
print("\n" + "=" * 80)
print(" GENERATING REPORT...")
print("=" * 80)

report_path = r"c:\Users\USER\Desktop\Algotrading\BACKTEST_RESULTS_FINAL.md"

# Sort by profit
successful = [r for r in results if r.get("status") == "SUCCESS"]
successful.sort(key=lambda x: x.get("profit_pct", -9999), reverse=True)

with open(report_path, "w", encoding="utf-8") as f:
    f.write("# Comprehensive Backtest Results\n\n")
    f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    f.write(f"**Timerange**: {timerange} (120 days)\n")
    f.write(f"**Pairs**: SOL/USDT, XRP/USDT, DOGE/USDT\n")
    f.write(f"**Leverage**: 18x\n\n")
    f.write("---\n\n")

    # Top performers
    f.write("## TOP 10 PERFORMERS\n\n")
    f.write("| Rank | Strategy | TF | Trades | Win% | Profit% | Max DD% | Sharpe |\n")
    f.write("|------|----------|----|----|------|---------|---------|--------|\n")

    for i, r in enumerate(successful[:10], 1):
        f.write(
            f"| {i} | {r['strategy'][:35]} | {r['timeframe']} | "
            f"{r['trades']} | {r.get('win_rate', 0):.1f} | "
            f"**{r['profit_pct']:.2f}** | {r.get('max_dd', 0):.2f} | "
            f"{r.get('sharpe', 0):.2f} |\n"
        )

    f.write("\n## COMPLETE RESULTS\n\n")
    f.write("| # | Strategy | TF | Status | Trades | Profit% | Win% |\n")
    f.write("|---|----------|----|----|-----|---------|------|\n")

    for i, r in enumerate(results, 1):
        status_icon = "OK" if r.get("status") == "SUCCESS" else "FAIL"
        f.write(
            f"| {i} | {r['strategy'][:35]} | {r['timeframe']} | {status_icon} | "
            f"{r.get('trades', 0)} | {r.get('profit_pct', 0):.2f} | "
            f"{r.get('win_rate', 0):.1f} |\n"
        )

    f.write("\n## SUMMARY\n\n")
    f.write(f"- Total Strategies Tested: {len(results)}\n")
    f.write(f"- Successful: {len(successful)}\n")
    f.write(f"- Failed: {len(results) - len(successful)}\n")

    active = [r for r in successful if r["trades"] > 0]
    f.write(f"- Strategies with Trades: {len(active)}\n")

    profitable = [r for r in successful if r.get("profit_pct", 0) > 0]
    f.write(f"- Profitable Strategies: {len(profitable)}\n\n")

    if profitable:
        best = profitable[0]
        f.write(
            f"**Best Performer**: {best['strategy']} ({best['profit_pct']:.2f}%)\n\n"
        )

    f.write("---\n\n")
    f.write("## RECOMMENDATIONS\n\n")

    if len(active) < 5:
        f.write("**Market Condition**: Ranging/Choppy (low activity)\n\n")
        f.write("Most trend-following strategies avoided trading (correct behavior).\n")
        f.write("Consider:\n")
        f.write("- Using mean reversion strategies in current market\n")
        f.write("- Testing on earlier trending period (May-June 2025)\n")
        f.write("- Relaxing choppiness thresholds via hyperopt\n")
    else:
        f.write("Based on backtest results, recommended strategies:\n\n")
        for i, r in enumerate(profitable[:3], 1):
            f.write(
                f"{i}. **{r['strategy']}** - {r['profit_pct']:.2f}% profit, "
                f"{r['trades']} trades\n"
            )

print(f"\n\nREPORT SAVED: {report_path}")
print("\nSummary:")
print(f"  Tested: {len(results)} strategies")
print(f"  Successful: {len(successful)}")
print(f"  With Trades: {len([r for r in successful if r['trades'] > 0])}")
print(f"  Profitable: {len([r for r in successful if r.get('profit_pct', 0) > 0])}")

print("\n" + "=" * 80)
print(" BACKTEST COMPLETE")
print("=" * 80)
