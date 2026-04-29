"""
Intent Planner - Stage 1 of the RIVA Golden Flow.

Classifies user intent across ALL domains with a significantly richer
taxonomy than v1. Now understands:
  - Wellness / energy management
  - Habit tracking & goal setting
  - Focus / deep work requests
  - Emotional state and stress signals
  - Smart suggestion context signals

This is a READ-ONLY step — no database writes.
Uses the RIVA Brain for rich, context-aware classification.
"""
from datetime import datetime
from typing import Dict
from openai import OpenAI
import os
import json
from dotenv import load_dotenv

from services.riva_brain import get_time_context, detect_mood, RIVA_PERSONA

load_dotenv()


class IntentPlanner:
    """
    Stage 1 of Golden Flow.
    Uses GPT to classify intent and determine data requirements.
    Now supports an expanded domain taxonomy with proactive hooks.
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
                "user_mood": "stressed" | "positive" | "neutral",
                "proactive_hook": str | None,  # optional coaching signal
            }
        """
        time_ctx = get_time_context()
        user_mood = detect_mood(user_input)

        # Build context
        context_parts = [
            f"Current date/time: {time_ctx['date']} {time_ctx['time']} (IST)",
            f"Day: {time_ctx['day_name']} ({time_ctx['week_context']})",
            f"Time of day: {time_ctx['period']} (user energy: {time_ctx['energy_level']})",
            f"Detected user mood: {user_mood}",
        ]

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
                context_parts.append("Recent conversation:")
                for msg in recent:
                    context_parts.append(f"  {msg.get('role', 'user')}: {msg.get('content', '')}")

        if memory_context:
            if memory_context.get("constraints"):
                context_parts.append(f"User budgets/constraints: {memory_context['constraints']}")
            if memory_context.get("preferences"):
                context_parts.append(f"User preferences: {memory_context['preferences']}")
            if memory_context.get("habits"):
                context_parts.append(f"Known habits: {memory_context['habits']}")

        context_str = "\n".join(context_parts)

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": f"CONTEXT:\n{context_str}\n\nUSER SAYS:\n{user_input}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=700,
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

        # Always attach mood for downstream agents
        result["user_mood"] = user_mood

        print(
            f"[INTENT_PLANNER] Intent: {result.get('intent')}, "
            f"Domain: {result.get('domain')}, "
            f"Mood: {user_mood}, "
            f"requires_data: {result.get('requires_data')}"
        )

        return result

    def _get_system_prompt(self) -> str:
        return """You are RIVA's Intent Planner — an expert at understanding what a user truly needs.
Go beyond literal words. Detect emotional subtext, implied urgency, and coaching opportunities.

=== DOMAIN & INTENT TAXONOMY ===

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

TODO domain:
- add_todo: User wants to add a task / to-do item
- list_todos: User asks about their pending tasks
- complete_todo: User wants to mark a task as done
- update_todo: User wants to change a task's details
- delete_todo: User wants to remove a task entirely

WELLNESS domain (NEW):
- log_mood: User shares how they are feeling (stressed, tired, great, etc.)
- request_break: User mentions needing rest, a break, or feeling burnt out
- hydration_check: User mentions thirst, water, hydration
- energy_check: User asks about their energy or focus for the day

FOCUS domain (NEW):
- start_focus: User wants to start a focus/deep work session
- end_focus: User says they are done with a focus session
- block_time: User wants to block time for uninterrupted work
- batch_meetings: User wants to group their meetings together

HABIT domain (NEW):
- set_goal: User states a new goal or aspiration ("I want to work out more")
- track_habit: User logs a habit occurrence ("I meditated today")
- query_habit: User asks about their habits or streaks
- update_goal: User refines or updates an existing goal

GENERAL domain:
- conversation: General chat, greetings, thanks, advice
- update_memory: User shares a preference or personal info
- general_question: Factual questions, web info
- coaching_request: User asks for advice, tips, or help improving

=== DISTINGUISHING RULES ===

TODO vs PRODUCTIVITY:
- "add meeting at 3pm" → PRODUCTIVITY (schedule_event) — has specific time, is a calendar event
- "add buy groceries to my list" → TODO (add_todo) — is a task, no specific time slot
- "remind me to call mom" → PRODUCTIVITY (set_reminder) — time-bound reminder
- "I need to finish the report" → TODO (add_todo) — is a task to track
- "what do I have to do today?" → TODO (list_todos) — asking about tasks
- "what's on my calendar today?" → PRODUCTIVITY (query_calendar) — asking about events/meetings

WELLNESS vs GENERAL:
- "I'm tired" → WELLNESS (log_mood) — emotional/physical state
- "I'm stressed" → WELLNESS (log_mood) — with coaching opportunity
- "I need a break" → WELLNESS (request_break) — explicit break request
- "how are you?" → GENERAL (conversation) — casual chat

FOCUS vs PRODUCTIVITY:
- "I need to focus for 2 hours" → FOCUS (start_focus)
- "block 9-11 for deep work" → FOCUS (block_time)
- "move all my meetings to afternoon" → FOCUS (batch_meetings)

HABIT vs GENERAL:
- "I want to read more" → HABIT (set_goal)
- "I went to the gym today" → HABIT (track_habit)
- "I prefer morning workouts" → GENERAL (update_memory)

=== RETURN THIS JSON ===
{
  "intent": "one of the allowed intents above",
  "domain": "money | productivity | todo | wellness | focus | habit | general",
  "requires_data": true/false,
  "needs_clarification": true/false,
  "clarification_question": "string or null",
  "pending_field": "what info is missing (amount, category, time, etc.) or null",
  "query_spec": {
    "entity": "expense | income | budget | event | todo | habit",
    "metric": "sum | count | list",
    "filters": {"category": "string or null"},
    "time_range": {"type": "relative", "value": "today | yesterday | this_week | last_week | this_month | last_month"}
  },
  "action_data": {
    "amount": "number or null",
    "category": "food | transport | shopping | entertainment | bills | health | personal | other",
    "description": "string",
    "date": "YYYY-MM-DD",
    "event_title": "string or null",
    "event_time": "string or null",
    "event_duration": "string or null",
    "task_title": "string or null",
    "task_priority": "high | medium | low or null",
    "task_category": "work | personal | health | study | other or null",
    "goal_description": "string or null",
    "habit_name": "string or null",
    "focus_duration_min": "number (minutes) or null",
    "mood": "stressed | tired | great | okay | anxious | excited or null"
  },
  "immediate_response": "Brief message to show user while processing (e.g., 'Let me check...')",
  "proactive_hook": "A short coaching signal or null — e.g., 'user_stressed', 'busy_day', 'goal_detected', 'overdue_tasks'"
}

=== RULES ===
1. If user asks about spending/expenses → domain: money, requires_data: true
2. If user is recording something but missing info → needs_clarification: true
3. If user mentions calendar/schedule/meeting → domain: productivity
4. If user mentions tasks/to-do/checklist → domain: todo
5. If user shares personal info ("I'm vegetarian", "I wake up at 6") → intent: update_memory
6. For greetings/casual chat → domain: general, intent: conversation
7. When in doubt about domain, default to general/conversation
8. If context shows pending_question and user's response is a short answer, resolve it using pending context
9. For any intent other than 'conversation', ALWAYS provide an 'immediate_response'
10. If user sounds stressed, set proactive_hook: "user_stressed"
11. If user mentions a goal or aspiration → set proactive_hook: "goal_detected"
12. NEW: Wellness/focus/habit intents don't require data unless querying history

=== EXAMPLES ===

User: "schedule gym tomorrow at 7am"
→ {"intent": "schedule_event", "domain": "productivity", "requires_data": false, "action_data": {"event_title": "gym", "event_time": "07:00", "date": "TOMORROW_DATE"}, "immediate_response": "On it! Scheduling your gym session..."}

User: "how much did I spend today"
→ {"intent": "query_spending", "domain": "money", "requires_data": true, "query_spec": {"entity": "expense", "metric": "sum", "time_range": {"type": "relative", "value": "today"}}, "immediate_response": "Let me check your spending..."}

User: "I'm feeling really overwhelmed with work"
→ {"intent": "log_mood", "domain": "wellness", "requires_data": false, "action_data": {"mood": "stressed"}, "proactive_hook": "user_stressed", "immediate_response": null}

User: "I want to start reading 30 minutes a day"
→ {"intent": "set_goal", "domain": "habit", "requires_data": false, "action_data": {"goal_description": "read 30 minutes daily"}, "proactive_hook": "goal_detected", "immediate_response": "Love that goal! Let me save it..."}

User: "block 9 to 11 for deep work"
→ {"intent": "block_time", "domain": "focus", "requires_data": false, "action_data": {"event_title": "Deep Work Block", "event_time": "09:00", "event_duration": "2h"}, "immediate_response": "Blocking that time for you..."}

User: "I meditated today"
→ {"intent": "track_habit", "domain": "habit", "requires_data": false, "action_data": {"habit_name": "meditation"}, "immediate_response": "Nice! Logging your meditation..."}

User: "I need to focus for an hour"
→ {"intent": "start_focus", "domain": "focus", "requires_data": false, "action_data": {"focus_duration_min": 60}, "immediate_response": "Starting a 60-minute focus session. You've got this!"}

User: "spent 500 on dinner"
→ {"intent": "add_expense", "domain": "money", "requires_data": false, "action_data": {"amount": 500, "category": "food", "description": "dinner", "date": "TODAY_DATE"}, "immediate_response": "Got it! Adding that now..."}

User: "what are my pending tasks"
→ {"intent": "list_todos", "domain": "todo", "requires_data": true, "immediate_response": "Let me pull up your tasks..."}

User: "I'm done with the report"
→ {"intent": "complete_todo", "domain": "todo", "requires_data": false, "action_data": {"task_title": "report"}, "immediate_response": "Awesome, marking it done!"}

User: "I prefer morning workouts"
→ {"intent": "update_memory", "domain": "general"}

User: "hello"
→ {"intent": "conversation", "domain": "general", "requires_data": false}

TODAY'S DATE: """ + datetime.now().strftime("%Y-%m-%d")
