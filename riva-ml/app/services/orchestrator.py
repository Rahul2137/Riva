"""
Orchestrator - The Golden Flow Controller
Implements the 5-stage pipeline:
1. GPT (plan) - Intent classification
2. RIVA (fetch) - Query data if needed
3. GPT (reason) - Decide actions
4. RIVA (act) - Execute with validation
5. GPT (respond) - Already in decision_engine

GPT never touches DB directly. RIVA validates all writes.
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
from openai import OpenAI
import os
import json
from dotenv import load_dotenv

from .memory_service import MemoryService
from .session_manager import SessionManager, get_session_manager
from .intent_planner import IntentPlanner
from .decision_engine import DecisionEngine
from .query_builder import QueryBuilder

load_dotenv()

# Confidence thresholds for auto-execution
CONFIDENCE_AUTO_EXECUTE = 0.9
CONFIDENCE_ASK_CONFIRM = 0.7


class Orchestrator:
    """
    Golden Flow Controller.
    Coordinates the 5-stage pipeline.
    """
    
    def __init__(
        self,
        memory_service: MemoryService = None,
        session_manager: SessionManager = None,
        openai_client: OpenAI = None,
        transactions_collection = None
    ):
        self.memory_service = memory_service
        self.session_manager = session_manager or get_session_manager()
        self.client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize the GPT stages
        self.intent_planner = IntentPlanner(self.client)
        self.decision_engine = DecisionEngine(self.client)
        
        self.transactions_collection = transactions_collection
    
    async def process_request(
        self,
        user_id: str,
        user_input: str
    ) -> Dict:
        """
        Main entry point - The Golden Flow.
        
        Returns:
            {
                "response": str,
                "intent": str,
                "actions_taken": List[str],
                "requires_followup": bool
            }
        """
        print(f"\n[GOLDEN_FLOW] ===== Processing: '{user_input}' =====")
        
        # Get session context
        session_context = self.session_manager.get_context_for_prompt(user_id)
        
        # Get memory context
        memory_context = {}
        if self.memory_service:
            try:
                memory_context = await self.memory_service.get_context_for_prompt(user_id)
            except Exception as e:
                print(f"[GOLDEN_FLOW] Memory fetch error: {e}")
        
        # Add user message to session
        self.session_manager.add_message(user_id, "user", user_input)
        
        # ========================================
        # STAGE 1: Intent & Planning (GPT #1)
        # ========================================
        print("[GOLDEN_FLOW] Stage 1: Intent Planning...")
        plan = await self.intent_planner.plan(
            user_input,
            session_context=session_context,
            memory_context=memory_context
        )
        
        intent = plan.get("intent", "conversation")
        requires_data = plan.get("requires_data", False)
        needs_clarification = plan.get("needs_clarification", False)
        
        print(f"[GOLDEN_FLOW] Intent: {intent}, requires_data: {requires_data}, needs_clarification: {needs_clarification}")
        
        # Handle clarification needed
        if needs_clarification:
            response = plan.get("clarification_question", "Could you clarify?")
            self.session_manager.set_pending_question(
                user_id,
                plan.get("action_data", {}).get("category") is None and "category" or "amount",
                plan.get("action_data", {})
            )
            self.session_manager.add_message(user_id, "assistant", response)
            return {
                "response": response,
                "intent": intent,
                "actions_taken": [],
                "requires_followup": True
            }
        
        # ========================================
        # STAGE 2: Data Fetch (RIVA)
        # ========================================
        query_results = None
        if requires_data and self.transactions_collection is not None:
            print("[GOLDEN_FLOW] Stage 2: Fetching data...")
            query_spec = plan.get("query_spec", {})
            query_results = await self._fetch_data(user_id, query_spec)
            print(f"[GOLDEN_FLOW] Data fetched: {query_results}")
        
        # ========================================
        # STAGE 3: Decision & Action (GPT #3)
        # ========================================
        print("[GOLDEN_FLOW] Stage 3: Decision Engine...")
        decision = await self.decision_engine.decide(
            user_input=user_input,
            intent=intent,
            query_results=query_results,
            memory_context=memory_context,
            action_data=plan.get("action_data")
        )
        
        response = decision.get("response", "I didn't quite understand that.")
        suggested_actions = decision.get("actions", [])
        memory_updates = decision.get("memory_updates", [])
        
        print(f"[GOLDEN_FLOW] Response: {response[:50]}...")
        
        # ========================================
        # STAGE 4: Action Execution (RIVA)
        # ========================================
        print("[GOLDEN_FLOW] Stage 4: Action Execution...")
        actions_taken = []
        
        for action in suggested_actions:
            confidence = action.get("confidence", 0)
            action_type = action.get("type")
            
            print(f"[GOLDEN_FLOW] Action: {action_type}, confidence: {confidence}")
            
            if confidence >= CONFIDENCE_AUTO_EXECUTE:
                # Auto-execute high confidence actions
                result = await self._execute_action(user_id, action)
                if result:
                    actions_taken.append(result)
            elif confidence >= CONFIDENCE_ASK_CONFIRM:
                # TODO: Ask for confirmation
                print(f"[GOLDEN_FLOW] Would ask confirmation for: {action_type}")
        
        # ========================================
        # STAGE 5: Memory Updates (RIVA)
        # ========================================
        if memory_updates and self.memory_service:
            print("[GOLDEN_FLOW] Stage 5: Memory Updates...")
            for update in memory_updates:
                confidence = update.get("confidence", 0)
                if confidence >= CONFIDENCE_AUTO_EXECUTE:
                    await self._update_memory(user_id, update)
        
        # Clear pending if we completed the action
        if actions_taken:
            self.session_manager.clear_pending(user_id)
        
        # Update session with last topic
        if plan.get("action_data", {}).get("category"):
            self.session_manager.set_last_category(user_id, plan["action_data"]["category"])
        
        # Add response to session
        self.session_manager.add_message(user_id, "assistant", response)
        
        print(f"[GOLDEN_FLOW] ===== Complete: {len(actions_taken)} actions =====\n")
        
        return {
            "response": response,
            "intent": intent,
            "actions_taken": actions_taken,
            "requires_followup": False
        }
    
    async def _fetch_data(self, user_id: str, query_spec: Dict) -> Dict:
        """Stage 2: Fetch data from DB using query_spec."""
        builder = QueryBuilder(user_id)
        
        try:
            query = builder.build_query(query_spec)
            print(f"[DATA_FETCH] Query: {query}")
            
            cursor = self.transactions_collection.find(query)
            transactions = await cursor.to_list(length=100)
            
            if not transactions:
                return {"total": 0, "count": 0, "by_category": {}}
            
            # Aggregate data
            total = sum(t.get("amount", 0) for t in transactions)
            
            by_category = {}
            for t in transactions:
                cat = t.get("category", "other")
                by_category[cat] = by_category.get(cat, 0) + t.get("amount", 0)
            
            return {
                "total": total,
                "count": len(transactions),
                "by_category": by_category,
                "date_range": query_spec.get("time_range", {}).get("value", "this_month")
            }
        
        except Exception as e:
            print(f"[DATA_FETCH] Error: {e}")
            return {"total": 0, "count": 0, "error": str(e)}
    
    async def _execute_action(self, user_id: str, action: Dict) -> Optional[str]:
        """Stage 4: Execute validated action."""
        action_type = action.get("type")
        data = action.get("data", {})
        
        print(f"[ACTION] Executing: {action_type}")
        
        try:
            if action_type == "add_expense":
                if self.transactions_collection is not None and data.get("amount"):
                    transaction = {
                        "user_id": user_id,
                        "type": "expense",
                        "amount": data.get("amount"),
                        "category": data.get("category", "other"),
                        "description": data.get("description", ""),
                        "date": data.get("date", datetime.now().strftime("%Y-%m-%d")),
                        "created_at": datetime.utcnow()
                    }
                    await self.transactions_collection.insert_one(transaction)
                    print(f"[ACTION] Expense saved: {transaction}")
                    return "expense_added"
            
            elif action_type == "add_income":
                if self.transactions_collection is not None and data.get("amount"):
                    transaction = {
                        "user_id": user_id,
                        "type": "income",
                        "amount": data.get("amount"),
                        "category": "income",
                        "description": data.get("description", ""),
                        "date": data.get("date", datetime.now().strftime("%Y-%m-%d")),
                        "created_at": datetime.utcnow()
                    }
                    await self.transactions_collection.insert_one(transaction)
                    return "income_added"
            
            elif action_type == "set_budget":
                if self.memory_service is not None and data.get("amount"):
                    await self.memory_service.set_budget(
                        user_id,
                        data.get("amount"),
                        category=data.get("category")
                    )
                    return "budget_set"
        
        except Exception as e:
            print(f"[ACTION] Error: {e}")
        
        return None
    
    async def _update_memory(self, user_id: str, update: Dict) -> bool:
        """Stage 5: Update user memory with validation."""
        memory_type = update.get("type")
        key = update.get("key")
        value = update.get("value")
        
        print(f"[MEMORY] Updating: {memory_type}/{key} = {value}")
        
        try:
            if self.memory_service:
                await self.memory_service.upsert_memory(
                    user_id=user_id,
                    memory_type=memory_type,
                    key=key,
                    value=value,
                    source="inferred"
                )
                return True
        except Exception as e:
            print(f"[MEMORY] Error: {e}")
        
        return False
