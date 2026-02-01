import json
import subprocess
import sys


def main():
    # Load requirements
    try:
        with open("strategy_requirements.json", "r") as f:
            requirements = json.load(f)
    except FileNotFoundError:
        print(
            "Error: strategy_requirements.json not found. Run analyze_strategy_requirements.py first."
        )
        sys.exit(1)

    # Aggregate unique timeframes
    all_timeframes = set()
    for strat, tfs in requirements.items():
        all_timeframes.update(tfs)

    # Ensure standards exist
    all_timeframes.add("1d")  # Always useful

    sorted_tfs = sorted(list(all_timeframes))
    print(f"Required Timeframes: {sorted_tfs}")

    # Configuration
    PAIR = "SOL/USDT:USDT"  # Could be dynamic, but fixed for this request
    TIMERANGE = "20250128-"  # 1 Year

    print(f"Downloading data for {PAIR}...")

    # Construct Docker command
    cmd = [
        "docker-compose",
        "-f",
        "infrastructure/docker-compose.backtest.yml",
        "run",
        "--rm",
        "freqtrade-backtest",
        "download-data",
        "--pairs",
        PAIR,
        "--timerange",
        TIMERANGE,
        "--timeframes",
        *sorted_tfs,
        "--prepend",
    ]

    try:
        subprocess.check_call(cmd, cwd="c:/Users/USER/Desktop/Algotrading")
        print("Data download completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Data download failed with code {e.returncode}")
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()
