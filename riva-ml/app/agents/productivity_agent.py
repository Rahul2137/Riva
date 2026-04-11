"""
ProductivityAgent - Handles scheduling, calendar, and task intents.

Fully integrated with Google Calendar via CalendarService.
Uses GPT to extract event details from natural language.

Intents handled:
- schedule_event, query_calendar, reschedule_event
- cancel_event, set_reminder
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from openai import OpenAI
import os
import json
from dotenv import load_dotenv

from .base_agent import BaseAgent, AgentResponse

load_dotenv()


class ProductivityAgent(BaseAgent):
    """Agent for calendar, scheduling, and task management."""

    SUPPORTED_INTENTS = [
        "schedule_event",
        "query_calendar",
        "reschedule_event",
        "cancel_event",
        "set_reminder",
    ]

    def __init__(self, calendar_service=None, openai_client: OpenAI = None):
        self.calendar_service = calendar_service
        self.client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    @property
    def domain(self) -> str:
        return "productivity"

    def get_supported_intents(self) -> List[str]:
        return self.SUPPORTED_INTENTS

    async def handle(
        self,
        intent: str,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> AgentResponse:
        """Route to intent handler."""
        print(f"[PRODUCTIVITY_AGENT] Handling intent={intent}")

        user_id = context.get("user_id", "unknown")

        # Check calendar connection
        if self.calendar_service is None:
            return self._no_service_response()

        is_connected = await self.calendar_service.is_connected(user_id)

        if not is_connected:
            return AgentResponse(
                response="Your Google Calendar isn't connected yet. "
                "Head over to the Productivity tab and tap 'Connect Calendar' to get started!",
                metadata={"needs_calendar_connect": True},
            )

        # Route to handler
        if intent == "schedule_event":
            return await self._handle_schedule(user_input, context, memory)
        elif intent == "query_calendar":
            return await self._handle_query(user_input, context, memory)
        elif intent == "reschedule_event":
            return await self._handle_reschedule(user_input, context, memory)
        elif intent == "cancel_event":
            return await self._handle_cancel(user_input, context, memory)
        elif intent == "set_reminder":
            return await self._handle_reminder(user_input, context, memory)
        else:
            return AgentResponse(response="I'm not sure how to handle that scheduling request.")

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    async def _handle_schedule(self, user_input, context, memory) -> AgentResponse:
        """Create a calendar event from natural language."""
        user_id = context.get("user_id", "unknown")

        # Extract event details via GPT
        event_data = await self._extract_event_data(user_input, context)

        title = event_data.get("title")
        start_time = event_data.get("start_time")
        end_time = event_data.get("end_time")
        description = event_data.get("description", "")

        # Validate required fields
        if not title:
            return AgentResponse(
                response="What would you like to call this event?",
                requires_followup=True,
                pending_field="event_title",
                data={"partial_data": event_data},
            )

        if not start_time:
            return AgentResponse(
                response="When should I schedule this?",
                requires_followup=True,
                pending_field="event_time",
                data={"partial_data": event_data},
            )

        # Default end time: 1 hour after start
        if not end_time:
            from dateutil.parser import parse
            try:
                start_dt = parse(start_time)
                end_dt = start_dt + timedelta(hours=1)
                end_time = end_dt.isoformat()
            except Exception:
                end_time = start_time

        # Check for conflicts
        conflicts = await self.calendar_service.check_conflicts(user_id, start_time, end_time)
        if conflicts:
            conflict_names = ", ".join([c["title"] for c in conflicts[:3]])
            return AgentResponse(
                response=f"Heads up — you already have: {conflict_names} at that time. "
                f"Want me to schedule '{title}' anyway?",
                requires_followup=True,
                pending_field="confirm_schedule",
                data={"event_data": event_data, "conflicts": conflicts},
            )

        # Create the event
        result = await self.calendar_service.create_event(
            user_id=user_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            description=description,
        )

        if result:
            # Format time for response
            time_str = self._format_time_for_speech(start_time)
            return AgentResponse(
                response=f"Done! '{title}' is scheduled for {time_str}.",
                actions_taken=["event_created"],
                data={"event": result},
            )
        else:
            return AgentResponse(
                response="Sorry, I couldn't create that event. Please try again.",
            )

    async def _handle_query(self, user_input, context, memory) -> AgentResponse:
        """Query upcoming events."""
        user_id = context.get("user_id", "unknown")

        # Determine time range from user input
        query_params = await self._extract_query_params(user_input)
        days = query_params.get("days", 1)

        events = await self.calendar_service.list_events(
            user_id,
            time_min=datetime.utcnow(),
            time_max=datetime.utcnow() + timedelta(days=days),
            max_results=10,
        )

        if not events:
            period = "today" if days == 1 else f"the next {days} days"
            return AgentResponse(
                response=f"Your calendar is clear for {period}. No events scheduled!",
                data={"events": [], "count": 0},
            )

        # Build natural language response
        response = await self._generate_schedule_response(events, query_params)
        return AgentResponse(
            response=response,
            data={"events": events, "count": len(events)},
        )

    async def _handle_reschedule(self, user_input, context, memory) -> AgentResponse:
        """Reschedule an event."""
        user_id = context.get("user_id", "unknown")

        # Get upcoming events to find the one to reschedule
        events = await self.calendar_service.list_events(
            user_id, max_results=10
        )

        if not events:
            return AgentResponse(response="You don't have any upcoming events to reschedule.")

        # Use GPT to match the event and new time
        match = await self._match_event(user_input, events)

        if not match.get("event_id"):
            event_list = "\n".join([f"• {e['title']}" for e in events[:5]])
            return AgentResponse(
                response=f"Which event would you like to reschedule?\n{event_list}",
                requires_followup=True,
                pending_field="event_selection",
                data={"events": events},
            )

        new_time = match.get("new_start_time")
        if not new_time:
            return AgentResponse(
                response="When would you like to move it to?",
                requires_followup=True,
                pending_field="new_time",
                data={"event_id": match["event_id"]},
            )

        # Calculate new end time (preserve duration)
        from dateutil.parser import parse
        old_event = next((e for e in events if e["id"] == match["event_id"]), None)
        if old_event:
            try:
                old_start = parse(old_event["start_time"])
                old_end = parse(old_event["end_time"])
                duration = old_end - old_start
                new_start = parse(new_time)
                new_end = new_start + duration
            except Exception:
                new_end = parse(new_time) + timedelta(hours=1)
        else:
            new_end = parse(new_time) + timedelta(hours=1)

        result = await self.calendar_service.update_event(
            user_id,
            match["event_id"],
            {"start_time": new_time, "end_time": new_end.isoformat()},
        )

        if result:
            time_str = self._format_time_for_speech(new_time)
            return AgentResponse(
                response=f"Done! I've moved '{result['title']}' to {time_str}.",
                actions_taken=["event_rescheduled"],
                data={"event": result},
            )
        return AgentResponse(response="Sorry, I couldn't reschedule that event.")

    async def _handle_cancel(self, user_input, context, memory) -> AgentResponse:
        """Cancel/delete an event."""
        user_id = context.get("user_id", "unknown")

        events = await self.calendar_service.list_events(user_id, max_results=10)
        if not events:
            return AgentResponse(response="You don't have any upcoming events to cancel.")

        match = await self._match_event(user_input, events)
        if not match.get("event_id"):
            event_list = "\n".join([f"• {e['title']}" for e in events[:5]])
            return AgentResponse(
                response=f"Which event would you like to cancel?\n{event_list}",
                requires_followup=True,
                pending_field="event_selection",
            )

        event_title = match.get("event_title", "the event")
        result = await self.calendar_service.delete_event(user_id, match["event_id"])

        if result:
            return AgentResponse(
                response=f"Done, '{event_title}' has been cancelled.",
                actions_taken=["event_cancelled"],
            )
        return AgentResponse(response="Sorry, I couldn't cancel that event.")

    async def _handle_reminder(self, user_input, context, memory) -> AgentResponse:
        """Set a reminder by creating a short calendar event."""
        user_id = context.get("user_id", "unknown")

        event_data = await self._extract_event_data(user_input, context)
        title = event_data.get("title", "Reminder")
        start_time = event_data.get("start_time")

        if not start_time:
            return AgentResponse(
                response="When should I remind you?",
                requires_followup=True,
                pending_field="reminder_time",
            )

        # Create a 15-minute reminder event
        from dateutil.parser import parse
        start_dt = parse(start_time)
        end_dt = start_dt + timedelta(minutes=15)

        result = await self.calendar_service.create_event(
            user_id=user_id,
            title=f"⏰ {title}",
            start_time=start_time,
            end_time=end_dt.isoformat(),
            description="Created by RIVA as a reminder",
        )

        if result:
            time_str = self._format_time_for_speech(start_time)
            return AgentResponse(
                response=f"Reminder set! I'll remind you about '{title}' at {time_str}.",
                actions_taken=["reminder_set"],
                data={"event": result},
            )
        return AgentResponse(response="Sorry, I couldn't set that reminder.")

    # ------------------------------------------------------------------
    # GPT helpers
    # ------------------------------------------------------------------

    async def _extract_event_data(self, user_input: str, context: Dict) -> Dict:
        """Use GPT to extract event details from natural language."""
        now = datetime.now()
        context_parts = [f"Current date/time: {now.strftime('%Y-%m-%d %H:%M')} (IST)"]

        if context.get("pending_data"):
            context_parts.append(f"Previous data: {json.dumps(context['pending_data'])}")
        if context.get("recent_messages"):
            for msg in context["recent_messages"][-3:]:
                context_parts.append(f"  {msg['role']}: {msg['content']}")

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._event_extraction_prompt()},
                    {"role": "user", "content": f"CONTEXT:\n" + "\n".join(context_parts) + f"\n\nUSER: {user_input}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=400,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[PRODUCTIVITY_AGENT] Extraction error: {e}")
            return {}

    async def _extract_query_params(self, user_input: str) -> Dict:
        """Extract query parameters (time range) from user input."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": """Extract calendar query parameters. Return JSON:
{"days": number (1=today, 7=this week, 30=this month), "period_label": "today|tomorrow|this week|this month"}
Current date: """ + datetime.now().strftime("%Y-%m-%d")},
                    {"role": "user", "content": user_input},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=100,
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
            return {"days": 1, "period_label": "today"}

    async def _match_event(self, user_input: str, events: List[Dict]) -> Dict:
        """Use GPT to match user input to a specific event."""
        event_list = json.dumps([{"id": e["id"], "title": e["title"], "start": e["start_time"]} for e in events])
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"""Match the user's request to one of these events. Return JSON:
{{"event_id": "matched event id or null", "event_title": "title", "new_start_time": "ISO datetime if rescheduling, else null"}}
Events: {event_list}
Current date: {datetime.now().strftime("%Y-%m-%d")}"""},
                    {"role": "user", "content": user_input},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=200,
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
            return {}

    async def _generate_schedule_response(self, events: List[Dict], params: Dict) -> str:
        """Generate a natural-language summary of events."""
        period = params.get("period_label", "today")

        if len(events) == 1:
            e = events[0]
            time_str = self._format_time_for_speech(e["start_time"])
            return f"You have one event {period}: '{e['title']}' at {time_str}."

        # For multiple events, build concise summary
        event_summaries = []
        for e in events[:5]:
            time_str = self._format_time_for_speech(e["start_time"])
            event_summaries.append(f"'{e['title']}' at {time_str}")

        return f"You have {len(events)} events {period}: " + ", ".join(event_summaries) + "."

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    def _event_extraction_prompt(self) -> str:
        return """You are RIVA's calendar event extractor. Extract event details from user input.

RETURN THIS JSON:
{
  "title": "Event title (e.g. 'Team Meeting', 'Gym')",
  "start_time": "ISO 8601 datetime (e.g. '2026-04-12T10:00:00+05:30')",
  "end_time": "ISO 8601 datetime or null (defaults to 1 hour after start)",
  "description": "Brief description or empty string",
  "all_day": false
}

RULES:
- Use IST timezone (+05:30) for all times
- "tomorrow at 3pm" → next day at 15:00
- "next Monday" → the coming Monday
- "in 2 hours" → current time + 2 hours
- If no time specified, default to 09:00
- If no duration specified, default to 1 hour
- Keep title concise
- TODAY'S DATE: """ + datetime.now().strftime("%Y-%m-%d %H:%M")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _no_service_response(self) -> AgentResponse:
        return AgentResponse(
            response="Calendar features are being set up. Check back soon!",
            metadata={"stub": True},
        )

    @staticmethod
    def _format_time_for_speech(time_str: str) -> str:
        """Format ISO time string for voice-friendly output."""
        try:
            from dateutil.parser import parse
            dt = parse(time_str)
            now = datetime.now()

            # Date part
            if dt.date() == now.date():
                date_part = "today"
            elif dt.date() == (now + timedelta(days=1)).date():
                date_part = "tomorrow"
            else:
                date_part = dt.strftime("%A, %B %d")

            # Time part
            time_part = dt.strftime("%I:%M %p").lstrip("0")

            return f"{date_part} at {time_part}"
        except Exception:
            return time_str
