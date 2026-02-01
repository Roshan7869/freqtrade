"""
Path Setup Utility for Freqtrade Strategies
============================================
This module provides a robust path setup function that works in both
local development and Docker environments.

Import this at the top of any strategy file:
    from path_setup import setup_strategy_path
    setup_strategy_path()
"""

import sys
import os
from pathlib import Path


def setup_strategy_path():
    """
    Add the strategies directory to sys.path for proper imports.
    Works in both local and Docker environments.
    """
    # Get the directory where this file is located (strategies/)
    strategies_dir = Path(__file__).parent.resolve()

    # Add strategies directory
    if str(strategies_dir) not in sys.path:
        sys.path.insert(0, str(strategies_dir))

    # Also add Docker-specific path if it exists
    docker_strategies = Path("/freqtrade/user_data/strategies")
    if docker_strategies.exists() and str(docker_strategies) not in sys.path:
        sys.path.insert(0, str(docker_strategies))


# Auto-setup when imported
setup_strategy_path()

# Also add the project root to sys.path to allow importing 'analysis_layer', 'decision_layer', etc.
project_root = Path(__file__).parent.parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
