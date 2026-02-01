import pandas as pd
from pathlib import Path


def check_range(pair, suffix):
    path = Path(
        f"user_data/data/binance/futures/{pair.replace('/', '_').replace(':', '_')}-8h-{suffix}.feather"
    )
    if not path.exists():
        print(f"{pair} {suffix}: File not found")
        return
    df = pd.read_feather(path)
    print(f"{pair} {suffix}: {df['date'].min()} to {df['date'].max()} ({len(df)} rows)")


for p in ["SOL/USDT:USDT", "DOGE/USDT:USDT", "XRP/USDT:USDT"]:
    check_range(p, "funding_rate")
    check_range(p, "mark")
