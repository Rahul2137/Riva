"""
Schedule Context - Shared context layer between Calendar and To-Do.

Builds a unified "schedule snapshot" that both the ProductivityAgent
and TodoAgent can consult. This enables:
- To-Do agent to suggest times that don't conflict with calendar events
- Calendar agent to mention related pending tasks
- Gemini system prompt to have full schedule awareness

This module is READ-ONLY; it never writes to either service.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional


class ScheduleContext:
    """Builds a combined snapshot of calendar events + to-do items."""

    def __init__(self, calendar_service=None, todo_service=None):
        self.calendar_service = calendar_service
        self.todo_service = todo_service

    async def get_full_context(
        self,
        user_id: str,
        days: int = 3,
    ) -> Dict[str, Any]:
        """Build a combined schedule snapshot for the next N days.

        Returns:
            {
                "date": "2026-04-28",
                "calendar_events": [...],
                "todos": {
                    "pending": [...],
                    "overdue": [...]
                },
                "stats": {"pending": 5, "completed_today": 2, "overdue": 1},
                "busy_slots": ["09:00-10:00", ...],
                "summary": "natural-language summary"
            }
        """
        context: Dict[str, Any] = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M"),
            "calendar_events": [],
            "todos": {"pending": [], "overdue": []},
            "stats": {},
            "busy_slots": [],
            "summary": "",
        }

        # ── Calendar events ─────────────────────────────────────────
        if self.calendar_service:
            try:
                is_connected = await self.calendar_service.is_connected(user_id)
                if is_connected:
                    events = await self.calendar_service.list_events(
                        user_id,
                        time_min=datetime.utcnow(),
                        time_max=datetime.utcnow() + timedelta(days=days),
                        max_results=20,
                    )
                    context["calendar_events"] = events

                    # Extract busy time slots
                    for e in events:
                        start = e.get("start_time", "")
                        end = e.get("end_time", "")
                        if start and end:
                            context["busy_slots"].append({
                                "title": e.get("title", ""),
                                "start": start,
                                "end": end,
                            })
            except Exception as ex:
                print(f"[SCHEDULE_CONTEXT] Calendar fetch error: {ex}")

        # ── To-do items ─────────────────────────────────────────────
        if self.todo_service:
            try:
                pending = await self.todo_service.get_upcoming_todos(user_id, days=days)
                overdue = await self.todo_service.get_overdue_todos(user_id)
                stats = await self.todo_service.get_stats(user_id)

                context["todos"]["pending"] = pending
                context["todos"]["overdue"] = overdue
                context["stats"] = stats
            except Exception as ex:
                print(f"[SCHEDULE_CONTEXT] Todo fetch error: {ex}")

        # ── Natural-language summary ────────────────────────────────
        context["summary"] = self._build_summary(context)

        return context

    async def get_context_for_prompt(self, user_id: str, days: int = 2) -> str:
        """Return a concise text summary for injecting into GPT/Gemini prompts.

        This is the key integration point — both agents call this
        to get awareness of the "other" domain.
        """
        ctx = await self.get_full_context(user_id, days=days)
        return ctx["summary"]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(ctx: Dict) -> str:
        """Build a natural-language schedule summary."""
        parts = [f"Current date/time: {ctx['date']} {ctx['time']} IST"]

        # Calendar
        events = ctx["calendar_events"]
        if events:
            parts.append(f"\nUpcoming calendar events ({len(events)}):")
            for e in events[:8]:
                parts.append(f"  • {e.get('title', 'Untitled')} — {e.get('start_time', '?')}")
        else:
            parts.append("\nNo upcoming calendar events.")

        # Todos
        stats = ctx.get("stats", {})
        overdue = ctx["todos"]["overdue"]
        pending = ctx["todos"]["pending"]

        if stats:
            parts.append(
                f"\nTo-do stats: {stats.get('pending', 0)} pending, "
                f"{stats.get('overdue', 0)} overdue, "
                f"{stats.get('completed_today', 0)} completed today"
            )

        if overdue:
            parts.append(f"\nOverdue tasks ({len(overdue)}):")
            for t in overdue[:5]:
                parts.append(
                    f"  ⚠ {t['title']} (due {t['due_date']}, {t['priority']} priority)"
                )

        if pending:
            parts.append(f"\nUpcoming tasks ({len(pending)}):")
            for t in pending[:8]:
                time_str = f" at {t['due_time']}" if t.get("due_time") else ""
                parts.append(
                    f"  • {t['title']} — due {t['due_date']}{time_str} "
                    f"[{t['priority']}] ({t['category']})"
                )

        return "\n".join(parts)
