"""
Intelligent Layer - Whale Signal Provider
==========================================
Centralized interface for accessing whale tracker signals.
Handles file reading, validation, TTL checking, and confidence filtering.

Author: 3-Layer Architecture Refactor
"""

import json
import logging
import sys
import os
from pathlib import Path


# sys.path handled by main.py
from typing import Optional
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WhaleSignal:
    """Standardized whale signal data structure"""

    pair: str
    signal_type: str  # 'BUY' or 'SELL'
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    amount_usd: float = 0.0
    source: str = "whale_tracker"


class WhaleSignalProvider:
    """
    Provides clean, validated access to whale signals.

    Features:
    - Automatic TTL validation (default 15 minutes)
    - Confidence threshold filtering
    - Error handling and fallback
    """

    def __init__(
        self,
        signal_file_path: Optional[Path] = None,
        ttl_seconds: int = 900,  # 15 minutes
        min_confidence: float = 0.70,
    ):
        if signal_file_path is None:
            # Look for whale_signals.json in user_data (mounted at /freqtrade/user_data in Docker)
            # Or simplified relative path for local dev

            # Default to Docker path
            docker_path = Path("/freqtrade/user_data/whale_signals.json")
            if docker_path.exists():
                self.signal_file = docker_path
            else:
                # Fallback to local dev path (approximate)
                # src/services/whale_provider.py -> ... -> user_data
                self.signal_file = (
                    Path(__file__).resolve().parent.parent.parent.parent
                    / "user_data"
                    / "whale_signals.json"
                )
        else:
            self.signal_file = signal_file_path

        self.ttl_seconds = ttl_seconds
        self.min_confidence = min_confidence

    def get_signal(self, pair: str) -> Optional[WhaleSignal]:
        """Get the latest valid whale signal for a trading pair"""
        try:
            signals = self._load_signals()
            if not signals:
                return None

            pair_signals = [s for s in signals if s.get("pair") == pair]
            if not pair_signals:
                return None

            latest = max(pair_signals, key=lambda x: x.get("timestamp", ""))
            signal = self._parse_signal(latest)

            if not signal or not self._is_signal_valid(signal):
                return None

            logger.info(
                f"✅ Valid whale signal for {pair}: {signal.signal_type} (confidence: {signal.confidence:.2%})"
            )
            return signal

        except Exception as e:
            logger.error(f"Error loading whale signal for {pair}: {e}")
            return None

    def _load_signals(self) -> list:
        """Load signals from JSON file"""
        if not self.signal_file.exists():
            return []

        try:
            with open(self.signal_file, "r") as f:
                signals = json.load(f)
            return signals if isinstance(signals, list) else []
        except:
            return []

    def _parse_signal(self, signal_data: dict) -> Optional[WhaleSignal]:
        """Parse raw signal dict into WhaleSignal object"""
        try:
            timestamp_str = signal_data.get("timestamp", "")
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

            return WhaleSignal(
                pair=signal_data.get("pair", ""),
                signal_type=signal_data.get("signal_type", ""),
                confidence=float(signal_data.get("confidence", 0.0)),
                timestamp=timestamp,
                amount_usd=float(signal_data.get("amount_usd", 0.0)),
            )
        except:
            return None

    def _is_signal_valid(self, signal: WhaleSignal) -> bool:
        """Check if signal is valid based on TTL and confidence"""
        age_seconds = (datetime.now(timezone.utc) - signal.timestamp).total_seconds()

        if age_seconds > self.ttl_seconds:
            return False
        if signal.confidence < self.min_confidence:
            return False
        if signal.signal_type not in ["BUY", "SELL"]:
            return False

        return True


# Singleton
_whale_signal_provider = None


def get_whale_signal_provider(
    ttl_seconds: int = 900, min_confidence: float = 0.70
) -> WhaleSignalProvider:
    """Get or create the singleton Whale SignalProvider instance"""
    global _whale_signal_provider
    if _whale_signal_provider is None:
        _whale_signal_provider = WhaleSignalProvider(
            ttl_seconds=ttl_seconds, min_confidence=min_confidence
        )
    return _whale_signal_provider
