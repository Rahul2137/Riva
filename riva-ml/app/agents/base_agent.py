"""
BaseAgent - Standard interface for all RIVA agents.

Every domain agent (Finance, Productivity, General, etc.)
must implement this interface. The Orchestrator uses it
to route intents to the correct agent without knowing
implementation details.

Design rules:
- Agents are stateless; all state lives in memory/session layers.
- Agents never talk to the user directly; they return AgentResponse.
- The Orchestrator decides final wording via the DecisionEngine.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class AgentResponse:
    """Standard response returned by every agent.

    Attributes:
        response: Natural-language response text for the user.
        actions_taken: List of action identifiers that were executed
                       (e.g. ["expense_added", "budget_set"]).
        data: Arbitrary payload (query results, fetched events, etc.)
              consumed by the Orchestrator / DecisionEngine.
        memory_updates: Suggested memory writes (preference, habit, fact …).
                        Each dict should have: type, key, value, confidence.
        requires_followup: True when the agent needs more info from the user.
        pending_field: Which field is missing (e.g. "category", "amount").
        metadata: Agent-specific metadata (timing, model used, …).
    """
    response: str = ""
    actions_taken: List[str] = field(default_factory=list)
    data: Optional[Dict[str, Any]] = None
    memory_updates: List[Dict[str, Any]] = field(default_factory=list)
    requires_followup: bool = False
    pending_field: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    background_tasks: List[Dict[str, Any]] = field(default_factory=list)


class BaseAgent(ABC):
    """Abstract base class that all RIVA agents must implement."""

    # ------------------------------------------------------------------
    # Core contract
    # ------------------------------------------------------------------

    @abstractmethod
    async def handle(
        self,
        intent: str,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> AgentResponse:
        """Process an intent and return a structured response.

        Args:
            intent: Classified intent string (e.g. "add_expense").
            user_input: Raw text the user said.
            context: Session context from SessionManager
                     (last_topic, pending_data, recent_messages …).
            memory: Long-term memory from MemoryService
                    (preferences, constraints, habits, facts).

        Returns:
            AgentResponse with everything the Orchestrator needs.
        """
        ...

    @abstractmethod
    def get_supported_intents(self) -> List[str]:
        """Return the list of intent strings this agent can handle."""
        ...

    @property
    @abstractmethod
    def domain(self) -> str:
        """Return the domain name (e.g. 'money', 'productivity', 'general')."""
        ...

    # ------------------------------------------------------------------
    # Optional hooks — subclasses may override
    # ------------------------------------------------------------------

    async def on_register(self) -> None:
        """Called once when the agent is registered with the AgentRegistry.
        Use for lazy initialisation (DB connections, model loading, etc.).
        """
        pass

    async def health_check(self) -> bool:
        """Return True if the agent is healthy and ready to serve."""
        return True
