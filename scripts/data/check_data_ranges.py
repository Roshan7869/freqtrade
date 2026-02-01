import pandas as pd
import os

data_dir = r"user_data/data/binance/futures"
pairs = ["DUSK_USDT_USDT", "XRP_USDT_USDT", "DOGE_USDT_USDT"]
timeframe = "1h"

print(f"{'Pair':<20} | {'Start':<20} | {'End':<20} | {'Rows':<5}")
print("-" * 75)

overall_start = None
overall_end = None

for pair in pairs:
    filename = f"{pair}-{timeframe}-futures.feather"
    filepath = os.path.join(data_dir, filename)

    if os.path.exists(filepath):
        try:
            df = pd.read_feather(filepath)
            start = df["date"].min()
            end = df["date"].max()
            print(f"{pair:<20} | {str(start):<20} | {str(end):<20} | {len(df):<5}")

            if overall_start is None or start > overall_start:
                overall_start = start
            if overall_end is None or end < overall_end:
                overall_end = end

        except Exception as e:
            print(f"{pair:<20} | Error: {e}")
    else:
        print(f"{pair:<20} | File Not Found")

print("-" * 75)
if overall_start and overall_end:
    print(f"Max Common Range: {overall_start} to {overall_end}")
    # Format for freqtrade: YYYYMMDD-YYYYMMDD
    ft_start = overall_start.strftime("%Y%m%d")
    ft_end = overall_end.strftime("%Y%m%d")
    print(f"Freqtrade Timerange: {ft_start}-{ft_end}")
