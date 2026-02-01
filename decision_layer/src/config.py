"""
Decision Layer Configuration
===========================
Centralized config.
"""

import os
import sys

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class Config:
    KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")
    # Decision Logic Params
    MIN_VOTES = int(os.getenv("DECISION_MIN_VOTES", "2"))
