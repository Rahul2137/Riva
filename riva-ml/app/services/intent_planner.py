"""
Intent Planner - GPT #1 in the Golden Flow
Classifies user intent, determines if data is needed, checks for clarifications.

This is a READ-ONLY step - no database writes.
"""
from datetime import datetime
from typing import Dict, Optional
from openai import OpenAI
import json
import os
from dotenv import load_dotenv

load_dotenv()


class IntentPlanner:
    """
    Stage 1 of Golden Flow.
    Uses GPT to classify intent and determine data requirements.
    """
    
    def __init__(self, openai_client: OpenAI = None):
        self.client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def plan(
        self,
        user_input: str,
        session_context: Dict = None,
        memory_context: Dict = None
    ) -> Dict:
        """
        Analyze user input and plan the processing steps.
        
        Returns:
            {
                "intent": str,
                "domain": str,
                "requires_data": bool,
                "needs_clarification": bool,
                "clarification_question": str | None,
                "query_spec": Dict | None,
                "immediate_response": str | None  # For user feedback during processing
            }
        """
        
        # Build context
        context_parts = ["Current date/time: " + datetime.now().strftime("%Y-%m-%d %H:%M")]
        
        if session_context:
            if session_context.get("last_topic"):
                context_parts.append(f"Last topic: {session_context['last_topic']}")
            if session_context.get("pending_question"):
                context_parts.append(f"Waiting for answer to: {session_context['pending_question']}")
                if session_context.get("pending_data"):
                    context_parts.append(f"Partial data: {json.dumps(session_context['pending_data'])}")
        
        if memory_context:
            if memory_context.get("constraints"):
                context_parts.append(f"User budgets: {memory_context['constraints']}")
        
        context_str = "\n".join(context_parts)
        
        # Call GPT for intent classification
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": f"CONTEXT:\n{context_str}\n\nUSER SAYS:\n{user_input}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=600
        )
        
        result = json.loads(response.choices[0].message.content)
        
        print(f"[INTENT_PLANNER] Intent: {result.get('intent')}, requires_data: {result.get('requires_data')}")
        
        return result
    
    def _get_system_prompt(self) -> str:
        return """You are RIVA's Intent Planner. Analyze user input and determine processing requirements.

ALLOWED INTENTS:
- add_expense: User wants to record a spending
- add_income: User wants to record income
- set_budget: User wants to set a spending limit
- query_spending: User wants to know about their expenses
- query_income: User wants to know about their income
- update_memory: User shares a preference or personal info
- conversation: General chat, greetings, thanks

RETURN THIS JSON:
{
  "intent": "one of the allowed intents",
  "domain": "money | task | general",
  "requires_data": true/false,
  "needs_clarification": true/false,
  "clarification_question": "string or null",
  "query_spec": {
    "entity": "expense | income | budget",
    "metric": "sum | count | list",
    "filters": {"category": "string or null", "min_amount": number or null},
    "time_range": {"type": "relative", "value": "today | yesterday | this_week | last_week | this_month | last_month"}
  },
  "action_data": {
    "amount": number or null,
    "category": "food | transport | shopping | entertainment | bills | health | personal | other",
    "description": "string",
    "date": "YYYY-MM-DD"
  },
  "immediate_response": "Brief message to show user while processing (e.g., 'Let me check...')"
}

RULES:
1. If user asks about spending/expenses → requires_data: true, include query_spec
2. If user is recording an expense but missing info → needs_clarification: true
3. If intent is clear and complete → immediate_response should confirm action
4. For greetings/conversation → requires_data: false, no query_spec

EXAMPLES:

User: "how much did I spend today"
→ {
  "intent": "query_spending",
  "domain": "money",
  "requires_data": true,
  "needs_clarification": false,
  "query_spec": {"entity": "expense", "metric": "sum", "time_range": {"type": "relative", "value": "today"}},
  "immediate_response": "Let me check your spending for today..."
}

User: "spent 500 on dinner"
→ {
  "intent": "add_expense",
  "domain": "money",
  "requires_data": false,
  "needs_clarification": false,
  "action_data": {"amount": 500, "category": "food", "description": "dinner", "date": "2026-01-18"},
  "immediate_response": null
}

User: "spent 500"
→ {
  "intent": "add_expense",
  "domain": "money",
  "requires_data": false,
  "needs_clarification": true,
  "clarification_question": "What was this expense for?",
  "action_data": {"amount": 500},
  "immediate_response": null
}

User: "hello"
→ {
  "intent": "conversation",
  "domain": "general",
  "requires_data": false,
  "needs_clarification": false,
  "immediate_response": null
}
"""
