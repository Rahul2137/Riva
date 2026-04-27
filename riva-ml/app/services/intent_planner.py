"""
Intent Planner - GPT Stage 1 in the Golden Flow.

Classifies user intent across ALL domains (money, productivity, general).
Determines if data is needed, checks for clarifications.

This is a READ-ONLY step — no database writes.
"""
from datetime import datetime
from typing import Dict
from openai import OpenAI
import os
import json
from dotenv import load_dotenv

load_dotenv()


class IntentPlanner:
    """
    Stage 1 of Golden Flow.
    Uses GPT to classify intent and determine data requirements.
    Now supports all domains: money, productivity, general.
    """

    def __init__(self, openai_client: OpenAI = None):
        self.client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def plan(
        self,
        user_input: str,
        session_context: Dict = None,
        memory_context: Dict = None,
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
                "pending_field": str | None,
                "query_spec": Dict | None,
                "action_data": Dict | None,
                "immediate_response": str | None,
            }
        """
        # Build context
        context_parts = ["Current date/time: " + datetime.now().strftime("%Y-%m-%d %H:%M")]

        if session_context:
            if session_context.get("last_topic"):
                context_parts.append(f"Last topic: {session_context['last_topic']}")
            if session_context.get("last_category"):
                context_parts.append(f"Last expense category: {session_context['last_category']}")
            if session_context.get("pending_question"):
                context_parts.append(f"Waiting for answer to: {session_context['pending_question']}")
                if session_context.get("pending_data"):
                    context_parts.append(f"Partial data: {json.dumps(session_context['pending_data'])}")
            if session_context.get("recent_messages"):
                recent = session_context["recent_messages"][-3:]
                for msg in recent:
                    context_parts.append(f"  {msg.get('role', 'user')}: {msg.get('content', '')}")

        if memory_context:
            if memory_context.get("constraints"):
                context_parts.append(f"User budgets: {memory_context['constraints']}")
            if memory_context.get("preferences"):
                context_parts.append(f"User preferences: {memory_context['preferences']}")

        context_str = "\n".join(context_parts)

        # Call GPT for intent classification
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": f"CONTEXT:\n{context_str}\n\nUSER SAYS:\n{user_input}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=600,
            )
            result = json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[INTENT_PLANNER] Error: {e}")
            result = {
                "intent": "conversation",
                "domain": "general",
                "requires_data": False,
                "needs_clarification": False,
            }

        print(
            f"[INTENT_PLANNER] Intent: {result.get('intent')}, "
            f"Domain: {result.get('domain')}, "
            f"requires_data: {result.get('requires_data')}"
        )

        return result

    def _get_system_prompt(self) -> str:
        return """You are RIVA's Intent Planner. Analyze user input and determine processing requirements.
Route to the correct DOMAIN and classify the precise INTENT.

DOMAINS & INTENTS:

MONEY domain:
- add_expense: User wants to record a spending
- add_income: User wants to record income
- set_budget: User wants to set a spending limit
- query_spending: User wants to know about their expenses
- query_income: User wants to know about their income
- correction: User wants to fix a previous transaction
- dont_track: User explicitly says don't record something

PRODUCTIVITY domain:
- schedule_event: User wants to add a calendar event / meeting
- query_calendar: User asks about upcoming events / schedule
- reschedule_event: User wants to move an event
- cancel_event: User wants to cancel/delete an event
- set_reminder: User wants a reminder for something

GENERAL domain:
- conversation: General chat, greetings, thanks, advice
- update_memory: User shares a preference or personal info
- general_question: Factual questions, web info

RETURN THIS JSON:
{
  "intent": "one of the allowed intents",
  "domain": "money | productivity | general",
  "requires_data": true/false,
  "needs_clarification": true/false,
  "clarification_question": "string or null",
  "pending_field": "what info is missing (amount, category, time, etc.) or null",
  "query_spec": {
    "entity": "expense | income | budget | event",
    "metric": "sum | count | list",
    "filters": {"category": "string or null"},
    "time_range": {"type": "relative", "value": "today | yesterday | this_week | last_week | this_month | last_month"}
  },
  "action_data": {
    "amount": number or null,
    "category": "food | transport | shopping | entertainment | bills | health | personal | other",
    "description": "string",
    "date": "YYYY-MM-DD",
    "event_title": "string or null",
    "event_time": "string or null",
    "event_duration": "string or null"
  },
  "immediate_response": "Brief message to show user while processing (e.g., 'Let me check...')"
}

RULES:
1. If user asks about spending/expenses → domain: money, requires_data: true
2. If user is recording something but missing info → needs_clarification: true
3. If user mentions calendar/schedule/meeting → domain: productivity
4. If user shares personal info ("I'm vegetarian", "I wake up at 6") → intent: update_memory
5. For greetings/casual chat → domain: general, intent: conversation
6. When in doubt about domain, default to general/conversation
7. If context shows pending_question and user's response is a short answer, 
   resolve it using the pending context
8. For any intent other than 'conversation', ALWAYS provide an 'immediate_response' (e.g., "Let me check that for you...", "Sure, adding it now...", "One moment...") to reduce perceived latency.

EXAMPLES:

User: "schedule gym tomorrow at 7am"
→ {"intent": "schedule_event", "domain": "productivity", "requires_data": false, "action_data": {"event_title": "gym", "event_time": "07:00", "date": "TOMORROW_DATE"}}

User: "how much did I spend today"
→ {"intent": "query_spending", "domain": "money", "requires_data": true, "query_spec": {"entity": "expense", "metric": "sum", "time_range": {"type": "relative", "value": "today"}}}

User: "spent 500 on dinner"
→ {"intent": "add_expense", "domain": "money", "requires_data": false, "action_data": {"amount": 500, "category": "food", "description": "dinner", "date": "TODAY_DATE"}}

User: "what's on my calendar"
→ {"intent": "query_calendar", "domain": "productivity", "requires_data": true}

User: "I prefer morning workouts"
→ {"intent": "update_memory", "domain": "general"}

User: "hello"
→ {"intent": "conversation", "domain": "general", "requires_data": false}

User: "spent 500"
→ {"intent": "add_expense", "domain": "money", "needs_clarification": true, "clarification_question": "What was this expense for?", "pending_field": "category", "action_data": {"amount": 500}}

TODAY'S DATE: """ + datetime.now().strftime("%Y-%m-%d")
