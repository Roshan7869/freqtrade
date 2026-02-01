"""
4-Agent Swarm Architecture
===========================
Convenience imports for the swarm system.
"""

from .model_factory import ModelFactory, get_model_factory
from .researcher_agent import ResearcherAgent, get_researcher_agent
from .analyst_agent import AnalystAgent, get_analyst_agent
from .executor_agent import ExecutorAgent, get_executor_agent
from .risk_guardian import RiskGuardianAgent, get_risk_guardian

__all__ = [
    # Factory
    "ModelFactory",
    "get_model_factory",
    # Agents
    "ResearcherAgent",
    "AnalystAgent",
    "ExecutorAgent",
    "RiskGuardianAgent",
    # Singleton getters
    "get_researcher_agent",
    "get_analyst_agent",
    "get_executor_agent",
    "get_risk_guardian",
]
