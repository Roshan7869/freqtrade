import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path


def get_strategies():
    try:
        with open("strategy_requirements.json", "r") as f:
            requirements = json.load(f)
            return list(requirements.keys())
    except FileNotFoundError:
        print(
            "strategy_requirements.json not found. Run analyze_strategy_requirements.py first."
        )
        sys.exit(1)


def generate_time_chunks(start_date, end_date, chunk_days=30):
    """Generates (start_str, end_str) tuples for freqtrade timerange."""
    current_start = start_date
    chunks = []

    while current_start < end_date:
        current_end = current_start + datetime.timedelta(days=chunk_days)
        if current_end > end_date:
            current_end = end_date

        # Freqtrade format YYYYMMDD-YYYYMMDD
        # Note: Freqtrade ensures inclusive start, exclusive end logic usually,
        # or inclusive-inclusive depending on implementation.
        # But standard is YYYYMMDD-YYYYMMDD

        # To avoid gaps/overlaps, we handle dates carefully.
        # Freqtrade usually treats end date as inclusive if timestamp is not provided?
        # Let's stringify.

        start_str = current_start.strftime("%Y%m%d")
        end_str = current_end.strftime("%Y%m%d")

        chunks.append(f"{start_str}-{end_str}")

        # Next chunk starts where this one left off?
        # Actually, usually better to start next day to avoid overlap?
        # But if we want continuous coverage...
        # Let's say 20250101-20250131. Next 20250131-20250302?
        # If we use strict dates, there might be overlap on the changeover day.
        # But for "months", simplistic is fine.

        current_start = current_end

    return chunks


def run_chunked_backtest(strategy, chunks, pairs):
    print(f"\n==================================================================")
    print(f"Running Chunked Backtest for: {strategy}")
    print(f"==================================================================\n")

    results = []

    for timerange in chunks:
        print(f"--> Testing Interval: {timerange}")

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
            strategy,
            "--timerange",
            timerange,
            "--pairs",
            pairs,
            "--export",
            "none",
        ]

        try:
            process = subprocess.Popen(
                cmd,
                cwd="c:/Users/USER/Desktop/Algotrading",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            # Capture output to find profit
            profit_pct = "N/A"
            profit_abs = "N/A"
            trades = "0"
            drawdown = "N/A"

            last_lines = []

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    # Optional: Print every line? Too spammy for multiple chunks.
                    # Just print status or key lines?
                    # let's only print warnings or errors, or final table
                    print(line.rstrip())
                    last_lines.append(line.rstrip())
                    # Keep buffer small
                    if len(last_lines) > 200:
                        last_lines.pop(0)

            # Parse results from output
            # Data row example: │ RSISMAMomentumStrategy │ 4 │ 2.38 │ 68.317 │ 6.83 │ ...
            for line in reversed(last_lines):
                if strategy in line and "│" in line:
                    parts = line.split("│")
                    if len(parts) > 5:
                        trades = parts[2].strip()
                        profit_abs = parts[4].strip()
                        profit_pct = parts[5].strip()

                if "Max Drawdown" in line and "Strategy" not in line:
                    parts = line.split("│")
                    if len(parts) > 2:
                        drawdown = parts[2].strip()

            print(
                f"    Result: Trades={trades}, Profit={profit_pct}%, Abs={profit_abs}, DD={drawdown}"
            )

            results.append(
                {
                    "timerange": timerange,
                    "trades": trades,
                    "profit_pct": profit_pct,
                    "profit_abs": profit_abs,
                    "drawdown": drawdown,
                }
            )

        except Exception as e:
            print(f"Error executing chunk {timerange}: {e}")

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", help="Specific strategy (or comma separated)")
    parser.add_argument("--days", type=int, default=30, help="Chunk size in days")
    parser.add_argument("--pairs", default="SOL/USDT:USDT", help="Pairs to backtest")

    args = parser.parse_args()

    start_date = datetime.datetime(2025, 1, 28)
    end_date = datetime.datetime(2026, 1, 28)  # Today or approximate data end

    chunks = generate_time_chunks(start_date, end_date, args.days)
    print(f"Generated {len(chunks)} chunks of {args.days} days.")

    strategies = []
    if args.strategy:
        strategies = [s.strip() for s in args.strategy.split(",")]
    else:
        strategies = get_strategies()
        # Limit to top/interesting strategies to avoid infinite run?
        # User said "my strategy", singular-ish.
        # I'll stick to running one if not specified, or fail?
        # No, better to pick a robust default or run all.
        # Running 40 strategies * 12 chunks = 480 runs.
        # That is too many for this turn.
        # I will revert to picking the first few or asking.
        # For now, let's take 'AroonMomentumStrategy' as default if None provided,
        # or just run the first 3.
        print("No strategy specified, selecting first 3 for demo...")
        strategies = strategies[:3]

    final_report = {}

    for strat in strategies:
        strat_results = run_chunked_backtest(strat, chunks, args.pairs)
        final_report[strat] = strat_results

    print("\n\n==================================================================")
    print("CHUNKED BACKTEST SUMMARY (Leverage 6x)")
    print("==================================================================")

    for strat, res_list in final_report.items():
        print(f"\nStrategy: {strat}")
        print(
            f"{'Period':<20} | {'Trades':<8} | {'Profit %':<10} | {'Profit $':<12} | {'Drawdown':<10}"
        )
        print("-" * 75)
        total_p_abs = 0.0
        for r in res_list:
            print(
                f"{r['timerange']:<20} | {r['trades']:<8} | {r['profit_pct']:<10} | {r['profit_abs']:<12} | {r['drawdown']:<10}"
            )
            try:
                total_p_abs += float(r["profit_abs"])
            except:
                pass
        print("-" * 75)
        print(f"{'TOTAL':<20} | {'':<8} | {'':<10} | {total_p_abs:<12.2f} |")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
