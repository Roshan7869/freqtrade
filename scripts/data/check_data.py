import pandas as pd
import glob
import os


def check_data_range():
    print("Checking feather file date ranges...")
    files = glob.glob("user_data/data/binance/futures/*-1h-futures.feather")

    for f in files:
        try:
            df = pd.read_feather(f)
            if "date" in df.columns:
                print(f"File: {os.path.basename(f)}")
                print(f"  Start: {df['date'].min()}")
                print(f"  End:   {df['date'].max()}")
                print(f"  Rows:  {len(df)}")
            else:
                print(f"File: {os.path.basename(f)} - 'date' column missing")
        except Exception as e:
            print(f"Error reading {f}: {e}")


if __name__ == "__main__":
    check_data_range()
