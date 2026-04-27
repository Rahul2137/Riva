"""
Orchestrator - The Golden Flow Controller (v2: Agent-based)

Implements the multi-stage pipeline:
1. Intent Planning  (GPT) — classify intent, plan data needs
2. Agent Routing    (RIVA) — find the right agent via AgentRegistry
3. Agent Execution  (Agent) — delegate to the domain agent
4. Memory Updates   (RIVA) — persist inferred memories
5. Response         (Agent) — return final response

GPT never touches DB directly. Agents validate all writes.
The Orchestrator is domain-agnostic; all domain logic lives in agents.
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
from openai import OpenAI
import os
from dotenv import load_dotenv

from agents.agent_registry import AgentRegistry
from agents.base_agent import AgentResponse
from services.memory_service import MemoryService
from services.session_manager import SessionManager, get_session_manager
from services.intent_planner import IntentPlanner
import asyncio

load_dotenv()

# Confidence thresholds for auto-execution
CONFIDENCE_AUTO_EXECUTE = 0.8
CONFIDENCE_ASK_CONFIRM = 0.6


class Orchestrator:
    """
    Golden Flow Controller v2.
    Routes intents to registered agents via AgentRegistry.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        memory_service: MemoryService = None,
        session_manager: SessionManager = None,
        openai_client: OpenAI = None,
    ):
        self.registry = agent_registry
        self.memory_service = memory_service
        self.session_manager = session_manager or get_session_manager()
        self.client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Intent planner (GPT stage 1)
        self.intent_planner = IntentPlanner(self.client)

    async def process_request_stream(
        self,
        user_id: str,
        user_input: str,
    ):
        """
        Main entry point — The Golden Flow (Stream version).

        Yields:
            {
                "type": "immediate" | "final",
                "response": str,
                ...other fields...
            }
        """
        print(f"\n[ORCHESTRATOR] ===== Processing: '{user_input}' =====")

        # ----------------------------------------------------------
        # Gather context
        # ----------------------------------------------------------
        session_context = self.session_manager.get_context_for_prompt(user_id)
        memory_context = {}
        if self.memory_service:
            try:
                memory_context = await self.memory_service.get_context_for_prompt(user_id)
            except Exception as e:
                print(f"[ORCHESTRATOR] Memory fetch error: {e}")

        # Add user message to session history
        self.session_manager.add_message(user_id, "user", user_input)

        # Inject user_id into context so agents can access it
        session_context["user_id"] = user_id

        # ----------------------------------------------------------
        # STAGE 1: Intent Classification (GPT)
        # ----------------------------------------------------------
        print("[ORCHESTRATOR] Stage 1: Intent Planning...")
        plan = await self.intent_planner.plan(
            user_input,
            session_context=session_context,
            memory_context=memory_context,
        )

        intent = plan.get("intent", "conversation")
        domain = plan.get("domain", "general")
        needs_clarification = plan.get("needs_clarification", False)

        print(f"[ORCHESTRATOR] Intent: {intent}, Domain: {domain}, "
              f"needs_clarification: {needs_clarification}")

        immediate_response = plan.get("immediate_response")
        if immediate_response and intent != "conversation" and not needs_clarification:
            yield {
                "type": "immediate",
                "response": immediate_response,
            }

        # Handle clarification needed
        if needs_clarification:
            response = plan.get("clarification_question", "Could you clarify?")
            self.session_manager.set_pending_question(
                user_id,
                plan.get("pending_field", "info"),
                plan.get("action_data", {}),
            )
            self.session_manager.add_message(user_id, "assistant", response)
            yield {
                "type": "final",
                "response": response,
                "intent": intent,
                "domain": domain,
                "actions_taken": [],
                "requires_followup": True,
            }
            return

        # ----------------------------------------------------------
        # STAGE 2: Agent Routing
        # ----------------------------------------------------------
        print("[ORCHESTRATOR] Stage 2: Agent Routing...")
        agent = self.registry.get_agent_for_intent(intent)

        if agent is None:
            print(f"[ORCHESTRATOR] No agent found for intent '{intent}', using fallback")
            agent = self.registry.get_agent_for_domain("general")

        if agent is None:
            print("[ORCHESTRATOR] ERROR: No agents registered!")
            yield {
                "type": "final",
                "response": "I'm having trouble processing that right now.",
                "intent": intent,
                "domain": domain,
                "actions_taken": [],
                "requires_followup": False,
            }
            return

        print(f"[ORCHESTRATOR] Routed to: {agent.domain} agent")

        # ----------------------------------------------------------
        # STAGE 3: Agent Execution
        # ----------------------------------------------------------
        print("[ORCHESTRATOR] Stage 3: Agent Execution...")

        # Pass plan's action_data into context so agents can use it
        if plan.get("action_data"):
            session_context["action_data"] = plan["action_data"]
        if plan.get("query_spec"):
            session_context["query_spec"] = plan["query_spec"]

        try:
            agent_response: AgentResponse = await agent.handle(
                intent=intent,
                user_input=user_input,
                context=session_context,
                memory=memory_context,
            )
        except Exception as e:
            print(f"[ORCHESTRATOR] Agent error: {e}")
            import traceback
            traceback.print_exc()
            yield {
                "type": "final",
                "response": "I encountered an error. Please try again.",
                "intent": intent,
                "domain": domain,
                "actions_taken": [],
                "requires_followup": False,
            }
            return

        print(f"[ORCHESTRATOR] Agent response: {agent_response.response[:80]}...")
 
        # ----------------------------------------------------------
        # STAGE 3.5: Handle Background Tasks
        # ----------------------------------------------------------
        if agent_response.background_tasks:
            print(f"[ORCHESTRATOR] Queueing {len(agent_response.background_tasks)} background tasks...")
            asyncio.create_task(self._run_background_tasks(user_id, agent, agent_response.background_tasks))
 
        # ----------------------------------------------------------

        # ----------------------------------------------------------
        # STAGE 4: Memory Updates
        # ----------------------------------------------------------
        if agent_response.memory_updates and self.memory_service:
            print(f"[ORCHESTRATOR] Stage 4: Processing {len(agent_response.memory_updates)} memory updates...")
            for update in agent_response.memory_updates:
                confidence = update.get("confidence", 0)
                if confidence >= CONFIDENCE_AUTO_EXECUTE:
                    try:
                        await self.memory_service.upsert_memory(
                            user_id=user_id,
                            memory_type=update.get("type", "fact"),
                            key=update.get("key", ""),
                            value=update.get("value", ""),
                            source="inferred",
                        )
                        print(f"[ORCHESTRATOR] Memory saved: {update.get('key')}")
                    except Exception as e:
                        print(f"[ORCHESTRATOR] Memory save error: {e}")

        # ----------------------------------------------------------
        # STAGE 5: Session Updates & Response
        # ----------------------------------------------------------

        # Handle followup state
        if agent_response.requires_followup:
            self.session_manager.set_pending_question(
                user_id,
                agent_response.pending_field or "info",
                agent_response.data or {},
            )
        elif agent_response.actions_taken:
            self.session_manager.clear_pending(user_id)

        # Track last category for context continuity
        if agent_response.data and agent_response.data.get("category"):
            self.session_manager.set_last_category(
                user_id, agent_response.data["category"]
            )

        # Add response to session history
        self.session_manager.add_message(user_id, "assistant", agent_response.response)

        print(f"[ORCHESTRATOR] ===== Complete: "
              f"{len(agent_response.actions_taken)} actions =====\n")

        yield {
            "type": "final",
            "response": agent_response.response,
            "intent": intent,
            "domain": agent.domain,
            "actions_taken": agent_response.actions_taken,
            "requires_followup": agent_response.requires_followup,
        }

    async def _run_background_tasks(self, user_id: str, agent: Any, tasks: List[Dict[str, Any]]):
        """Execute background tasks after the response has been sent."""
        for task in tasks:
            task_type = task.get("type")
            payload = task.get("payload", {})
            print(f"[ORCHESTRATOR] Running background task: {task_type} (Agent: {agent.domain})")
            
            try:
                # Delegate back to the agent for background processing if it has a method for it
                if hasattr(agent, "execute_background_task"):
                    await agent.execute_background_task(task_type, payload, user_id)
                else:
                    print(f"[WARNING] Agent {agent.domain} does not support background tasks.")
            except Exception as e:
                print(f"[ERROR] Background task {task_type} failed: {e}")
