"""
Decision Engine - GPT #3 in the Golden Flow
Analyzes data + context, suggests actions with confidence scores.

This is the REASONING step - suggests but doesn't execute.
"""
from datetime import datetime
from typing import Dict, List, Optional
from openai import OpenAI
import json
import os
from dotenv import load_dotenv

load_dotenv()


class DecisionEngine:
    """
    Stage 4 of Golden Flow (GPT #3).
    Given data + context, decides what actions to take.
    Returns suggestions with confidence scores.
    """
    
    def __init__(self, openai_client: OpenAI = None):
        self.client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def decide(
        self,
        user_input: str,
        intent: str,
        query_results: Dict = None,
        memory_context: Dict = None,
        action_data: Dict = None
    ) -> Dict:
        """
        Analyze data and decide on actions.
        
        Args:
            user_input: Original user message
            intent: Classified intent from IntentPlanner
            query_results: Data fetched from DB (for query intents)
            memory_context: User preferences, budgets
            action_data: Pre-extracted data for action intents
            
        Returns:
            {
                "response": str,  # Final response to user
                "actions": [
                    {"type": str, "data": Dict, "confidence": float}
                ],
                "memory_updates": [
                    {"type": str, "key": str, "value": any, "confidence": float}
                ]
            }
        """
        
        # Build context for GPT
        context = {
            "user_input": user_input,
            "intent": intent,
            "current_datetime": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        
        if query_results:
            context["query_results"] = query_results
        
        if memory_context:
            context["user_memory"] = memory_context
        
        if action_data:
            context["action_data"] = action_data
        
        # Call GPT for decision
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": json.dumps(context, indent=2, default=str)}
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
            max_tokens=600
        )
        
        result = json.loads(response.choices[0].message.content)
        
        print(f"[DECISION_ENGINE] Actions: {len(result.get('actions', []))}, Memory updates: {len(result.get('memory_updates', []))}")
        
        return result
    
    def _get_system_prompt(self) -> str:
        return """You are RIVA's Decision Engine. Given context and data, decide actions and response.

RETURN THIS JSON:
{
  "response": "Natural, friendly response to the user",
  "actions": [
    {
      "type": "add_expense | add_income | set_budget | update_preference",
      "data": {...},
      "confidence": 0.0-1.0
    }
  ],
  "memory_updates": [
    {
      "type": "preference | habit | fact | constraint",
      "key": "descriptive_key",
      "value": "value",
      "confidence": 0.0-1.0
    }
  ]
}

CONFIDENCE RULES:
- 1.0: Explicit user request with complete data
- 0.9: Clear intent, all data present
- 0.7-0.8: Inferred from context, should confirm
- Below 0.7: Don't include in actions

RESPONSE RULES:
- Use ₹ for currency
- Be concise (1-2 sentences)
- Be friendly, never judgmental
- If query_results provided, base response on actual data

EXAMPLES:

Context: {"intent": "query_spending", "query_results": {"total": 8200, "by_category": {"food": 5000, "transport": 3200}}}
→ {
  "response": "You've spent ₹8,200 so far. Food is your biggest category at ₹5,000, followed by transport at ₹3,200.",
  "actions": [],
  "memory_updates": []
}

Context: {"intent": "add_expense", "action_data": {"amount": 500, "category": "food", "description": "dinner"}}
→ {
  "response": "Got it! Added ₹500 for dinner.",
  "actions": [{"type": "add_expense", "data": {"amount": 500, "category": "food", "description": "dinner", "date": "2026-01-18"}, "confidence": 1.0}],
  "memory_updates": []
}

Context: {"intent": "query_spending", "query_results": {"total": 9500}, "user_memory": {"constraints": [{"key": "food_budget", "value": 10000}]}}
→ {
  "response": "You've spent ₹9,500 on food this month. That's 95% of your ₹10,000 budget - getting close!",
  "actions": [],
  "memory_updates": []
}

Context: {"intent": "conversation", "user_input": "I'm vegetarian"}
→ {
  "response": "Noted! I'll remember you're vegetarian.",
  "actions": [],
  "memory_updates": [{"type": "preference", "key": "diet", "value": "vegetarian", "confidence": 0.95}]
}
"""
