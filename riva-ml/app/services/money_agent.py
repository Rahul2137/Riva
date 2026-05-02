"""
Money Agent - GPT-powered finance intent processing.
Uses GPT for ALL classification and extraction - no regex patterns.

NOTE: This agent does NOT talk to user directly.
      Orchestrator decides final wording.
"""
from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from openai import OpenAI
from enum import Enum
import os
import json
from dotenv import load_dotenv

load_dotenv()


class MoneyIntent(str, Enum):
    ADD_EXPENSE = "add_expense"
    ADD_INCOME = "add_income"
    SET_BUDGET = "set_budget"
    GET_INSIGHTS = "get_insights"
    GET_SUMMARY = "get_summary"
    CORRECTION = "correction"
    DONT_TRACK = "dont_track"
    CONVERSATION = "conversation"


class MoneyAgent:
    """
    GPT-powered agent for processing money-related requests.
    Uses structured outputs for reliable extraction.
    """
    
    def __init__(self, openai_client: OpenAI = None):
        self.client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def process_input(
        self,
        user_input: str,
        session_context: Dict = None,
        memory_context: Dict = None
    ) -> Dict:
        """
        Main entry point - uses GPT to understand intent, extract data, and generate response.
        
        Returns:
            {
                "intent": str,
                "response": str,           # Natural language response to user
                "action": {                # Database action to take (if any)
                    "type": "add_expense" | "add_income" | "set_budget" | None,
                    "data": {...}
                },
                "requires_followup": bool,
                "pending_field": str | None
            }
        """
        
        # Build context for GPT
        context_parts = []
        
        if session_context:
            if session_context.get("last_topic"):
                context_parts.append(f"Last topic discussed: {session_context['last_topic']}")
            if session_context.get("last_category"):
                context_parts.append(f"Last expense category: {session_context['last_category']}")
            if session_context.get("pending_question"):
                context_parts.append(f"Waiting for user to answer: {session_context['pending_question']}")
                if session_context.get("pending_data"):
                    context_parts.append(f"Partial data collected: {json.dumps(session_context['pending_data'])}")
            if session_context.get("recent_messages"):
                recent = session_context["recent_messages"][-3:]
                if recent:
                    context_parts.append("Recent conversation:")
                    for msg in recent:
                        context_parts.append(f"  {msg['role']}: {msg['content']}")
        
        if memory_context:
            if memory_context.get("constraints"):
                budgets = [f"{c['key']}: {c['value']}" for c in memory_context["constraints"]]
                context_parts.append(f"User's budgets: {budgets}")
        
        context_str = "\n".join(context_parts) if context_parts else "No prior context."
        
        # Call GPT with structured output
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": f"CONTEXT:\n{context_str}\n\nUSER SAYS:\n{user_input}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=500
        )
        
        result = json.loads(response.choices[0].message.content)
        
        print(f"[MONEY_AGENT] GPT returned: intent={result.get('intent')}, query_spec={result.get('query_spec')}")
        
        return {
            "intent": result.get("intent", "conversation"),
            "response": result.get("response", "I didn't quite understand that."),
            "action": result.get("action"),
            "query_spec": result.get("query_spec"),  # Add this for insights queries
            "requires_followup": result.get("requires_followup", False),
            "pending_field": result.get("pending_field"),
            "extracted_data": result.get("extracted_data", {})
        }
    
    def _get_system_prompt(self) -> str:
        return """You are RIVA's finance brain. Analyze user input and return structured JSON.

YOUR PERSONALITY:
- Friendly, concise (1-2 sentences max)
- Supportive, never judgmental about spending
- Natural conversational tone

RETURN THIS JSON STRUCTURE:
{
  "intent": "add_expense" | "add_income" | "set_budget" | "get_insights" | "correction" | "dont_track" | "conversation",
  "response": "Natural language response to speak to user",
  "action": {
    "type": "add_expense" | "add_income" | "set_budget" | "update_transaction" | null,
    "data": {
      "amount": number or null,
      "category": "food" | "transport" | "shopping" | "entertainment" | "bills" | "health" | "personal" | "other" | null,
      "description": "string",
      "date": "YYYY-MM-DD",
      "is_recurring": boolean
    }
  },
  "query_spec": {
    "type": "expense" | "income" | "all",
    "category": category or null,
    "date_range": "today" | "yesterday" | "this_week" | "last_week" | "this_month" | "last_month" | "last_30_days" | "all_time",
    "min_amount": number or null,
    "max_amount": number or null,
    "group_by": "category" | "day" | "week" | "month" | null,
    "sort_by": "amount" | "date" | null,
    "sort_order": "asc" | "desc",
    "limit": number or null
  },
  "requires_followup": boolean,
  "pending_field": "amount" | "category" | null,
  "extracted_data": {
    "topic": "what user mentioned (e.g., 'movie', 'dinner')",
    "mentioned_amount": number or null
  }
}

EXAMPLES:

User: "I spent 500 on dinner"
→ {
  "intent": "add_expense",
  "response": "Got it. Added ₹500 for dinner today.",
  "action": {"type": "add_expense", "data": {"amount": 500, "category": "food", "description": "dinner", "date": "2026-01-18"}},
  "requires_followup": false,
  "extracted_data": {"topic": "dinner", "mentioned_amount": 500}
}

User: "spent 500"
→ {
  "intent": "add_expense",
  "response": "Sure, what was this expense for?",
  "action": null,
  "requires_followup": true,
  "pending_field": "category",
  "extracted_data": {"mentioned_amount": 500}
}

User: "how much did I spend this month"
→ {
  "intent": "get_insights",
  "response": "Let me check your spending for this month.",
  "query_spec": {"type": "expense", "date_range": "this_month", "group_by": "category"},
  "requires_followup": false
}

User: "how much did I spend today"
→ {
  "intent": "get_insights",
  "response": "Let me check your spending for today.",
  "query_spec": {"type": "expense", "date_range": "today"},
  "requires_followup": false
}

User: "food expenses last week over 500"
→ {
  "intent": "get_insights",
  "response": "Let me find your food expenses over ₹500 from last week.",
  "query_spec": {"type": "expense", "category": "food", "date_range": "last_week", "min_amount": 500},
  "requires_followup": false
}

User: "what did I spend yesterday"
→ {
  "intent": "get_insights",
  "response": "Let me check your spending from yesterday.",
  "query_spec": {"type": "expense", "date_range": "yesterday"},
  "requires_followup": false
}

User: "show my top spending categories this month"
→ {
  "intent": "get_insights",
  "response": "Let me show you your top spending categories.",
  "query_spec": {"type": "expense", "date_range": "this_month", "group_by": "category", "sort_by": "amount", "sort_order": "desc", "limit": 5},
  "requires_followup": false
}

User: "don't track this"
→ {
  "intent": "dont_track",
  "response": "No problem, I won't track that.",
  "action": null,
  "requires_followup": false
}

User: "good morning"
→ {
  "intent": "conversation",
  "response": "Good morning! How can I help you today?",
  "action": null,
  "requires_followup": false
}

CONTEXT HANDLING:
- If context shows "pending_question: category" and user says "food", complete the expense with collected data
- If user says "also add 200 for coffee", use same date as last transaction
- "spent 500 there" with last_topic="movie" → category=entertainment

TODAY'S DATE: """ + datetime.now().strftime("%Y-%m-%d")


# For backward compatibility - wrapper functions
async def classify_and_respond(
    user_input: str,
    openai_client: OpenAI,
    session_context: Dict = None,
    memory_context: Dict = None
) -> Dict:
    """Convenience function for direct use."""
    agent = MoneyAgent(openai_client)
    return await agent.process_input(user_input, session_context, memory_context)
