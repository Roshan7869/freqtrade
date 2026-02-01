import pandas as pd
from pathlib import Path


def check_range(pair):
    path = Path(
        f"user_data/data/binance/futures/{pair.replace('/', '_').replace(':', '_')}-1h-futures.feather"
    )
    if not path.exists():
        print(f"{pair}: File not found")
        return
    df = pd.read_feather(path)
    print(f"{pair}: {df['date'].min()} to {df['date'].max()} ({len(df)} rows)")


check_range("SOL/USDT:USDT")
check_range("DOGE/USDT:USDT")
check_range("XRP/USDT:USDT")
