import json
from datetime import datetime, timezone
from pathlib import Path


def summarize_momentum():
    # Use the most recent full backtest result
    result_file = (
        "user_data/backtest_results/temp_scan/backtest-result-2026-01-28_05-48-12.json"
    )
    if not Path(result_file).exists():
        print("Recent scan result not found.")
        return

    with open(result_file, "r") as f:
        data = json.load(f)

    trades = data.get("strategy", {}).get("AroonMACDStrategy", {}).get("trades", [])

    now = datetime.fromisoformat("2026-01-28T05:48:00+00:00")  # Based on file timestamp

    # Track latest entry per pair
    latest_per_pair = {}
    for t in trades:
        pair = t["pair"].split("/")[0]
        entry_time = datetime.fromisoformat(t["open_date"].replace(" ", "T"))
        if pair not in latest_per_pair or entry_time > latest_per_pair[pair]["time"]:
            latest_per_pair[pair] = {
                "time": entry_time,
                "side": t["enter_tag"],
                "profit": t["profit_ratio"] * 100,
            }

    print("--- LATEST SIGNAL AGE & MOMENTUM ---")
    print(
        f"{'TOKEN':<15} | {'LAST ENTRY':<15} | {'HOURS AGO':<10} | {'MOMENTUM STATUS'}"
    )
    print("-" * 65)

    sorted_pairs = sorted(
        latest_per_pair.items(), key=lambda x: x[1]["time"], reverse=True
    )

    for pair, info in sorted_pairs:
        hours_ago = (now - info["time"]).total_seconds() / 3600

        status = "EXHAUSTED"
        if hours_ago < 4:
            status = "HOT (Just Entered)"
        elif hours_ago < 12:
            status = "ACTIVE (Trend in Play)"
        elif hours_ago < 24:
            status = "COOLING"

        print(
            f"{pair:<15} | {info['time'].strftime('%H:%M'):<15} | {hours_ago:<10.1f} | {status}"
        )


if __name__ == "__main__":
    summarize_momentum()
