"""
ProactiveEngine — RIVA's proactive intelligence layer.

This engine runs AFTER every agent response and decides whether to append
a smart, context-aware suggestion. It is the mechanism that makes RIVA
feel alive and genuinely helpful — not just reactive.

Key capabilities:
  1. Daily briefing generator (morning summary)
  2. Overdue task alerts
  3. Meeting prep reminders (upcoming in <30 min)
  4. Budget proximity warnings
  5. Schedule optimisation hints (fragmented deep work, overloaded day)
  6. Habit & goal check-ins
  7. Energy-aware scheduling advice

The engine is CHEAP — it uses no LLM call. It is pure heuristic logic
that runs in under 1 ms, so it adds zero latency.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import json


class ProactiveEngine:
    """
    Analyses the user's current context and returns a proactive suggestion
    (or None) to append to any agent response.

    Usage:
        engine = ProactiveEngine()
        suggestion = await engine.evaluate(
            user_id=...,
            session_context=...,
            memory_context=...,
            todos=...,       # optional: List[Dict] from TodoService
            events=...,      # optional: List[Dict] from CalendarService
        )
        if suggestion:
            agent_response.response += f" — {suggestion}"
    """

    # How many minutes before an event to trigger a prep reminder
    MEETING_PREP_WINDOW_MIN = 30

    # Overload thresholds
    OVERLOAD_EVENTS_PER_DAY = 6
    OVERLOAD_TASKS_PER_DAY = 8

    # Budget warning threshold (percentage)
    BUDGET_WARNING_PCT = 0.80

    def __init__(self):
        self._last_suggestions: Dict[str, Tuple[str, datetime]] = {}
        # key=user_id, value=(suggestion_type, timestamp) — prevent spam

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        user_id: str,
        session_context: Dict[str, Any],
        memory_context: Dict[str, Any] = None,
        todos: List[Dict] = None,
        events: List[Dict] = None,
        intent: str = None,
        last_agent_response: str = "",
    ) -> Optional[str]:
        """
        Run all proactive checks and return the highest-priority suggestion.

        Returns:
            A short suggestion string (≤1 sentence) to append to the response,
            or None if there is nothing useful to say.
        """
        now = datetime.now()
        memory_context = memory_context or {}
        session_context = session_context or {}
        todos = todos or []
        events = events or []

        # Collect all candidate suggestions with (priority, text)
        candidates: List[Tuple[int, str, str]] = []  # (priority, type, text)

        # ----- Check 1: Upcoming meeting prep -----
        prep = self._check_meeting_prep(events, now)
        if prep:
            candidates.append((10, "meeting_prep", prep))

        # ----- Check 2: Overdue tasks -----
        overdue = self._check_overdue_tasks(todos, now)
        if overdue:
            candidates.append((9, "overdue_tasks", overdue))

        # ----- Check 3: Today's overload -----
        overload = self._check_day_overload(todos, events, now)
        if overload:
            candidates.append((7, "day_overload", overload))

        # ----- Check 4: Budget proximity -----
        budget_warn = self._check_budget_proximity(memory_context)
        if budget_warn:
            candidates.append((8, "budget_warning", budget_warn))

        # ----- Check 5: Morning briefing -----
        briefing = self._check_morning_briefing(
            session_context, todos, events, now
        )
        if briefing:
            candidates.append((6, "morning_briefing", briefing))

        # ----- Check 6: Evening wrap-up -----
        wrap = self._check_evening_wrap(todos, events, now, session_context)
        if wrap:
            candidates.append((5, "evening_wrap", wrap))

        # ----- Check 7: Goal/habit check-in -----
        habit = self._check_habit_nudge(memory_context, now)
        if habit:
            candidates.append((4, "habit_nudge", habit))

        # ----- Check 8: Empty time slot nudge -----
        slot = self._check_free_slot(todos, events, now)
        if slot:
            candidates.append((3, "free_slot", slot))

        if not candidates:
            return None

        # Pick the highest-priority suggestion not shown recently
        candidates.sort(key=lambda x: -x[0])
        for priority, stype, text in candidates:
            if self._is_cool_down_ok(user_id, stype, now):
                self._record_suggestion(user_id, stype, now)
                return text

        return None

    # ------------------------------------------------------------------
    # Generators — Daily briefing (can be called directly)
    # ------------------------------------------------------------------

    def generate_daily_briefing(
        self,
        todos: List[Dict],
        events: List[Dict],
        now: datetime = None,
    ) -> str:
        """
        Generate a full morning briefing string.
        Call this explicitly on first interaction of the day.
        """
        now = now or datetime.now()
        today = now.strftime("%Y-%m-%d")

        today_events = self._events_for_date(events, today)
        today_tasks = [
            t for t in todos
            if t.get("due_date", "") == today and t.get("status") != "completed"
        ]
        high_priority = [t for t in today_tasks if t.get("priority") == "high"]

        parts = [f"Here's your day at a glance — it's {now.strftime('%A, %B %d')}."]

        if today_events:
            first_event = today_events[0]
            first_time = self._format_time(first_event.get("start_time", ""))
            parts.append(
                f"You have {len(today_events)} event(s), starting with "
                f"'{first_event.get('title', 'your first event')}' at {first_time}."
            )
        else:
            parts.append("Your calendar is clear today — great for focused work!")

        if high_priority:
            tasks_str = ", ".join(f"'{t['title']}'" for t in high_priority[:3])
            parts.append(
                f"High-priority tasks: {tasks_str}."
            )
        elif today_tasks:
            parts.append(f"You have {len(today_tasks)} task(s) to tackle today.")
        else:
            parts.append("No tasks due today — want to plan ahead?")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Private: Check helpers
    # ------------------------------------------------------------------

    def _check_meeting_prep(
        self, events: List[Dict], now: datetime
    ) -> Optional[str]:
        """Trigger a prep reminder for an event starting within PREP_WINDOW minutes."""
        if not events:
            return None
        from dateutil.parser import parse as dt_parse
        for event in events:
            try:
                start = dt_parse(event.get("start_time", ""))
                # Make timezone-naive for comparison if needed
                if start.tzinfo:
                    from datetime import timezone
                    now_aware = now.replace(tzinfo=timezone.utc)
                    # Use local time comparison
                    start_naive = start.replace(tzinfo=None)
                    delta = (start_naive - now).total_seconds() / 60
                else:
                    delta = (start - now).total_seconds() / 60
                if 0 < delta <= self.MEETING_PREP_WINDOW_MIN:
                    mins = int(delta)
                    return (
                        f"Just a heads-up — '{event.get('title', 'your next event')}' "
                        f"starts in {mins} min. All set?"
                    )
            except Exception:
                continue
        return None

    def _check_overdue_tasks(
        self, todos: List[Dict], now: datetime
    ) -> Optional[str]:
        """Alert about overdue tasks (due_date < today, status != completed)."""
        if not todos:
            return None
        today = now.strftime("%Y-%m-%d")
        overdue = [
            t for t in todos
            if t.get("status", "pending") != "completed"
            and t.get("due_date", today) < today
        ]
        if not overdue:
            return None
        count = len(overdue)
        if count == 1:
            return f"'{overdue[0]['title']}' is overdue — want to reschedule it?"
        return (
            f"You have {count} overdue tasks. "
            f"Want me to reschedule them to today?"
        )

    def _check_day_overload(
        self, todos: List[Dict], events: List[Dict], now: datetime
    ) -> Optional[str]:
        """Warn if today is packed beyond healthy thresholds."""
        today = now.strftime("%Y-%m-%d")
        today_tasks = [
            t for t in todos
            if t.get("due_date", "") == today and t.get("status") != "completed"
        ]
        today_events = self._events_for_date(events, today)

        task_overload = len(today_tasks) >= self.OVERLOAD_TASKS_PER_DAY
        event_overload = len(today_events) >= self.OVERLOAD_EVENTS_PER_DAY

        if task_overload and event_overload:
            return (
                f"Today looks very full — {len(today_events)} events and "
                f"{len(today_tasks)} tasks. Want help prioritising?"
            )
        if task_overload:
            return (
                f"You've got {len(today_tasks)} tasks today — that's a heavy list. "
                f"Want to defer some lower-priority ones?"
            )
        if event_overload:
            return (
                f"Your calendar has {len(today_events)} events today — "
                f"that's a packed schedule. Make sure to schedule breaks!"
            )
        return None

    def _check_budget_proximity(
        self, memory_context: Dict
    ) -> Optional[str]:
        """Warn if any budget constraint is near its limit."""
        constraints = memory_context.get("constraints", [])
        for constraint in constraints:
            key = constraint.get("key", "")
            value = constraint.get("value", {})
            if not isinstance(value, dict):
                continue
            pct = value.get("used_pct")
            if pct and pct >= self.BUDGET_WARNING_PCT:
                category = key.replace("monthly_", "").replace("_budget", "")
                pct_display = int(pct * 100)
                return (
                    f"You're at {pct_display}% of your {category} budget for this month — "
                    f"keeping an eye on it!"
                )
        return None

    def _check_morning_briefing(
        self,
        session_context: Dict,
        todos: List[Dict],
        events: List[Dict],
        now: datetime,
    ) -> Optional[str]:
        """Suggest a daily briefing on first morning interaction."""
        if now.hour < 6 or now.hour > 10:
            return None
        # Only suggest if this appears to be the first message of the day
        recent = session_context.get("recent_messages", [])
        if recent:
            return None
        today = now.strftime("%Y-%m-%d")
        task_count = sum(
            1 for t in todos
            if t.get("due_date", "") == today and t.get("status") != "completed"
        )
        event_count = len(self._events_for_date(events, today))
        if task_count + event_count == 0:
            return None
        return (
            f"Good morning! You have {task_count} task(s) and "
            f"{event_count} event(s) lined up today. Want a quick briefing?"
        )

    def _check_evening_wrap(
        self,
        todos: List[Dict],
        events: List[Dict],
        now: datetime,
        session_context: Dict,
    ) -> Optional[str]:
        """Suggest an evening wrap-up nudge."""
        if now.hour < 17 or now.hour > 21:
            return None
        today = now.strftime("%Y-%m-%d")
        pending = [
            t for t in todos
            if t.get("due_date", "") == today and t.get("status") != "completed"
        ]
        done = [
            t for t in todos
            if t.get("due_date", "") == today and t.get("status") == "completed"
        ]
        if not pending:
            return None
        done_txt = f"{len(done)} done" if done else "none done yet"
        return (
            f"End-of-day check: {done_txt}, {len(pending)} still pending. "
            f"Want me to move them to tomorrow?"
        )

    def _check_habit_nudge(
        self, memory_context: Dict, now: datetime
    ) -> Optional[str]:
        """Nudge the user on a stated goal or habit they haven't acted on."""
        # Only nudge on weekdays
        if now.weekday() >= 5:
            return None
        # Only nudge in the afternoon (3-6 PM)
        if not (15 <= now.hour <= 18):
            return None
        habits = memory_context.get("habits", [])
        goals = [
            h for h in habits
            if h.get("key", "").startswith("goal")
            and h.get("confidence", 0) >= 0.7
        ]
        if not goals:
            return None
        goal = goals[0]
        goal_val = goal.get("value", "your goal")
        return f"Quick check-in: how's '{goal_val}' going? Even 15 minutes today keeps the streak alive."

    def _check_free_slot(
        self, todos: List[Dict], events: List[Dict], now: datetime
    ) -> Optional[str]:
        """Detect a 2-hour free window and suggest using it for a high-priority task."""
        # Only during working hours
        if not (9 <= now.hour <= 17):
            return None
        # Find next free 2-hour window
        free_start = self._find_free_slot(events, now, min_duration_hours=2)
        if not free_start:
            return None
        # Find the top pending task
        pending_high = [
            t for t in todos
            if t.get("status") != "completed" and t.get("priority") == "high"
        ]
        if not pending_high:
            return None
        top_task = pending_high[0]
        slot_str = free_start.strftime("%-I:%M %p") if hasattr(free_start, "strftime") else "soon"
        return (
            f"You've got a clear window around {slot_str}. "
            f"Good time for '{top_task['title']}'?"
        )

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _events_for_date(self, events: List[Dict], date_str: str) -> List[Dict]:
        """Filter events that fall on a given date (YYYY-MM-DD)."""
        result = []
        for e in events:
            start = e.get("start_time", "")
            if start.startswith(date_str):
                result.append(e)
        return result

    def _find_free_slot(
        self, events: List[Dict], now: datetime, min_duration_hours: float = 2.0
    ) -> Optional[datetime]:
        """
        Find the next free time slot of at least min_duration_hours.
        Returns the start of the free window, or None.
        """
        if not events:
            # Entire rest of day is free
            return now + timedelta(minutes=5)

        from dateutil.parser import parse as dt_parse
        today = now.strftime("%Y-%m-%d")

        # Build sorted list of (start, end) for today's events
        slots = []
        for e in events:
            try:
                s = dt_parse(e.get("start_time", "")).replace(tzinfo=None)
                en = dt_parse(e.get("end_time", "")).replace(tzinfo=None)
                if s.strftime("%Y-%m-%d") == today:
                    slots.append((s, en))
            except Exception:
                continue

        slots.sort()
        check_from = now

        for s, en in slots:
            gap = (s - check_from).total_seconds() / 3600
            if gap >= min_duration_hours and check_from >= now:
                return check_from
            check_from = max(check_from, en)

        # Check after last event
        if check_from < datetime.now().replace(hour=19, minute=0):
            gap = (datetime.now().replace(hour=19, minute=0) - check_from).total_seconds() / 3600
            if gap >= min_duration_hours:
                return check_from

        return None

    @staticmethod
    def _format_time(time_str: str) -> str:
        """Format ISO time string for speech."""
        try:
            from dateutil.parser import parse as dt_parse
            dt = dt_parse(time_str).replace(tzinfo=None)
            return dt.strftime("%I:%M %p").lstrip("0")
        except Exception:
            return time_str

    def _is_cool_down_ok(
        self, user_id: str, suggestion_type: str, now: datetime, cooldown_min: int = 60
    ) -> bool:
        """Return True if we haven't shown this suggestion recently."""
        key = f"{user_id}:{suggestion_type}"
        last = self._last_suggestions.get(key)
        if last is None:
            return True
        _, ts = last
        return (now - ts).total_seconds() / 60 >= cooldown_min

    def _record_suggestion(
        self, user_id: str, suggestion_type: str, now: datetime
    ) -> None:
        key = f"{user_id}:{suggestion_type}"
        self._last_suggestions[key] = (suggestion_type, now)
