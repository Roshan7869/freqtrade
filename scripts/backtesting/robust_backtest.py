import json
import subprocess
import sys
import os
import argparse
from datetime import datetime


def run_backtest(
    strategy_name,
    timeframe_override=None,
    timerange="20250128-",
    pairs="SOL/USDT:USDT",
):
    print(f"----------------------------------------------------------------")
    print(f"Starting Backtest: {strategy_name}")
    print(f"Timerange: {timerange}")
    print(f"Pairs: {pairs}")
    print(f"----------------------------------------------------------------")

    cmd = [
        "docker-compose",
        "-f",
        "infrastructure/docker-compose.backtest.yml",
        "run",
        "--rm",
        "freqtrade-backtest",
        "backtesting",
        "--config",
        "/freqtrade/user_data/config_backtest.json",
        "--strategy",
        strategy_name,
        "--timerange",
        timerange,
        "--pairs",
        pairs,
        "--export",
        "trades",
    ]

    if timeframe_override:
        cmd.extend(["--timeframe", timeframe_override])

    try:
        # We capture output to check for crashing errors, but also stream it to user
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        process = subprocess.Popen(
            cmd,
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            text=True,
            encoding="utf-8",
            errors="replace",  # Handle encoding issues safely
        )

        full_log = []
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                print(line.rstrip())
                full_log.append(line)

        return_code = process.poll()

        # Simple heuristic to detect if it "crashed" vs "finished with 0 trades"
        log_content = "".join(full_log)
        if "KeyError" in log_content or "Traceback" in log_content:
            return "CRASH", log_content

        if return_code == 0:
            return "SUCCESS", log_content
        else:
            return "FAILURE", log_content

    except Exception as e:
        return "ERROR", str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", help="Specific strategy to run")
    parser.add_argument("--timerange", default="20250128-", help="Backtest timerange")
    parser.add_argument(
        "--pairs", default="SOL/USDT:USDT", help="Pairs to backtest (comma separated)"
    )
    args = parser.parse_args()

    # Load list of strategies if not specified
    if args.strategy:
        strategies_to_run = [s.strip() for s in args.strategy.split(",")]
    else:
        # Load from the requirements file to get all known strategies
        try:
            with open("strategy_requirements.json", "r") as f:
                requirements = json.load(f)
                strategies_to_run = list(requirements.keys())
        except:
            print("Please run analyze_strategy_requirements.py first")
            sys.exit(1)

    summary_results = []

    for strategy in strategies_to_run:
        status, log = run_backtest(strategy, timerange=args.timerange, pairs=args.pairs)

        # Extract profit if success
        profit = "N/A"
        if status == "SUCCESS":
            # Very basic parsing of the summary table at the end
            # "Tot Profit %       | 16.81"
            for line in reversed(log.splitlines()):  # Read from end
                if "Tot Profit %" in line:
                    # Example line: │ AroonMomentumStrategy │ 8 │ 10.02 │ 184.898 │ 16.81 │ ...
                    parts = line.split("│")
                    if len(parts) > 5:
                        profit = parts[5].strip() + "%"
                        break

        summary_results.append(
            {"strategy": strategy, "status": status, "profit": profit}
        )

    # Print Summary Table
    print("\n\n================================================================")
    print("ROBUST SYSTEM BACKTEST REPORT")
    print("================================================================")
    print(f"{'Strategy':<40} | {'Status':<10} | {'Profit':<10}")
    print("-" * 65)
    for res in summary_results:
        print(f"{res['strategy']:<40} | {res['status']:<10} | {res['profit']:<10}")
    print("================================================================")


if __name__ == "__main__":
    main()
