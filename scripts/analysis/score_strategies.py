"""
Strategy Scoring Automation (Matrix Edition)
============================================
1. Fetches REAL-TIME market data (via CCXT) for Current Regime.
2. Loads ALL RECENT Backtest Results (aggregates ZIP/JSON).
3. Scores each strategy against MULTIPLE Regimes (Current, Trend, Chop, Shock).
4. Outputs a Suitability Matrix to guide selection.
"""

import os
import sys
import json
import logging
import zipfile
import pandas as pd
import ccxt

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from analysis_layer.src.market_quant import MarketQuantAnalyzer  # noqa: E402
from decision_layer.src.scoring.strategy_profile import StrategyProfile  # noqa: E402
from decision_layer.src.scoring.scoring_engine import StrategyScorer  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StrategyScorer")

RESULTS_DIR = os.path.join(project_root, "user_data", "backtest_results")


def get_current_market_data(pair="SOL/USDT", timeframe="5m", limit=100) -> pd.DataFrame:
    """Fetch recent OHLCV data from Binance (Public API)."""
    try:
        exchange = ccxt.binance()
        ohlcv = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        logger.error(f"Failed to fetch market data: {e}")
        return pd.DataFrame()


def load_recent_backtests(lookback_minutes=120) -> dict:
    """
    Aggregates backtest results from all JSON/ZIP files modified in the last N minutes.
    """
    aggregated_results = {"strategy": {}}

    try:
        # Find all result files
        files = []
        if not os.path.exists(RESULTS_DIR):
            logger.error(f"Results dir not found: {RESULTS_DIR}")
            return {}

        now = pd.Timestamp.now().timestamp()

        for f in os.listdir(RESULTS_DIR):
            full_path = os.path.join(RESULTS_DIR, f)
            mtime = os.path.getmtime(full_path)

            # Filter by time
            if (now - mtime) > (lookback_minutes * 60):
                continue

            if f.endswith(".json") and not f.startswith(".") and "meta" not in f:
                files.append(full_path)
            elif f.endswith(".zip") and f.startswith("backtest-result"):
                files.append(full_path)

        if not files:
            logger.warning(
                f"No recent backtest results found (checked last {lookback_minutes} mins)."
            )
            return {}

        logger.info(f"Found {len(files)} recent backtest files. Aggregating...")

        for file_path in files:
            try:
                data = {}
                if file_path.endswith(".zip"):
                    with zipfile.ZipFile(file_path, "r") as z:
                        # Find the main json file inside zip
                        # Usually matches zip basename but with .json
                        # Or just take the first json that isn't meta
                        candidates = [
                            n
                            for n in z.namelist()
                            if n.endswith(".json") and "meta" not in n
                        ]
                        if candidates:
                            with z.open(candidates[0]) as json_file:
                                data = json.load(json_file)
                else:
                    with open(file_path, "r") as f:
                        data = json.load(f)

                # Merge strategy metrics
                if "strategy" in data:
                    aggregated_results["strategy"].update(data["strategy"])

            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")

        return aggregated_results

    except Exception as e:
        logger.error(f"Error scanning backtest results: {e}")
        return {}


def guess_regime_vector(strategy_name: str) -> list:
    """Heuristic to guess ideal regime based on strategy name."""
    name = strategy_name.lower()

    # [Trend, Volatility, Volume, MeanReversion]
    if "trend" in name or "supertrend" in name:
        return [0.9, 0.4, 0.6, 0.2]
    elif "rsi" in name or "reversion" in name or "dip" in name:
        return [0.2, 0.5, 0.5, 0.9]  # Mean Reversion focus
    elif "breakout" in name:
        return [0.7, 0.8, 0.9, 0.3]  # High Vol/Vol
    elif "scalp" in name:
        return [0.4, 0.4, 0.8, 0.5]
    elif "channel" in name:
        return [0.5, 0.6, 0.5, 0.8]
    else:
        return [0.5, 0.5, 0.5, 0.5]  # Neutral / Balanced


def main():
    print("==========================================")
    print("      STRATEGY SCORING AUTOMATION         ")
    print("==========================================")

    # 1. Analyze Market
    print("[1/3] Analyzing Real-Time Market Conditions...")
    df = get_current_market_data()
    if df.empty:
        print("Error: Could not fetch market data. Aborting.")
        return

    quant = MarketQuantAnalyzer()
    market_vector_dict = quant.analyze_market_state(df)
    market_vector = list(market_vector_dict.values())

    print("Current Market Context (SOL/USDT):")
    for k, v in market_vector_dict.items():
        print(f"  > {k}: {v}")

    # 2. Load Results
    print("\n[2/3] Loading Backtest Performance...")
    # Increase lookback to ensure we catch the long running backtest results
    results = load_recent_backtests(lookback_minutes=600)
    if not results or "strategy" not in results or not results["strategy"]:
        print("No strategy results loaded.")
        return

    strategy_metrics = results.get("strategy", {})
    profiles = []

    for strat_name, metrics in strategy_metrics.items():
        trades = metrics.get("trades", [])
        total_trades = len(trades)

        # Calculate raw metrics if not pre-calculated
        wins = sum(1 for t in trades if t.get("profit_ratio", 0) > 0)
        win_rate = wins / total_trades if total_trades > 0 else 0

        drawdown = 0.5
        sharpe = 0.0

        results_list = metrics.get("results_per_pair", [])
        total_res = next((r for r in results_list if r.get("key") == "TOTAL"), None)

        if total_res:
            drawdown = total_res.get("max_drawdown_account", 0.0)
            sharpe = total_res.get("sharpe", 0.0)

        # Filter mostly insignificant results unless we have no other choice
        # if total_trades < 5 and drawdown == 0:
        #      continue

        profile = StrategyProfile(
            strategy_id=strat_name,
            ideal_regime_vector=guess_regime_vector(strat_name),
            win_rate_last_50_trades=win_rate,
            sharpe_ratio_rolling=sharpe,
            max_drawdown_allowed=0.30,
            current_drawdown=drawdown,
        )
        profiles.append(profile)

    print(f"Loaded {len(profiles)} qualified strategies.")

    # 3. Strategic Matrix
    print("\n[3/3] Strategic Analysis: Regime Suitability Matrix")
    scorer = StrategyScorer()

    # Define synthetic regimes
    regimes = {
        "Current": market_vector,
        "Trend": [0.9, 0.2, 0.7, 0.1],  # High Trend, Low Vol
        "Chop": [0.1, 0.3, 0.4, 0.9],  # Low Trend, High MR
        "Shock": [0.4, 0.9, 0.9, 0.3],  # High Vol, High Volatility
    }

    scored_data = []  # List of dicts

    for p in profiles:
        row = {"id": p.strategy_id, "type": "Balanced"}

        # Determine type label
        if p.ideal_regime_vector[0] > 0.7:
            row["type"] = "Trend"
        elif p.ideal_regime_vector[3] > 0.7:
            row["type"] = "MeanRev"
        elif p.ideal_regime_vector[1] > 0.7:
            row["type"] = "Vol/Brk"

        # Calculate score for each regime
        for r_name, r_vec in regimes.items():
            score = scorer.calculate_fitness_score(p, r_vec)
            row[r_name] = score

        scored_data.append(row)

    # Sort by Current score
    scored_data.sort(key=lambda x: x["Current"], reverse=True)

    print("\n" + "=" * 85)
    print(
        f"{'Strategy':<30} | {'Type':<8} | {'Current':<7} | {'Trend':<7} | {'Chop':<7} | {'Shock':<7}"
    )
    print("-" * 85)

    if not scored_data:
        print("No strategies to score.")
    else:
        for item in scored_data[:15]:
            print(
                f"{item['id']:<30} | {item['type']:<8} | {item['Current']:.4f}  | {item['Trend']:.4f}  | {item['Chop']:.4f}  | {item['Shock']:.4f}"
            )

    print("=" * 85)
    if scored_data:
        print(
            f"\nTop Recommendation for NOW ({pd.Timestamp.now()}): {scored_data[0]['id']}"
        )


if __name__ == "__main__":
    main()
