"""
AgentRegistry - Intent-to-agent routing.

Central registry that maps intent strings → BaseAgent instances.
The Orchestrator queries this registry to find the right agent
for each classified intent.
"""
from typing import Dict, List, Optional
from .base_agent import BaseAgent


class AgentRegistry:
    """Maps intents to agent instances.

    Usage:
        registry = AgentRegistry()
        registry.register(FinanceAgent(...))
        registry.register(ProductivityAgent(...))
        registry.register(GeneralAgent(...))

        agent = registry.get_agent_for_intent("add_expense")
    """

    def __init__(self):
        self._agents: List[BaseAgent] = []
        self._intent_map: Dict[str, BaseAgent] = {}
        self._domain_map: Dict[str, BaseAgent] = {}
        self._fallback_agent: Optional[BaseAgent] = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register(self, agent: BaseAgent, *, is_fallback: bool = False) -> None:
        """Register an agent and map its supported intents.

        Args:
            agent: A concrete BaseAgent implementation.
            is_fallback: If True, this agent is used when no other
                         agent matches the intent.
        """
        self._agents.append(agent)
        self._domain_map[agent.domain] = agent

        for intent in agent.get_supported_intents():
            if intent in self._intent_map:
                existing = self._intent_map[intent]
                print(
                    f"[REGISTRY] WARNING: intent '{intent}' already registered "
                    f"to {existing.domain}, overwriting with {agent.domain}"
                )
            self._intent_map[intent] = agent

        if is_fallback:
            self._fallback_agent = agent

        # Let the agent run any lazy init
        await agent.on_register()

        print(
            f"[REGISTRY] Registered {agent.domain} agent "
            f"with intents: {agent.get_supported_intents()}"
        )

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_agent_for_intent(self, intent: str) -> Optional[BaseAgent]:
        """Return the agent responsible for the given intent.

        Falls back to the fallback agent (GeneralAgent) if no
        specific agent is registered for the intent.
        """
        agent = self._intent_map.get(intent)
        if agent is None:
            return self._fallback_agent
        return agent

    def get_agent_for_domain(self, domain: str) -> Optional[BaseAgent]:
        """Return the agent for a specific domain."""
        return self._domain_map.get(domain)

    def get_all_intents(self) -> List[str]:
        """Return all registered intents."""
        return list(self._intent_map.keys())

    def get_all_agents(self) -> List[BaseAgent]:
        """Return all registered agents."""
        return list(self._agents)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check_all(self) -> Dict[str, bool]:
        """Run health checks on every registered agent."""
        results = {}
        for agent in self._agents:
            try:
                results[agent.domain] = await agent.health_check()
            except Exception as e:
                print(f"[REGISTRY] Health check failed for {agent.domain}: {e}")
                results[agent.domain] = False
        return results
