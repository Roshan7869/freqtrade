"""
Comprehensive Backtest Runner - 10 Month SOL/USDT Analysis
Runs 24 strategies on 300 days of data using stable Docker containers
"""

import subprocess
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
DAYS = 300
PAIR = "SOL/USDT:USDT"  # Specific pair requested
TIMERANGE = getattr(datetime.now() - timedelta(days=DAYS), "strftime")("%Y%m%d") + "-"

# Strategies
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

results = []


def run_backtest(strategy, timeframe):
    print(f"\nTesting {strategy} ({timeframe})...")

    # Use docker run for stability/isolation
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{Path.cwd()}/user_data:/freqtrade/user_data",
        "freqtradeorg/freqtrade:stable",
        "backtesting",
        "--strategy",
        strategy,
        "--timeframe",
        timeframe,
        "--timerange",
        TIMERANGE,
        "--config",
        "/freqtrade/user_data/config.json",
        "--pairs",
        PAIR,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1200,  # 20 min per strategy limit
        )
        return result.stdout, result.stderr
    except Exception as e:
        print(f"Error: {e}")
        return "", str(e)


def extract_metrics(output, stderr, strategy, timeframe):
    metrics = {
        "strategy": strategy,
        "timeframe": timeframe,
        "status": "FAILED",
        "trades": 0,
        "profit_pct": 0.0,
        "win_rate": 0.0,
        "max_dd": 0.0,
        "sharpe": 0.0,
        "profit_abs": 0.0,
        "error": "",
    }

    if "Exit code: 0" in output:
        metrics["status"] = "SUCCESS"

        # Trades
        if m := re.search(r"Total/Daily Avg Trades\s+\|\s+(\d+)", output):
            metrics["trades"] = int(m.group(1))

        # Profit %
        if m := re.search(
            r"TOTAL\s+\|\s+\d+\s+\|\s+[-\d.]+\s+\|\s+[-\d.]+\s+\|\s+([-\d.]+)", output
        ):
            metrics["profit_pct"] = float(m.group(1))

        # Win Rate
        if m := re.search(
            r"Win\s+Draw\s+Loss\s+Win%\s+\|\s+\d+\s+\d+\s+\d+\s+([\d.]+)", output
        ):
            metrics["win_rate"] = float(m.group(1))

        # Max DD
        if m := re.search(
            r"Absolute drawdown\s+\|\s+[-\d.]+\s+USDT\s+\(([-\d.]+)%\)", output
        ):
            metrics["max_dd"] = float(m.group(1))

        # Sharpe
        if m := re.search(r"Sharpe\s+\|\s+([-\d.]+)", output):
            metrics["sharpe"] = float(m.group(1))
    else:
        # Capture error
        if "No module named" in output:
            metrics["error"] = "Missing Dependency"
        elif "Impossible to load Strategy" in output:
            metrics["error"] = "Load Error"
            # Look for specific error lines
            for line in output.splitlines():
                if "ERROR" in line:
                    print(f"   [!] {line[:100]}...")
        else:
            metrics["error"] = "Runtime Error"

    return metrics


def generate_report(results_list):
    successful = [r for r in results_list if r["status"] == "SUCCESS"]
    successful.sort(key=lambda x: x["profit_pct"], reverse=True)

    report_path = Path.cwd() / "SOLANA_10MONTH_RESULTS.md"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Solana 10-Month Strategy Ranking\n\n")
        f.write(f"**Period**: Last 300 Days\n")
        f.write(f"**Pair**: {PAIR}\n")
        f.write(f"**Total Strategies**: {len(results_list)}\n\n")

        f.write("## Top Performers\n\n")
        f.write("| Rank | Strategy | Trades | Profit % | Win % | Max DD % | Sharpe |\n")
        f.write("|------|----------|--------|----------|-------|----------|--------|\n")

        for i, r in enumerate(successful, 1):
            profit_str = (
                f"**{r['profit_pct']:.2f}%**"
                if r["profit_pct"] > 0
                else f"{r['profit_pct']:.2f}%"
            )
            f.write(
                f"| {i} | {r['strategy'][:30]} | {r['trades']} | {profit_str} | {r['win_rate']:.1f}% | {r['max_dd']:.2f}% | {r['sharpe']:.2f} |\n"
            )

    print(f"\nReport generated: {report_path}")


def main():
    print("=" * 60)
    print(f" SOLANA 10-MONTH BACKTEST MARATHON")
    print(f" Target: {PAIR} for {DAYS} days")
    print("=" * 60)

    for i, (strat, tf) in enumerate(STRATEGIES, 1):
        print(f"[{i}/{len(STRATEGIES)}]", end=" ")
        output, stderr = run_backtest(strat, tf)
        m = extract_metrics(output, stderr, strat, tf)
        results.append(m)

        status = "OK" if m["status"] == "SUCCESS" else "FAIL"
        print(f"   [{status}] Trades: {m['trades']} | Profit: {m['profit_pct']:.2f}%")

    generate_report(results)


if __name__ == "__main__":
    main()
