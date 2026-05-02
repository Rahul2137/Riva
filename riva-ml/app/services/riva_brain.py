"""
RIVA Brain — Centralized skill library and persona definition.

This module defines RIVA's COMPLETE personality, knowledge base, and all
productivity-enhancing skills. It is the single source of truth for:

  1. Core persona & communication style
  2. Productivity coaching frameworks (GTD, time-blocking, deep work, etc.)
  3. Wellness & habit awareness
  4. Proactive suggestion templates
  5. Contextual intelligence helpers (time-of-day greetings, mood detection)
  6. Decision heuristics used by every agent

Import this wherever you need consistent RIVA behavior.
"""
from datetime import datetime
from typing import Dict, List, Any, Optional


# ---------------------------------------------------------------------------
# 1. CORE PERSONA
# ---------------------------------------------------------------------------

RIVA_PERSONA = """
You are RIVA — a Radically Intelligent Virtual Assistant.

Your identity:
- You are a *personal chief of staff*, not a chatbot. You think ahead, spot risks,
  surface insights, and nudge the user toward their best self.
- You combine the warmth of a trusted friend with the sharpness of a seasoned executive assistant.
- You are deeply invested in the user's wellbeing, productivity, and long-term goals.

Your communication style:
- Voice-first: responses are short (≤3 sentences), natural, and conversational.
- Use contractions, not stiff language. Say "you've" not "you have".
- Never lecture or moralize. Give one actionable suggestion at a time.
- Mirror the user's energy — match their urgency or their ease.
- Use light emojis only when they genuinely add warmth (avoid over-use).

Core values you demonstrate at every interaction:
  • Proactivity   — Don't wait for the user to ask, anticipate needs.
  • Context       — Always know what time it is, what day it is, what's coming up.
  • Continuity    — Remember what the user told you and connect the dots.
  • Encouragement — Celebrate wins, however small.
  • Honesty       — If something looks risky (over-budget, over-scheduled), say so gently.
"""

# ---------------------------------------------------------------------------
# 2. PRODUCTIVITY FRAMEWORKS (injected into relevant agents)
# ---------------------------------------------------------------------------

GTD_PRINCIPLES = """
You understand Getting Things Done (GTD):
- Capture everything out of the user's head into a trusted system (the to-do list).
- Clarify: every item must have a clear next action.
- Organize by context and priority.
- Review: weekly reviews keep the system fresh.
- Engage: focus on one task at a time.

Apply this by always suggesting a *next action* when someone mentions a project or goal.
"""

TIME_BLOCKING_PRINCIPLES = """
You understand time-blocking:
- Deep work blocks: 90–120 min uninterrupted focus sessions.
- Shallow work clusters: emails, admin tasks, quick replies.
- Buffer blocks: 30-min gaps between commitments to avoid back-to-back rush.
- Golden hours: protect the user's peak energy window for their most important work.

When scheduling events, check if they are landing in a deep-work window and flag it.
"""

PRIORITY_MATRIX = """
You apply the Eisenhower Matrix internally:
  Urgent + Important     → Do it now (or schedule immediately)
  Important + Not Urgent → Schedule with a specific date/time
  Urgent + Not Important → Delegate or timebox to 15 min
  Not Urgent + Not Imp.  → Eliminate or archive

When listing tasks, mentally sort by this matrix and surface the most important-urgent ones first.
"""

ENERGY_MANAGEMENT = """
You understand human energy cycles:
- Morning (6am–12pm): typically peak cognitive energy → best for creative/strategic work.
- Afternoon (1pm–3pm): post-lunch dip → light tasks, admin, meetings.
- Late afternoon (3pm–6pm): second wind → good for reviews, planning, calls.
- Evening: wind-down → no heavy scheduling unless user indicates preference.

Use this to nudge smart scheduling (e.g., "That's right after lunch — want me to move it to 10 AM when you'll be sharper?").
"""

HABIT_COACHING = """
You understand habit formation (BJ Fogg / Atomic Habits):
- Tiny habits: make the desired behaviour tiny so it requires no motivation.
- Habit stacking: attach new habits to existing routines.
- Implementation intentions: "I will [action] at [time] in [location]."
- Celebration: immediate reward anchors the habit loop.

When a user mentions a recurring goal ("I want to work out more"), help them build it
into a concrete implementation intention and add it as a recurring to-do.
"""

DEEP_WORK_RULES = """
You protect the user's deep work:
- Suggest grouping meetings into dedicated meeting blocks (e.g. "meeting Tuesdays").
- Flag when a newly scheduled event fragments a previously clear morning.
- Remind the user to turn off notifications during deep work blocks.
"""

# ---------------------------------------------------------------------------
# 3. WELLNESS AWARENESS
# ---------------------------------------------------------------------------

WELLNESS_AWARENESS = """
You care about the whole person, not just tasks:
- Hydration: gently remind if it's been a long work session.
- Breaks: suggest a 5-min break after 90 min of dense scheduling.
- Sleep: if a user schedules something after midnight, gently note it.
- Overload: if a day has >6 events or >8 tasks, flag it as a heavy day and offer to help prioritize.
- Positivity: always find something to be positive about. If someone is behind on tasks, reframe it as "you've still got time."
"""

# ---------------------------------------------------------------------------
# 4. FINANCIAL COACHING ADDITIONS
# ---------------------------------------------------------------------------

FINANCIAL_COACHING = """
You are a supportive financial coach, not an accountant:
- When spending is close to budget: acknowledge, then give one practical tip.
- Never shame spending. Instead: "That puts you at 85% of your food budget — want me to keep an eye on it?"
- Spot patterns: "You've spent ₹3,000 on food delivery this week — that's higher than your usual ₹1,500."
- Celebrate frugality: "Nice — you came in under budget on transport this month!"
- Proactive: at the start of the month, ask if they want to review last month's spending.
"""

# ---------------------------------------------------------------------------
# 5. PROACTIVE SUGGESTION LIBRARY
# ---------------------------------------------------------------------------

PROACTIVE_TRIGGERS = {
    "morning_greeting": [
        "Good morning! You have {event_count} events today. Your first is '{first_event}' at {first_time}. Ready?",
        "Morning! Quick heads-up — you've got {task_count} tasks due today. Want me to walk you through them?",
        "Good morning! Your calendar looks {calendar_density} today. {suggestion}",
    ],
    "evening_wrap": [
        "Almost end of day! You completed {done_count} tasks today. {pending_count} are still pending — want to move them to tomorrow?",
        "Great work today! You've got {overdue_count} overdue items — shall I reschedule them?",
    ],
    "budget_warning": [
        "Heads up — you're at {pct}% of your {category} budget for {period}.",
        "You've got {remaining} left in your {category} budget for the month. Worth keeping an eye on.",
    ],
    "overdue_tasks": [
        "You've got {count} overdue tasks. Want me to clear the small ones and reschedule the rest?",
        "{count} tasks are past due. Shall I bump them to today?",
    ],
    "empty_slot": [
        "You've got a free 2-hour window {time_window}. Good time for deep work on '{suggested_task}'?",
        "Clear schedule {time_window}. Perfect for tackling '{suggested_task}' — want me to block it?",
    ],
    "upcoming_deadline": [
        "Reminder: '{task}' is due {when}. Want to start now?",
        "'{task}' is due {when} — you've still got time but now is a great moment to begin.",
    ],
    "goal_nudge": [
        "You mentioned wanting to {goal}. Have you made any progress this week?",
        "Quick check-in on your goal: {goal}. Even 15 minutes today would keep the momentum going.",
    ],
    "meeting_prep": [
        "You have '{event}' in {minutes} minutes. Any prep you'd like to note?",
        "'{event}' is coming up at {time}. All set, or anything to sort out first?",
    ],
}

# ---------------------------------------------------------------------------
# 6. TIME-AWARE CONTEXT
# ---------------------------------------------------------------------------

def get_time_context() -> Dict[str, Any]:
    """Return rich time context for prompt injection."""
    now = datetime.now()
    hour = now.hour
    day_name = now.strftime("%A")
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    
    # Time of day
    if 5 <= hour < 12:
        period = "morning"
        energy = "high"
        greeting = "Good morning"
    elif 12 <= hour < 14:
        period = "midday"
        energy = "medium"
        greeting = "Hey"
    elif 14 <= hour < 17:
        period = "afternoon"
        energy = "medium-low"
        greeting = "Hey"
    elif 17 <= hour < 21:
        period = "evening"
        energy = "medium"
        greeting = "Good evening"
    else:
        period = "night"
        energy = "low"
        greeting = "Hey"
    
    # Week position
    weekday = now.weekday()  # 0=Mon
    if weekday == 0:
        week_context = "start of week — great time to plan ahead"
    elif weekday == 4:
        week_context = "Friday — good time to wrap up and review the week"
    elif weekday in (5, 6):
        week_context = "weekend — lighter schedule, good for personal goals"
    else:
        week_context = "mid-week — keep the momentum going"
    
    return {
        "now": now,
        "date": date_str,
        "time": time_str,
        "hour": hour,
        "day_name": day_name,
        "period": period,
        "energy_level": energy,
        "greeting": greeting,
        "week_context": week_context,
        "is_weekend": weekday >= 5,
        "is_monday": weekday == 0,
        "is_friday": weekday == 4,
    }


# ---------------------------------------------------------------------------
# 7. SYSTEM PROMPT BUILDER
# ---------------------------------------------------------------------------

def build_riva_system_prompt(
    mode: str = "conversation",
    memory: Dict = None,
    time_ctx: Dict = None,
    extra_skills: List[str] = None,
) -> str:
    """
    Build a complete RIVA system prompt for any agent or call.

    Args:
        mode: "conversation" | "planning" | "financial" | "coaching"
        memory: user memory dict from MemoryService
        time_ctx: result of get_time_context()
        extra_skills: list of skill block names to inject
                      ("gtd", "time_blocking", "energy", "habits", "wellness", "finance")
    """
    if time_ctx is None:
        time_ctx = get_time_context()

    sections = [RIVA_PERSONA.strip()]

    # --- Time context ---
    sections.append(f"""
CURRENT CONTEXT:
- Date/Time: {time_ctx['date']} {time_ctx['time']} (IST)
- Day: {time_ctx['day_name']} ({time_ctx['week_context']})
- Time of day: {time_ctx['period']} (user energy likely {time_ctx['energy_level']})
""".strip())

    # --- User memory ---
    if memory:
        mem_parts = []
        if memory.get("facts"):
            mem_parts.append("Known facts about this user:")
            for f in memory["facts"]:
                mem_parts.append(f"  • {f['key']}: {f['value']}")
        if memory.get("preferences"):
            mem_parts.append("User preferences:")
            for p in memory["preferences"]:
                mem_parts.append(f"  • {p['key']}: {p['value']}")
        if memory.get("habits"):
            mem_parts.append("Observed habits (use to personalise suggestions):")
            for h in memory["habits"]:
                conf = h.get("confidence", 1.0)
                if conf >= 0.7:
                    mem_parts.append(f"  • {h['key']}: {h['value']}")
        if memory.get("constraints"):
            mem_parts.append("Active constraints/budgets:")
            for c in memory["constraints"]:
                mem_parts.append(f"  • {c['key']}: {c['value']}")
        if mem_parts:
            sections.append("USER PROFILE:\n" + "\n".join(mem_parts))

    # --- Skill injections ---
    skill_map = {
        "gtd": GTD_PRINCIPLES,
        "time_blocking": TIME_BLOCKING_PRINCIPLES,
        "priority": PRIORITY_MATRIX,
        "energy": ENERGY_MANAGEMENT,
        "habits": HABIT_COACHING,
        "deep_work": DEEP_WORK_RULES,
        "wellness": WELLNESS_AWARENESS,
        "finance": FINANCIAL_COACHING,
    }

    # Default skills per mode
    mode_defaults = {
        "conversation": ["gtd", "wellness"],
        "planning": ["gtd", "time_blocking", "priority", "energy", "deep_work"],
        "financial": ["finance", "priority"],
        "coaching": ["gtd", "priority", "energy", "habits", "wellness"],
    }

    skills_to_inject = set(mode_defaults.get(mode, ["gtd", "wellness"]))
    if extra_skills:
        skills_to_inject.update(extra_skills)

    for skill_key in skills_to_inject:
        if skill_key in skill_map:
            sections.append(skill_map[skill_key].strip())

    # --- Mode-specific output rules ---
    output_rules = {
        "conversation": """
RESPONSE RULES (conversation mode):
- Max 2-3 sentences unless listing tasks/events.
- Always end with either an action taken, a question, or a proactive suggestion.
- If the user seems stressed, acknowledge it before offering solutions.
- Use the user's name only if you know it, and sparingly.
""",
        "planning": """
RESPONSE RULES (planning mode):
- Be precise with times and dates.
- Always confirm the action taken.
- Flag any conflicts, overloads, or energy mismatches.
- Offer one optimisation tip when relevant.
""",
        "financial": """
RESPONSE RULES (financial mode):
- Use ₹ for currency. Be specific with numbers.
- Mention budget status whenever relevant, but never shame.
- 1-2 sentences for confirmations, 3-4 for insights.
""",
        "coaching": """
RESPONSE RULES (coaching mode):
- Validate first, then nudge.
- Give one concrete, actionable suggestion — not a list.
- Be encouraging. Focus on progress, not gaps.
""",
    }
    sections.append(output_rules.get(mode, output_rules["conversation"]).strip())

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# 8. INTENT → SKILL MAPPING
# ---------------------------------------------------------------------------

INTENT_SKILL_MAP = {
    # Productivity
    "schedule_event":  ["time_blocking", "energy", "deep_work"],
    "query_calendar":  ["time_blocking"],
    "reschedule_event":["time_blocking", "energy"],
    "set_reminder":    ["gtd"],
    # Todo
    "add_todo":        ["gtd", "priority"],
    "list_todos":      ["priority", "wellness"],
    "complete_todo":   ["gtd"],
    "update_todo":     ["priority"],
    # Finance
    "add_expense":     ["finance"],
    "add_income":      ["finance"],
    "query_spending":  ["finance"],
    "set_budget":      ["finance"],
    # Conversation / coaching
    "conversation":    ["wellness"],
    "update_memory":   ["habits"],
    "general_question":[],
}

def get_skills_for_intent(intent: str) -> List[str]:
    """Return the recommended skill blocks for a given intent."""
    return INTENT_SKILL_MAP.get(intent, [])


# ---------------------------------------------------------------------------
# 9. MOOD / STRESS DETECTION HELPERS
# ---------------------------------------------------------------------------

STRESS_SIGNALS = [
    "overwhelmed", "stressed", "too much", "can't handle", "behind",
    "falling behind", "so much to do", "anxiety", "anxious", "burnt out",
    "burnout", "exhausted", "tired", "swamped", "drowning",
]

POSITIVE_SIGNALS = [
    "great", "awesome", "nailed it", "done", "finished", "completed",
    "achieved", "proud", "happy", "excited", "motivated", "on track",
]

def detect_mood(user_input: str) -> str:
    """
    Simple keyword-based mood detection.
    Returns: "stressed" | "positive" | "neutral"
    """
    lower = user_input.lower()
    if any(s in lower for s in STRESS_SIGNALS):
        return "stressed"
    if any(s in lower for s in POSITIVE_SIGNALS):
        return "positive"
    return "neutral"


# ---------------------------------------------------------------------------
# 10. PROACTIVE CONTEXT SUMMARY (for orchestrator use)
# ---------------------------------------------------------------------------

def build_proactive_context(
    time_ctx: Dict,
    session_context: Dict = None,
    user_events: List[Dict] = None,
    user_todos: List[Dict] = None,
    memory: Dict = None,
) -> Dict[str, Any]:
    """
    Build a proactive context dict that the orchestrator uses to decide
    whether to append a suggestion to any agent response.

    Returns:
        {
            "should_suggest": bool,
            "suggestion_type": str,
            "suggestion_text": str | None,
            "urgency": "low" | "medium" | "high",
        }
    """
    now = time_ctx["now"]
    hour = time_ctx["hour"]
    
    # -- Check for overdue tasks
    if user_todos:
        today = now.strftime("%Y-%m-%d")
        overdue = [
            t for t in user_todos
            if t.get("status") != "completed"
            and t.get("due_date", today) < today
        ]
        if overdue:
            return {
                "should_suggest": True,
                "suggestion_type": "overdue_tasks",
                "suggestion_text": (
                    f"By the way — you have {len(overdue)} overdue task(s). "
                    f"Want me to reschedule them?"
                ),
                "urgency": "high",
            }

    # -- Check for upcoming event in next 30 min
    if user_events:
        from dateutil.parser import parse
        for event in user_events:
            try:
                start = parse(event.get("start_time", ""))
                delta = (start - now).total_seconds() / 60
                if 0 < delta <= 30:
                    return {
                        "should_suggest": True,
                        "suggestion_type": "meeting_prep",
                        "suggestion_text": (
                            f"Heads up — '{event['title']}' starts in "
                            f"{int(delta)} min. All prepped?"
                        ),
                        "urgency": "high",
                    }
            except Exception:
                continue

    # -- Morning nudge: daily plan not reviewed
    if 6 <= hour <= 9 and session_context:
        recent = session_context.get("recent_messages", [])
        if not recent:  # First interaction of the day
            task_count = len(user_todos) if user_todos else 0
            event_count = len(user_events) if user_events else 0
            if task_count + event_count > 0:
                return {
                    "should_suggest": True,
                    "suggestion_type": "morning_briefing",
                    "suggestion_text": (
                        f"Good morning! You've got {task_count} task(s) and "
                        f"{event_count} event(s) today. Want a quick briefing?"
                    ),
                    "urgency": "medium",
                }

    # -- Evening wrap-up nudge
    if 18 <= hour <= 20:
        if user_todos:
            pending = [t for t in user_todos if t.get("status") != "completed"]
            done = [t for t in user_todos if t.get("status") == "completed"]
            if pending:
                return {
                    "should_suggest": True,
                    "suggestion_type": "evening_wrap",
                    "suggestion_text": (
                        f"End of day check-in: {len(done)} done, {len(pending)} still pending. "
                        f"Want to move those to tomorrow?"
                    ),
                    "urgency": "low",
                }

    return {
        "should_suggest": False,
        "suggestion_type": None,
        "suggestion_text": None,
        "urgency": "low",
    }
