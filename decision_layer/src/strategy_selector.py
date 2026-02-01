"""
Backtest-Based Strategy Selector
=================================
Automatically selects the best strategy for live trading based on backtest scores.

Key Features:
1. Aggregates ALL backtest results
2. Scores strategies using multiple metrics
3. Considers market regime compatibility
4. Outputs top strategies for live deployment
5. Integrates with the 4-Agent Swarm for enhanced decision making
"""

import os
import sys
import json
import logging
import zipfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import pandas as pd

# Add project root
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StrategySelector")

RESULTS_DIR = project_root / "user_data" / "backtest_results"
STRATEGIES_DIR = project_root / "user_data" / "strategies"


@dataclass
class StrategyScore:
    """Comprehensive scoring for a strategy based on backtest results"""

    strategy_name: str

    # Core Performance Metrics
    total_profit_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0

    # Risk Metrics
    max_drawdown_pct: float = 0.0
    avg_trade_duration_hours: float = 0.0
    total_trades: int = 0

    # Consistency Metrics
    winning_months_pct: float = 0.0
    profit_per_trade_pct: float = 0.0

    # Regime Suitability
    best_regime: str = "Unknown"
    regime_scores: Dict[str, float] = field(default_factory=dict)

    # Final Composite Score (0-100)
    composite_score: float = 0.0

    # Metadata
    backtest_count: int = 0
    last_backtest_date: Optional[datetime] = None
    pairs_tested: List[str] = field(default_factory=list)
    timeframes_tested: List[str] = field(default_factory=list)


class StrategySelector:
    """
    Selects the best strategies based on backtest performance.
    Uses a weighted scoring system to rank strategies.
    """

    # Weights for composite scoring (must sum to 1.0)
    WEIGHTS = {
        "profit_factor": 0.20,  # Higher = better risk-adjusted returns
        "sharpe_ratio": 0.15,  # Risk-adjusted excess return
        "win_rate": 0.15,  # Consistency of winning
        "max_drawdown": 0.15,  # Inverted - lower is better
        "total_trades": 0.10,  # Statistical significance
        "profit_per_trade": 0.10,  # Efficiency per trade
        "regime_match": 0.15,  # Current regime suitability
    }

    def __init__(self, results_dir: Path = RESULTS_DIR):
        self.results_dir = results_dir
        self.all_results: Dict[
            str, List[Dict]
        ] = {}  # strategy -> list of backtest results
        self.strategy_scores: Dict[str, StrategyScore] = {}

    def load_all_backtest_results(self, lookback_days: int = 30) -> int:
        """
        Load and aggregate all backtest results from the past N days.
        Returns count of files processed.
        """
        files_processed = 0
        cutoff_time = datetime.now() - timedelta(days=lookback_days)

        if not self.results_dir.exists():
            logger.error(f"Results directory not found: {self.results_dir}")
            return 0

        # Scan all backtest files
        for file_path in self.results_dir.iterdir():
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff_time:
                    continue

                data = None

                if file_path.suffix == ".zip" and file_path.name.startswith(
                    "backtest-result"
                ):
                    # Extract JSON from ZIP
                    with zipfile.ZipFile(file_path, "r") as z:
                        candidates = [
                            n
                            for n in z.namelist()
                            if n.endswith(".json") and "meta" not in n
                        ]
                        if candidates:
                            with z.open(candidates[0]) as f:
                                data = json.load(f)

                elif file_path.suffix == ".json" and "meta" not in file_path.name:
                    with open(file_path, "r") as f:
                        data = json.load(f)

                if data and "strategy" in data:
                    for strat_name, strat_data in data["strategy"].items():
                        if strat_name not in self.all_results:
                            self.all_results[strat_name] = []

                        self.all_results[strat_name].append(
                            {
                                "data": strat_data,
                                "file": str(file_path),
                                "timestamp": mtime,
                            }
                        )
                    files_processed += 1

            except Exception as e:
                logger.debug(f"Skipping {file_path.name}: {e}")

        logger.info(
            f"Loaded {files_processed} backtest files for {len(self.all_results)} strategies"
        )
        return files_processed

    def calculate_strategy_score(self, strategy_name: str) -> StrategyScore:
        """
        Calculate comprehensive score for a single strategy
        based on ALL its backtest results.
        """
        results = self.all_results.get(strategy_name, [])
        if not results:
            return StrategyScore(strategy_name=strategy_name)

        score = StrategyScore(strategy_name=strategy_name)
        score.backtest_count = len(results)
        score.last_backtest_date = max(r["timestamp"] for r in results)

        # Aggregate metrics across all backtests
        total_profits = []
        win_rates = []
        profit_factors = []
        sharpe_ratios = []
        max_drawdowns = []
        trade_counts = []
        pairs = set()
        timeframes = set()

        for result in results:
            data = result["data"]

            # Extract from results_per_pair TOTAL row
            results_per_pair = data.get("results_per_pair", [])
            total_row = next(
                (r for r in results_per_pair if r.get("key") == "TOTAL"), None
            )

            if total_row:
                total_profits.append(total_row.get("profit_pct", 0))
                profit_factors.append(total_row.get("profit_factor", 0))
                sharpe_ratios.append(total_row.get("sharpe", 0))
                max_drawdowns.append(abs(total_row.get("max_drawdown_account", 0)))
                trade_counts.append(total_row.get("trades", 0))

            # Extract from trades list
            trades = data.get("trades", [])
            if trades:
                wins = sum(1 for t in trades if t.get("profit_ratio", 0) > 0)
                win_rates.append(wins / len(trades) if trades else 0)
                trade_counts.append(len(trades))

                # Collect pairs
                for t in trades:
                    pairs.add(t.get("pair", "Unknown"))

            # Collect timeframes from metadata
            if "timeframe" in data:
                timeframes.add(data["timeframe"])

        # Calculate averages with safety
        score.total_profit_pct = (
            sum(total_profits) / len(total_profits) if total_profits else 0
        )
        score.win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
        score.profit_factor = (
            sum(profit_factors) / len(profit_factors) if profit_factors else 0
        )
        score.sharpe_ratio = (
            sum(sharpe_ratios) / len(sharpe_ratios) if sharpe_ratios else 0
        )
        score.max_drawdown_pct = (
            sum(max_drawdowns) / len(max_drawdowns) if max_drawdowns else 0
        )
        score.total_trades = sum(trade_counts)
        score.profit_per_trade_pct = score.total_profit_pct / max(score.total_trades, 1)
        score.pairs_tested = list(pairs)
        score.timeframes_tested = list(timeframes)

        # Infer best regime from strategy name
        score.best_regime = self._infer_regime(strategy_name)

        return score

    def _infer_regime(self, strategy_name: str) -> str:
        """Infer best regime from strategy name patterns"""
        name = strategy_name.lower()

        if any(
            kw in name
            for kw in ["trend", "supertrend", "momentum", "breakout", "wma", "ema"]
        ):
            return "TRENDING"
        elif any(
            kw in name for kw in ["reversion", "rsi", "squeeze", "range", "bb", "band"]
        ):
            return "RANGING"
        elif any(kw in name for kw in ["dip", "dca", "martingale", "scalp"]):
            return "VOLATILE"
        else:
            return "BALANCED"

    def calculate_composite_score(
        self, score: StrategyScore, current_regime: str = "BALANCED"
    ) -> float:
        """
        Calculate composite score (0-100) using weighted metrics.
        Higher = Better for live trading.
        """
        components = []

        # 1. Profit Factor Score (0-100): Target 2.0 = 100
        pf_score = (
            min(100, (score.profit_factor / 2.0) * 100)
            if score.profit_factor > 0
            else 0
        )
        components.append(("profit_factor", pf_score))

        # 2. Sharpe Ratio Score (0-100): Target 2.0 = 100
        sharpe_score = min(100, max(0, (score.sharpe_ratio + 1) / 3 * 100))
        components.append(("sharpe_ratio", sharpe_score))

        # 3. Win Rate Score (0-100): Direct percentage
        wr_score = score.win_rate * 100
        components.append(("win_rate", wr_score))

        # 4. Drawdown Score (0-100): Lower is better, inverted
        dd_score = max(
            0, 100 - abs(score.max_drawdown_pct) * 3
        )  # Each 1% DD costs 3 points
        components.append(("max_drawdown", dd_score))

        # 5. Trade Count Score (0-100): Target 50 trades = 100
        trades_score = min(100, (score.total_trades / 50) * 100)
        components.append(("total_trades", trades_score))

        # 6. Profit Per Trade Score (0-100): Target 2% = 100
        ppt_score = (
            min(100, (score.profit_per_trade_pct / 2) * 100)
            if score.profit_per_trade_pct > 0
            else 0
        )
        components.append(("profit_per_trade", ppt_score))

        # 7. Regime Match Score (0-100)
        if score.best_regime.upper() == current_regime.upper():
            regime_score = 100
        elif current_regime == "BALANCED":
            regime_score = 70  # Neutral regime accepts all
        else:
            regime_score = 40  # Mismatch penalty
        components.append(("regime_match", regime_score))

        # Calculate weighted sum
        composite = sum(self.WEIGHTS.get(name, 0) * value for name, value in components)

        # Bonus for statistical significance
        if score.total_trades >= 100:
            composite *= 1.05  # 5% bonus for large sample
        elif score.total_trades < 10:
            composite *= 0.8  # 20% penalty for small sample

        return min(100, composite)

    def rank_all_strategies(
        self, current_regime: str = "BALANCED"
    ) -> List[StrategyScore]:
        """
        Score and rank ALL strategies.
        Returns sorted list (highest score first).
        """
        # Calculate scores for each strategy
        for strategy_name in self.all_results.keys():
            score = self.calculate_strategy_score(strategy_name)
            score.composite_score = self.calculate_composite_score(
                score, current_regime
            )
            self.strategy_scores[strategy_name] = score

        # Sort by composite score
        ranked = sorted(
            self.strategy_scores.values(), key=lambda s: s.composite_score, reverse=True
        )

        return ranked

    def get_top_strategies(
        self, n: int = 3, current_regime: str = "BALANCED"
    ) -> List[StrategyScore]:
        """Get top N strategies for current market conditions"""
        ranked = self.rank_all_strategies(current_regime)
        return ranked[:n]

    def generate_strategy_report(self, current_regime: str = "BALANCED") -> str:
        """Generate a detailed text report of strategy rankings"""
        ranked = self.rank_all_strategies(current_regime)

        report = []
        report.append("=" * 100)
        report.append(
            f"STRATEGY RANKING REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        report.append(f"Current Regime: {current_regime}")
        report.append("=" * 100)
        report.append("")
        report.append(
            f"{'Rank':<5} {'Strategy':<35} {'Score':>7} {'PF':>6} {'WR':>6} {'Sharpe':>7} {'DD%':>6} {'Trades':>6}"
        )
        report.append("-" * 100)

        for i, s in enumerate(ranked[:20], 1):
            report.append(
                f"{i:<5} {s.strategy_name:<35} {s.composite_score:>7.1f} "
                f"{s.profit_factor:>6.2f} {s.win_rate * 100:>5.1f}% "
                f"{s.sharpe_ratio:>7.2f} {s.max_drawdown_pct:>5.1f}% {s.total_trades:>6}"
            )

        report.append("=" * 100)

        # Top 3 Recommendations
        report.append("")
        report.append("TOP 3 STRATEGIES FOR LIVE TRADING:")
        for i, s in enumerate(ranked[:3], 1):
            report.append(f"  {i}. {s.strategy_name} (Score: {s.composite_score:.1f})")
            report.append(
                f"     Profit Factor: {s.profit_factor:.2f} | Win Rate: {s.win_rate * 100:.1f}%"
            )
            report.append(
                f"     Max Drawdown: {s.max_drawdown_pct:.1f}% | Total Trades: {s.total_trades}"
            )
            report.append(f"     Best Regime: {s.best_regime}")
            report.append("")

        return "\n".join(report)

    def export_rankings_json(self, output_path: Optional[Path] = None) -> Dict:
        """Export rankings to JSON format"""
        ranked = self.rank_all_strategies()

        export_data = {
            "generated_at": datetime.now().isoformat(),
            "total_strategies": len(ranked),
            "rankings": [
                {
                    "rank": i,
                    "strategy_name": s.strategy_name,
                    "composite_score": round(s.composite_score, 2),
                    "profit_factor": round(s.profit_factor, 2),
                    "win_rate": round(s.win_rate, 4),
                    "sharpe_ratio": round(s.sharpe_ratio, 2),
                    "max_drawdown_pct": round(s.max_drawdown_pct, 2),
                    "total_trades": s.total_trades,
                    "backtest_count": s.backtest_count,
                    "best_regime": s.best_regime,
                    "pairs_tested": s.pairs_tested[:5],  # Limit for readability
                    "timeframes_tested": s.timeframes_tested,
                }
                for i, s in enumerate(ranked, 1)
            ],
        }

        if output_path:
            with open(output_path, "w") as f:
                json.dump(export_data, f, indent=2)
            logger.info(f"Rankings exported to {output_path}")

        return export_data


def main():
    """Main execution: Analyze backtests and recommend strategies"""
    print("\n" + "=" * 80)
    print("   BACKTEST-BASED STRATEGY SELECTOR")
    print("   Analyzing all backtest results to find optimal strategies...")
    print("=" * 80 + "\n")

    # Initialize selector
    selector = StrategySelector()

    # Load all backtest results (last 30 days)
    print("[1/3] Loading backtest results...")
    file_count = selector.load_all_backtest_results(lookback_days=30)

    if file_count == 0:
        print("ERROR: No backtest results found!")
        print(
            f"Please run backtests first using: docker exec freqtrade freqtrade backtesting"
        )
        return

    print(
        f"      Found {file_count} backtest files for {len(selector.all_results)} strategies\n"
    )

    # Get current regime (simplified - could use MarketQuant here)
    print("[2/3] Determining current market regime...")
    current_regime = "BALANCED"  # Default; could enhance with real-time analysis
    print(f"      Current regime: {current_regime}\n")

    # Generate report
    print("[3/3] Calculating strategy scores...\n")
    report = selector.generate_strategy_report(current_regime)
    print(report)

    # Export JSON
    output_file = project_root / "user_data" / "strategy_rankings.json"
    selector.export_rankings_json(output_file)
    print(f"\nRankings exported to: {output_file}")

    # Get top strategies
    top = selector.get_top_strategies(n=3, current_regime=current_regime)

    print("\n" + "=" * 80)
    print("RECOMMENDED ACTION:")
    print("=" * 80)

    if top:
        best = top[0]
        print(f"\n  Set your live strategy to: {best.strategy_name}")
        print(
            f"  Command: docker exec freqtrade freqtrade trade --strategy {best.strategy_name}"
        )
        print(f"\n  Expected Performance:")
        print(f"    - Profit Factor: {best.profit_factor:.2f}x")
        print(f"    - Win Rate: {best.win_rate * 100:.1f}%")
        print(f"    - Max Drawdown: {best.max_drawdown_pct:.1f}%")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
