"""
GeneralAgent — RIVA's conversational core and coaching brain.

Handles:
  - conversation (greetings, casual chat, Q&A, advice)
  - update_memory (user shares personal info / preferences)
  - general_question (factual questions)
  - coaching_request (user asks for advice or tips)

NEW in v2:
  - wellness domain: log_mood, request_break
  - focus domain: start_focus, end_focus, block_time, batch_meetings
  - habit domain: set_goal, track_habit, query_habit, update_goal
  - Full RIVA Brain persona integration
  - Mood-aware responses (validates stress before problem-solving)
  - Proactive coaching after every significant interaction
"""
from typing import Dict, Any, List
from openai import OpenAI
import os
import json
from datetime import datetime
from dotenv import load_dotenv

from .base_agent import BaseAgent, AgentResponse
from services.riva_brain import (
    build_riva_system_prompt,
    get_time_context,
    detect_mood,
    get_skills_for_intent,
)

load_dotenv()

# Focus session state (in-memory; for production move to SessionManager)
_FOCUS_SESSIONS: Dict[str, Dict] = {}


class GeneralAgent(BaseAgent):
    """RIVA's conversational core — now a full-spectrum productivity coach."""

    SUPPORTED_INTENTS = [
        # Original
        "conversation",
        "update_memory",
        "general_question",
        # New general
        "coaching_request",
        # Wellness
        "log_mood",
        "request_break",
        "hydration_check",
        "energy_check",
        # Focus
        "start_focus",
        "end_focus",
        "block_time",
        "batch_meetings",
        # Habit
        "set_goal",
        "track_habit",
        "query_habit",
        "update_goal",
    ]

    def __init__(self, openai_client: OpenAI = None, memory_service=None):
        self.client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.memory_service = memory_service

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    @property
    def domain(self) -> str:
        return "general"

    def get_supported_intents(self) -> List[str]:
        return self.SUPPORTED_INTENTS

    async def handle(
        self,
        intent: str,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> AgentResponse:
        """Route to the right handler based on intent."""
        print(f"[GENERAL_AGENT] Handling intent={intent}")

        user_mood = context.get("user_mood", detect_mood(user_input))

        # --- Wellness ---
        if intent in ("log_mood", "request_break"):
            return await self._handle_wellness(intent, user_input, context, memory, user_mood)
        if intent in ("hydration_check", "energy_check"):
            return await self._handle_wellness_check(intent, user_input, context, memory)

        # --- Focus ---
        if intent in ("start_focus", "end_focus", "block_time", "batch_meetings"):
            return await self._handle_focus(intent, user_input, context, memory)

        # --- Habit / Goal ---
        if intent in ("set_goal", "update_goal"):
            return await self._handle_set_goal(user_input, context, memory)
        if intent == "track_habit":
            return await self._handle_track_habit(user_input, context, memory)
        if intent == "query_habit":
            return await self._handle_query_habit(user_input, context, memory)

        # --- Memory update ---
        if intent == "update_memory":
            return await self._handle_memory_update(user_input, context, memory)

        # --- Coaching ---
        if intent == "coaching_request":
            return await self._handle_coaching(user_input, context, memory)

        # --- Default: conversation + general_question ---
        return await self._handle_conversation(user_input, context, memory, user_mood)

    # ------------------------------------------------------------------
    # Wellness handlers
    # ------------------------------------------------------------------

    async def _handle_wellness(
        self, intent: str, user_input: str, context: Dict, memory: Dict, mood: str
    ) -> AgentResponse:
        """Handle mood logging and break requests with empathy-first coaching."""
        time_ctx = get_time_context()
        system_prompt = build_riva_system_prompt(
            mode="coaching",
            memory=memory,
            time_ctx=time_ctx,
            extra_skills=["wellness", "energy"],
        )

        mood_instructions = {
            "stressed": (
                "The user is stressed. First validate their feelings with genuine empathy (1 sentence). "
                "Then offer ONE practical, small action that can immediately reduce load. "
                "Do NOT give a list of tips. Do NOT say 'I understand' — show it through your response."
            ),
            "positive": (
                "The user is feeling good. Match their energy and celebrate it briefly. "
                "Then offer one small nudge to channel this energy productively."
            ),
            "neutral": (
                "Respond with warmth and offer a grounding question or a tiny actionable suggestion."
            ),
        }.get(mood, "Respond with warmth and offer a grounding question.")

        if intent == "request_break":
            extra = (
                "The user is asking for a break. Enthusiastically endorse it. "
                "Suggest a specific 10-15 minute break activity based on time of day. "
                "Optionally mention they'll come back sharper."
            )
            mood_instructions = extra

        messages = [
            {"role": "system", "content": system_prompt + "\n\n" + mood_instructions},
        ]

        # Add recent conversation for continuity
        for msg in context.get("recent_messages", [])[-4:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_input})

        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.75,
                max_tokens=200,
            )
            response_text = resp.choices[0].message.content

            # Memory: store mood signal
            memory_updates = [{
                "type": "habit",
                "key": f"mood_{datetime.now().strftime('%Y-%m-%d')}",
                "value": mood,
                "confidence": 0.85,
            }]

            return AgentResponse(
                response=response_text,
                memory_updates=memory_updates,
                metadata={"intent": intent, "mood": mood},
            )
        except Exception as e:
            print(f"[GENERAL_AGENT] Wellness error: {e}")
            if mood == "stressed":
                return AgentResponse(
                    response="That sounds tough — let's take a breath. What's the one thing that would help most right now?"
                )
            return AgentResponse(response="You deserve a moment to recharge. Take it! 🌿")

    async def _handle_wellness_check(
        self, intent: str, user_input: str, context: Dict, memory: Dict
    ) -> AgentResponse:
        """Handle hydration and energy checks."""
        time_ctx = get_time_context()
        hour = time_ctx["hour"]

        if intent == "hydration_check":
            if hour < 10:
                return AgentResponse(
                    response="Good reminder! Aim for a glass of water first thing in the morning. "
                    "Hydration boosts focus by up to 30%. 💧"
                )
            return AgentResponse(
                response="Great habit! Keep sipping — try to hit 8 glasses by end of day. 💧"
            )

        if intent == "energy_check":
            energy = time_ctx["energy_level"]
            period = time_ctx["period"]
            suggestions = {
                "high": f"Your energy is likely at its peak right now ({period}). "
                        "Perfect time for your hardest task!",
                "medium": f"Mid-{period} energy — solid for meetings, reviews, and planning.",
                "medium-low": "Post-lunch dip is natural. Try a 10-min walk or cold water "
                             "to bounce back.",
                "low": "Evening mode — wind down with lighter tasks. Prep tomorrow's plan "
                       "and log off at a decent hour.",
            }
            return AgentResponse(
                response=suggestions.get(energy, "Energy varies — listen to your body and adjust!")
            )

        return AgentResponse(response="Listen to your body — it knows what it needs!")

    # ------------------------------------------------------------------
    # Focus handlers
    # ------------------------------------------------------------------

    async def _handle_focus(
        self, intent: str, user_input: str, context: Dict, memory: Dict
    ) -> AgentResponse:
        """Handle focus sessions and time blocking."""
        user_id = context.get("user_id", "unknown")
        time_ctx = get_time_context()
        action_data = context.get("action_data", {})

        if intent == "start_focus":
            duration_min = action_data.get("focus_duration_min", 60)
            _FOCUS_SESSIONS[user_id] = {
                "start": datetime.now().isoformat(),
                "duration_min": duration_min,
            }
            hr = duration_min // 60
            mn = duration_min % 60
            dur_str = f"{hr}h {mn}min" if hr else f"{mn} min"
            tips = [
                "Close unneeded tabs, mute notifications.",
                "Have water nearby.",
                "Pick ONE task to focus on.",
            ]
            tip = tips[datetime.now().minute % len(tips)]
            return AgentResponse(
                response=f"Focus session started! 🎯 You've got {dur_str} of uninterrupted time. "
                         f"Quick tip: {tip}",
                actions_taken=["focus_session_started"],
                metadata={"focus_duration_min": duration_min},
            )

        if intent == "end_focus":
            session = _FOCUS_SESSIONS.pop(user_id, None)
            if session:
                elapsed = (datetime.now() - datetime.fromisoformat(session["start"]))
                elapsed_min = int(elapsed.total_seconds() / 60)
                return AgentResponse(
                    response=f"Focus session complete! 💪 You worked for {elapsed_min} minutes. "
                    f"Take a 5-10 min break — you've earned it.",
                    actions_taken=["focus_session_ended"],
                    memory_updates=[{
                        "type": "habit",
                        "key": f"focus_{datetime.now().strftime('%Y-%m-%d')}",
                        "value": f"{elapsed_min} minutes",
                        "confidence": 1.0,
                    }],
                )
            return AgentResponse(response="No active focus session found, but take a break anyway — you deserve one! 🌿")

        if intent == "block_time":
            event_title = action_data.get("event_title", "Deep Work Block")
            event_time = action_data.get("event_time", "09:00")
            duration = action_data.get("event_duration", "2h")
            return AgentResponse(
                response=f"Got it — blocking '{event_title}' from {event_time} for {duration}. "
                         f"Your calendar will show this as protected time. 🔒",
                actions_taken=["time_blocked"],
                background_tasks=[{
                    "type": "create_event",
                    "payload": {
                        "title": event_title,
                        "start_time": event_time,
                        "duration": duration,
                        "description": "Protected deep work block — created by RIVA",
                    },
                }],
            )

        if intent == "batch_meetings":
            return AgentResponse(
                response="Smart move! Batching meetings is one of the best productivity hacks. "
                         "I'd recommend designating Tuesday and Thursday afternoons as your meeting slots. "
                         "Want me to block mornings as focus time?",
                metadata={"suggestion": "batch_meetings"},
            )

        return AgentResponse(response="I'll help you protect your focus time. What works best for you?")

    # ------------------------------------------------------------------
    # Habit / Goal handlers
    # ------------------------------------------------------------------

    async def _handle_set_goal(
        self, user_input: str, context: Dict, memory: Dict
    ) -> AgentResponse:
        """Help the user define and save a concrete goal."""
        system_prompt = build_riva_system_prompt(
            mode="coaching",
            memory=memory,
            time_ctx=get_time_context(),
            extra_skills=["habits", "gtd"],
        )

        goal_prompt = """The user has stated a new goal or aspiration. Help them turn it into a concrete implementation intention using this format:
"I will [specific action] at [time] on [days] in [location/context]."

Then offer to:
1. Add it as a recurring to-do item.
2. Set a reminder.

Keep your response to 3 sentences max. Be enthusiastic and specific.
"""
        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt + "\n\n" + goal_prompt},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.7,
                max_tokens=200,
            )
            response_text = resp.choices[0].message.content

            # Extract goal for memory
            memory_updates = [{
                "type": "habit",
                "key": f"goal_{datetime.now().strftime('%Y%m%d%H%M')}",
                "value": user_input,
                "confidence": 0.9,
            }]

            return AgentResponse(
                response=response_text,
                memory_updates=memory_updates,
                actions_taken=["goal_saved"],
            )
        except Exception as e:
            print(f"[GENERAL_AGENT] Set goal error: {e}")
            return AgentResponse(
                response="That's a great goal! Let's make it stick — want me to add a daily reminder for it?"
            )

    async def _handle_track_habit(
        self, user_input: str, context: Dict, memory: Dict
    ) -> AgentResponse:
        """Log a habit occurrence and celebrate it."""
        action_data = context.get("action_data", {})
        habit_name = action_data.get("habit_name", "your habit")

        celebrations = [
            f"🎉 Yes! Logged '{habit_name}'. Consistency is everything — keep going!",
            f"✅ '{habit_name}' logged. Every rep counts. You're building something great!",
            f"🔥 Nice work on '{habit_name}'! Streaks start with moments like these.",
        ]
        message = celebrations[datetime.now().second % len(celebrations)]

        memory_updates = [{
            "type": "habit",
            "key": f"habit_log_{habit_name}_{datetime.now().strftime('%Y-%m-%d')}",
            "value": {"logged": True, "date": datetime.now().strftime("%Y-%m-%d")},
            "confidence": 1.0,
        }]

        return AgentResponse(
            response=message,
            memory_updates=memory_updates,
            actions_taken=["habit_logged"],
        )

    async def _handle_query_habit(
        self, user_input: str, context: Dict, memory: Dict
    ) -> AgentResponse:
        """Summarise habit progress from memory."""
        habits = memory.get("habits", [])
        habit_logs = [h for h in habits if h.get("key", "").startswith("habit_log_")]

        if not habit_logs:
            return AgentResponse(
                response="I don't have any habit logs yet. Tell me about a habit you've been working on "
                "and I'll start tracking it for you!"
            )

        # Group by habit name
        from collections import defaultdict
        by_habit: Dict[str, int] = defaultdict(int)
        for h in habit_logs:
            # Key format: habit_log_{name}_{date}
            parts = h.get("key", "").split("_")
            if len(parts) >= 3:
                name = "_".join(parts[2:-1])  # everything between habit_log_ and _date
                by_habit[name] += 1

        if not by_habit:
            return AgentResponse(response="No habit history found yet — start logging and I'll track your streaks!")

        summary_parts = []
        for name, count in sorted(by_habit.items(), key=lambda x: -x[1])[:5]:
            summary_parts.append(f"• {name.replace('_', ' ').title()}: {count} log(s)")

        return AgentResponse(
            response="Here's your habit summary:\n" + "\n".join(summary_parts)
            + "\n\nConsistency is the key — keep it up! 💪",
            data={"habit_counts": dict(by_habit)},
        )

    # ------------------------------------------------------------------
    # Coaching handler
    # ------------------------------------------------------------------

    async def _handle_coaching(
        self, user_input: str, context: Dict, memory: Dict
    ) -> AgentResponse:
        """Handle explicit requests for advice, tips, or coaching."""
        system_prompt = build_riva_system_prompt(
            mode="coaching",
            memory=memory,
            time_ctx=get_time_context(),
            extra_skills=["gtd", "priority", "energy", "habits", "wellness"],
        )

        coaching_instruction = """The user is asking for advice or coaching. Give ONE clear, specific, actionable insight.
Do not give a numbered list — weave the advice into a natural, warm response.
Draw on productivity science (GTD, time-blocking, deep work, habit formation) but speak simply.
End with a question that helps the user take the first small step.
Max 3 sentences."""

        messages = [
            {"role": "system", "content": system_prompt + "\n\n" + coaching_instruction},
        ]
        for msg in context.get("recent_messages", [])[-4:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_input})

        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=250,
            )
            return AgentResponse(response=resp.choices[0].message.content)
        except Exception as e:
            print(f"[GENERAL_AGENT] Coaching error: {e}")
            return AgentResponse(
                response="The best first step is always the smallest one. What's one tiny thing you can do right now?"
            )

    # ------------------------------------------------------------------
    # Conversation handler
    # ------------------------------------------------------------------

    async def _handle_conversation(
        self,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
        user_mood: str = "neutral",
    ) -> AgentResponse:
        """Handle general conversation with personality and proactive coaching."""
        time_ctx = get_time_context()
        extra_skills = get_skills_for_intent("conversation")

        system_prompt = build_riva_system_prompt(
            mode="conversation",
            memory=memory,
            time_ctx=time_ctx,
            extra_skills=extra_skills,
        )

        # Mood-aware instruction addendum
        if user_mood == "stressed":
            system_prompt += "\n\nIMPORTANT: The user seems stressed. Lead with empathy. Validate first, suggest second."
        elif user_mood == "positive":
            system_prompt += "\n\nThe user is in a great mood. Match their energy!"

        messages = [{"role": "system", "content": system_prompt}]
        for msg in context.get("recent_messages", [])[-5:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_input})

        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.72,
                max_tokens=300,
            )
            response_text = resp.choices[0].message.content
            memory_updates = await self._detect_memory_updates(user_input, response_text)

            return AgentResponse(
                response=response_text,
                memory_updates=memory_updates,
            )
        except Exception as e:
            print(f"[GENERAL_AGENT] Conversation error: {e}")
            return AgentResponse(
                response="I'm here with you! Could you say that again?",
                metadata={"error": str(e)},
            )

    # ------------------------------------------------------------------
    # Memory update handler
    # ------------------------------------------------------------------

    async def _handle_memory_update(
        self,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> AgentResponse:
        """Handle explicit memory updates."""
        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._memory_extraction_prompt()},
                    {"role": "user", "content": user_input},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=300,
            )
            result = json.loads(resp.choices[0].message.content)

            memory_updates = result.get("memory_updates", [])
            response_text = result.get(
                "response", "Noted! I'll keep that in mind."
            )

            return AgentResponse(
                response=response_text,
                memory_updates=memory_updates,
            )
        except Exception as e:
            print(f"[GENERAL_AGENT] Memory update error: {e}")
            return AgentResponse(response="I'll remember that!")

    # ------------------------------------------------------------------
    # Passive memory detection
    # ------------------------------------------------------------------

    async def _detect_memory_updates(
        self, user_input: str, response_text: str
    ) -> List[Dict[str, Any]]:
        """Passively detect memory-worthy statements during conversation."""
        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._passive_memory_prompt()},
                    {"role": "user", "content": user_input},
                ],
                response_format={"type": "json_object"},
                temperature=0.15,
                max_tokens=250,
            )
            result = json.loads(resp.choices[0].message.content)
            updates = result.get("memory_updates", [])
            return [u for u in updates if u.get("confidence", 0) >= 0.8]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    def _memory_extraction_prompt(self) -> str:
        return """You are RIVA's memory extractor. The user has shared personal information.
Extract it into structured memory updates and craft a warm acknowledgement.

RETURN THIS JSON:
{
  "response": "Natural acknowledgement (e.g. 'Noted! I'll remember that.')",
  "memory_updates": [
    {
      "type": "preference | habit | fact | constraint | goal",
      "key": "descriptive_key (e.g. 'diet', 'wake_time', 'monthly_budget', 'goal_fitness')",
      "value": "the value",
      "confidence": 0.0-1.0
    }
  ]
}

EXAMPLES:
- "I'm vegetarian" → fact: diet=vegetarian (confidence 0.95)
- "I usually wake up at 6am" → habit: wake_time=6am (confidence 0.85)
- "I prefer morning meetings" → preference: meeting_time=morning (confidence 0.90)
- "I want to run a 5K" → goal: goal_running=5K race (confidence 0.90)
- "My budget is 50k a month" → constraint: monthly_budget=50000 (confidence 0.95)"""

    def _passive_memory_prompt(self) -> str:
        return """Analyze this user message. Extract any personal facts, preferences, habits, or goals.
Only extract high-confidence items (≥0.8). Return empty array if nothing notable.

RETURN THIS JSON:
{
  "memory_updates": [
    {
      "type": "preference | habit | fact | goal",
      "key": "descriptive_key",
      "value": "the value",
      "confidence": 0.0-1.0
    }
  ]
}

Only extract with confidence >= 0.8."""
