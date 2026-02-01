import requests
import json


def get_binance_futures_stats():
    # Binance Futures ticker info
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    try:
        response = requests.get(url)
        response.raise_for_status()
        tickers = response.json()
    except Exception as e:
        print(f"Error fetching data: {e}")
        return

    # Filter for USDT pairs only to keep it simple and relevant
    usdt_tickers = [t for t in tickers if t["symbol"].endswith("USDT")]

    # Sort by price change percentage
    gainers = sorted(
        usdt_tickers, key=lambda x: float(x["priceChangePercent"]), reverse=True
    )[:10]
    losers = sorted(usdt_tickers, key=lambda x: float(x["priceChangePercent"]))[:10]

    # Sort by volume (quoteVolume is USDT volume)
    volume = sorted(usdt_tickers, key=lambda x: float(x["quoteVolume"]), reverse=True)[
        :10
    ]

    print("\n--- TOP 10 GAINERS ---")
    for t in gainers:
        print(f"{t['symbol']}: {t['priceChangePercent']}%")

    print("\n--- TOP 10 LOSERS ---")
    for t in losers:
        print(f"{t['symbol']}: {t['priceChangePercent']}%")

    print("\n--- TOP 10 VOLUME ---")
    for t in volume:
        print(f"{t['symbol']}: {t['quoteVolume']} USDT")

    # Filter problematic pairs
    excluded = {
        "FOGO",
        "XAU",
        "XAG",
        "AMB",
        "BAKE",
        "TROY",
        "MEMEFI",
        "VIDT",
        "ALPACA",
        "SKATE",
        "NEIROETH",
    }

    # Combine unique symbols
    all_symbols = set()
    for t in gainers + losers + volume:
        sym = t["symbol"].replace("USDT", "")
        if sym not in excluded:
            all_symbols.add(t["symbol"])

    # Convert to Freqtrade pair format: BTC/USDT:USDT
    formatted_pairs = []
    for s in all_symbols:
        base = s.replace("USDT", "")
        formatted_pairs.append(f"{base}/USDT:USDT")

    print("\nAll Unique Pairs (formatted for freqtrade):")
    print(",".join(formatted_pairs))

    # Save to a file for the next step
    with open("market_scan_pairs.txt", "w") as f:
        f.write(",".join(formatted_pairs))


if __name__ == "__main__":
    get_binance_futures_stats()
