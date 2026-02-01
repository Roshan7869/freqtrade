"""
Test/Demo Script for 4-Agent Swarm System
==========================================
Demonstrates the full pipeline with sample data.

Usage:
    python scripts/test_swarm.py
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from decision_layer.src.swarm_orchestrator import get_swarm_orchestrator


def generate_sample_data(days=30):
    """Generate sample OHLCV data with indicators"""

    # Generate dates
    dates = pd.date_range(end=datetime.now(), periods=days * 24, freq="1H")

    # Generate price data (simple random walk)
    base_price = 150.0
    returns = np.random.normal(0.0001, 0.02, len(dates))
    prices = base_price * np.exp(np.cumsum(returns))

    # OHLCV
    df = pd.DataFrame(
        {
            "date": dates,
            "open": prices * (1 + np.random.uniform(-0.005, 0.005, len(dates))),
            "high": prices * (1 + np.random.uniform(0.002, 0.015, len(dates))),
            "low": prices * (1 - np.random.uniform(0.002, 0.015, len(dates))),
            "close": prices,
            "volume": np.random.uniform(1e6, 5e6, len(dates)),
        }
    )

    # Calculate simple indicators
    df["rsi"] = 50 + np.random.normal(0, 15, len(df))  # Mock RSI
    df["rsi"] = df["rsi"].clip(0, 100)

    df["adx"] = 25 + np.random.normal(0, 10, len(df))  # Mock ADX
    df["adx"] = df["adx"].clip(0, 100)

    df["macd"] = np.random.normal(0, 0.5, len(df))
    df["macdsignal"] = df["macd"].rolling(9).mean()

    df["atr"] = df["close"] * 0.02  # 2% ATR

    df["ema_fast"] = df["close"].ewm(span=12).mean()
    df["ema_slow"] = df["close"].ewm(span=26).mean()

    # Bollinger Bands
    rolling_mean = df["close"].rolling(20).mean()
    rolling_std = df["close"].rolling(20).std()
    df["bb_mid"] = rolling_mean
    df["bb_upper"] = rolling_mean + 2 * rolling_std
    df["bb_lower"] = rolling_mean - 2 * rolling_std

    df = df.dropna()  # Remove NaN from rolling calculations

    return df


async def test_swarm():
    """Test the swarm orchestrator with sample data"""

    print("\n" + "=" * 70)
    print("🚀 4-AGENT SWARM SYSTEM TEST")
    print("=" * 70 + "\n")

    # Initialize swarm
    print("Initializing Swarm Orchestrator...")
    swarm = get_swarm_orchestrator()
    print("✅ Swarm initialized\n")

    # Generate sample data
    print("Generating sample market data...")
    df = generate_sample_data(days=30)
    print(f"✅ Generated {len(df)} candles\n")

    print(f"Latest candle:")
    print(f"  Close: ${df.iloc[-1]['close']:.2f}")
    print(f"  RSI: {df.iloc[-1]['rsi']:.2f}")
    print(f"  ADX: {df.iloc[-1]['adx']:.2f}")
    print(f"  MACD: {df.iloc[-1]['macd']:.4f}\n")

    # Run swarm analysis
    print("Running 4-agent pipeline...\n")

    decision = await swarm.analyze_and_decide(
        pair="SOL/USDT:USDT",
        ohlcv_dataframe=df,
        timeframe="1h",
        portfolio_balance=10000.0,
        existing_exposure_pct=30.0,
        risk_limits={
            "max_exposure_pct": 80.0,
            "max_drawdown_pct": 15.0,
            "max_leverage": 20.0,
            "max_position_pct": 10.0,
            "max_correlation": 0.8,
        },
        portfolio_state={
            "total_balance": 10000.0,
            "current_exposure_pct": 30.0,
            "current_drawdown_pct": 2.5,
            "open_positions": 2,
            "pairs_held": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
        },
    )

    # Display results
    print("\n" + "=" * 70)
    print("📊 SWARM DECISION RESULTS")
    print("=" * 70 + "\n")

    print(f"⏱️  Pipeline Duration: {decision.decision_pipeline_duration_ms:.0f}ms")
    print(f"🤖 Agents Involved: {', '.join(decision.agents_involved)}\n")

    print("🔬 RESEARCHER (DeepSeek R1):")
    print(f"   Regime: {decision.regime_assessment.regime}")
    print(f"   Confidence: {decision.regime_assessment.confidence:.2f}")
    print(f"   Risk Level: {decision.regime_assessment.risk_level}/10")
    print(
        f"   Strategies: {', '.join(decision.regime_assessment.suggested_strategies)}\n"
    )

    print("📊 ANALYST (Qwen Coder):")
    print(f"   Signal: {decision.signal_proposal.direction}")
    print(f"   Entry: ${decision.signal_proposal.entry_price}")
    print(f"   Stop: ${decision.signal_proposal.stop_loss}")
    print(f"   Target: ${decision.signal_proposal.take_profit}")
    print(f"   Score: {decision.signal_proposal.technical_score:.2f}\n")

    print("⚡ EXECUTOR (Llama 3.1):")
    print(f"   Quantity: {decision.draft_order.quantity:.2f}")
    print(f"   USD Value: ${decision.draft_order.quantity_usd:.2f}")
    print(f"   Leverage: {decision.draft_order.leverage}x")
    print(f"   Allocation: {decision.draft_order.portfolio_allocation_pct:.1f}%\n")

    print("🛡️  RISK GUARDIAN (Gemini 2.0):")
    print(f"   Status: {decision.risk_verification.status}")
    print(f"   Checks Passed: {len(decision.risk_verification.checks_passed)}")
    print(f"   Checks Failed: {len(decision.risk_verification.checks_failed)}")
    print(
        f"   Post-Trade Exposure: {decision.risk_verification.post_trade_exposure_pct:.1f}%\n"
    )

    print("✅ FINAL DECISION:")
    print(f"   Execute: {'YES' if decision.should_execute else 'NO'}")
    print(f"   Direction: {decision.final_direction}")

    if decision.should_execute and decision.final_order:
        print(f"\n📝 FINAL ORDER:")
        for key, value in decision.final_order.items():
            print(f"   {key}: {value}")
    elif not decision.should_execute:
        print(f"\n❌ NOT EXECUTING:")
        if decision.risk_verification.rejection_reason:
            print(f"   Reason: {decision.risk_verification.rejection_reason}")

    print("\n" + "=" * 70)
    print("✅ TEST COMPLETE")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(test_swarm())
