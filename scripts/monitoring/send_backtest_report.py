import json
import os
import sys
import requests
import glob
import zipfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

CONFIG_PATH = Path("user_data/config.json")


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}


def send_telegram_report(message):
    config = load_config()
    telegram_config = config.get("telegram", {})

    token = telegram_config.get("token")
    chat_id = telegram_config.get("chat_id")

    if not token or not chat_id:
        print("Telegram not configured")
        return

    print(f"Sending to Chat ID: {chat_id}")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("Telegram message sent successfully!")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")


def get_latest_results():
    results_dir = Path("user_data/backtest_results")

    # Try finding the designated output file first
    manual_file = results_dir / "backtest_result.json"
    if manual_file.exists():
        return manual_file

    # Fallback: Find latest zip and extract
    files = list(results_dir.glob("backtest-result-*.zip"))
    if not files:
        return None

    latest_zip = max(files, key=os.path.getmtime)
    print(f"Extracting from latest zip: {latest_zip.name}")

    try:
        with zipfile.ZipFile(latest_zip, "r") as z:
            # Find the main json report inside
            # usually named like backtest-result-YYYY-MM-DD_HH-mm-ss.json
            for name in z.namelist():
                if name.endswith(".json") and not name.endswith(".meta.json"):
                    z.extract(name, results_dir)
                    return results_dir / name
    except Exception as e:
        print(f"Error unzipping: {e}")
        return None

    return None


def parse_and_send_results():
    latest_file = get_latest_results()

    if not latest_file:
        print("No backtest results found (json or zip).")
        return

    print(f"Processing result file: {latest_file}")

    try:
        with open(latest_file, "r") as f:
            data = json.load(f)

        msg = "📊 <b>Backtest Results Report</b> 📊\n\n"

        # Check if 'strategy' key exists (standard format)
        strategies = data.get("strategy", {})

        # If empty, might be comparison format
        if not strategies and "strategy_comparison" in data:
            for item in data["strategy_comparison"]:
                strategies.update(item)

        total_profit_usd = 0

        for strat_name, stats in strategies.items():
            wins = stats.get("wins", 0)
            draws = stats.get("draws", 0)
            losses = stats.get("losses", 0)
            total = stats.get("total_trades", 0)
            winrate = stats.get("win_rate", 0)
            profit_pct = stats.get("profit_total_pct", 0)
            profit_abs = stats.get("profit_total_abs", 0)
            drawdown = stats.get("max_drawdown", 0)

            total_profit_usd += profit_abs

            msg += f"Strategy: <b>{strat_name}</b>\n"
            msg += f"🗓️ Period: {data.get('timerange', 'Unknown')}\n"
            msg += f"💰 Profit: <b>{profit_abs:.2f} USDT</b> ({profit_pct:.2f}%)\n"
            msg += f"🔢 Trades: {total} (W:{wins} L:{losses})\n"
            msg += f"✅ Win Rate: {winrate:.2%}\n"
            msg += f"📉 Max Drawdown: {drawdown:.2%}\n"
            msg += "--------------------------------\n"

        if not strategies:
            msg += "⚠️ No trades executed or strategy metrics missing."

        send_telegram_report(msg)

    except Exception as e:
        print(f"Error parsing results: {e}")
        send_telegram_report(f"⚠️ Backtest executed but report generation failed: {e}")


if __name__ == "__main__":
    parse_and_send_results()
