"""
Agents package for RIVA
All domain agents implement BaseAgent interface.
"""
from .base_agent import BaseAgent, AgentResponse
from .agent_registry import AgentRegistry
from .finance_agent import FinanceAgent
from .productivity_agent import ProductivityAgent
from .general_agent import GeneralAgent

__all__ = [
    "BaseAgent",
    "AgentResponse",
    "AgentRegistry",
    "FinanceAgent",
    "ProductivityAgent",
    "GeneralAgent",
]
