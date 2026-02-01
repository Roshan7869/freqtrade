"""
Strategy Scoring Engine
=======================
Calculates fitness scores for strategies based on Market Regime alignment and Performance.
"""

import numpy as np
from scipy.spatial.distance import cosine
from typing import List, Dict
from .strategy_profile import StrategyProfile


class StrategyScorer:
    def __init__(self):
        # Weights for the final score components
        self.W_REGIME = 0.5
        self.W_PERF = 0.3
        self.W_RISK = 0.2

    def calculate_fitness_score(
        self, profile: StrategyProfile, market_vector: List[float]
    ) -> float:
        """
        Calculates a 0.0 to 1.0 (or higher) fitness score.
        """
        # 0. HARD KILLS (Binary Logic)
        # If drawdown exceeds 80% of max allowed -> KILL
        if profile.current_drawdown > (profile.max_drawdown_allowed * 0.8):
            return 0.0

        # 1. Regime Match Score (Vector Cosine Similarity)
        # 1 - cosine_distance gives similarity. 1.0 = aligned, 0.0 = orthogonal, -1.0 = opposite.
        # We clamp to 0-1 for simplified scoring.

        # Ensure vectors are numpy arrays
        v_market = np.array(market_vector)
        v_strat = np.array(profile.ideal_regime_vector)

        # Avoid zero division
        if np.all(v_market == 0) or np.all(v_strat == 0):
            regime_score = 0.5  # Neutral fallback
        else:
            similarity = 1 - cosine(v_market, v_strat)
            # Map [-1, 1] to [0, 1] for safer scoring?
            # Actually, negative correlation is bad, so mapping negative to 0 is fine.
            regime_score = max(0.0, similarity)

        # 2. Performance Score (Normalized)
        # Win Rate is 0-1. Sharpe can be >1 or <0.
        # Normalize Sharpe: assume 2.0 is great (1.0 contribution), 0 is bad.
        sharpe_norm = max(0.0, min(1.0, profile.sharpe_ratio_rolling / 2.0))
        perf_score = (profile.win_rate_last_50_trades * 0.6) + (sharpe_norm * 0.4)

        # 3. Drawdown Safety Score
        # Closer to 0 DD is better.
        # Score = 1 - (Current / MaxAllowed)
        dd_fraction = profile.current_drawdown / (profile.max_drawdown_allowed + 1e-9)
        safety_score = max(0.0, 1.0 - dd_fraction)

        # 4. Weighted Combination
        raw_score = (
            (regime_score * self.W_REGIME)
            + (perf_score * self.W_PERF)
            + (safety_score * self.W_RISK)
        )

        # 5. Penalties (Multipliers)
        # Staleness: If last trade > 7 days (168 hours), decay score
        if profile.last_trade_time_hours_ago > 168:
            raw_score *= 0.95

        return round(raw_score, 4)


class PortfolioOptimizer:
    def __init__(self, scorer: StrategyScorer):
        self.scorer = scorer

    def select_top_strategies(
        self,
        strategies: List[StrategyProfile],
        market_vector: List[float],
        top_n: int = 3,
        max_correlation: float = 0.7,
    ) -> List[Dict]:
        """
        Selects top N strategies, filtering for correlation.
        Returns detailed scoring metadata.
        """
        scored_strats = []

        # 1. Score all strategies
        for strat in strategies:
            score = self.scorer.calculate_fitness_score(strat, market_vector)
            scored_strats.append({"strategy": strat, "score": score})

        # 2. Sort by Score Descending
        scored_strats.sort(key=lambda x: x["score"], reverse=True)

        selected = []

        # 3. Correlation Filter (Simplified Group Logic for now)
        # In a real system, we'd check covariance matrix of returns.
        # Here we assume strategies have a 'correlation_group' tag.
        # We calculate correlation based on the profiles' ideal vectors (proxy for logic similarity).

        for candidate in scored_strats:
            if len(selected) >= top_n:
                break

            strat = candidate["strategy"]
            score = candidate["score"]

            if score == 0.0:
                continue  # Skip dead strategies

            # Check correlation against already selected
            is_correlated = False
            for picked in selected:
                picked_strat = picked["strategy"]

                # Check 1: Explicit Group
                if (
                    strat.correlation_group
                    and strat.correlation_group == picked_strat.correlation_group
                ):
                    is_correlated = True
                    break

                # Check 2: Vector Similarity (Logic Proxy)
                v1 = np.array(strat.ideal_regime_vector)
                v2 = np.array(picked_strat.ideal_regime_vector)
                sim = 1 - cosine(v1, v2)
                if sim > max_correlation:
                    is_correlated = True
                    break

            if not is_correlated:
                selected.append(candidate)

        return selected
