"""
TodoAgent - Handles to-do list management intents.

Fully integrated with TodoService (MongoDB) and ScheduleContext
for cross-domain awareness with the Calendar system.

Intents handled:
- add_todo, list_todos, complete_todo, update_todo, delete_todo

Uses GPT to extract task details from natural language.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from openai import OpenAI
import os
import json
from dotenv import load_dotenv

from .base_agent import BaseAgent, AgentResponse

load_dotenv()


class TodoAgent(BaseAgent):
    """Agent for to-do list management with shared calendar awareness."""

    SUPPORTED_INTENTS = [
        "add_todo",
        "list_todos",
        "complete_todo",
        "update_todo",
        "delete_todo",
    ]

    def __init__(
        self,
        todo_service=None,
        schedule_context=None,
        openai_client: OpenAI = None,
    ):
        self.todo_service = todo_service
        self.schedule_context = schedule_context
        self.client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    @property
    def domain(self) -> str:
        return "todo"

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
        print(f"[TODO_AGENT] Handling intent={intent}")

        if self.todo_service is None:
            return AgentResponse(
                response="To-do features are being set up. Check back soon!",
                metadata={"stub": True},
            )

        if intent == "add_todo":
            return await self._handle_add(user_input, context, memory)
        elif intent == "list_todos":
            return await self._handle_list(user_input, context, memory)
        elif intent == "complete_todo":
            return await self._handle_complete(user_input, context, memory)
        elif intent == "update_todo":
            return await self._handle_update(user_input, context, memory)
        elif intent == "delete_todo":
            return await self._handle_delete(user_input, context, memory)
        else:
            return AgentResponse(response="I'm not sure how to handle that task request.")

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    async def _handle_add(self, user_input, context, memory) -> AgentResponse:
        """Add a new to-do item from natural language."""
        user_id = context.get("user_id", "unknown")

        # Get shared schedule for smarter suggestions
        schedule_summary = ""
        if self.schedule_context:
            try:
                schedule_summary = await self.schedule_context.get_context_for_prompt(user_id)
            except Exception as e:
                print(f"[TODO_AGENT] Schedule context error: {e}")

        # Extract task data via GPT
        task_data = await self._extract_task_data(user_input, context, schedule_summary)

        title = task_data.get("title")
        if not title:
            return AgentResponse(
                response="What task would you like to add?",
                requires_followup=True,
                pending_field="task_title",
            )

        due_date = task_data.get("due_date")
        if not due_date:
            due_date = datetime.now().strftime("%Y-%m-%d")

        # Create task in background
        background_tasks = [{
            "type": "create_todo",
            "payload": {
                "title": title,
                "due_date": due_date,
                "due_time": task_data.get("due_time"),
                "priority": task_data.get("priority", "medium"),
                "category": task_data.get("category", "other"),
                "description": task_data.get("description", ""),
            }
        }]

        # Build friendly response
        date_str = self._format_date_for_speech(due_date)
        priority = task_data.get("priority", "medium")
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "")

        return AgentResponse(
            response=f"Got it! Added '{title}' for {date_str}. {priority_emoji} {priority.title()} priority.",
            actions_taken=["todo_creation_queued"],
            background_tasks=background_tasks,
            data={"task_data": task_data},
        )

    async def _handle_list(self, user_input, context, memory) -> AgentResponse:
        """List to-do items, optionally with schedule context."""
        user_id = context.get("user_id", "unknown")

        # Determine query parameters
        query_params = await self._extract_list_params(user_input)
        days = query_params.get("days", 1)
        status = query_params.get("status")

        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

        todos = await self.todo_service.get_todos(
            user_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=20,
        )

        if not todos:
            period = "today" if days == 1 else f"the next {days} days"
            return AgentResponse(
                response=f"You're all clear for {period} — no tasks pending!",
                data={"todos": [], "count": 0},
            )

        # Build natural language response
        response = self._build_list_response(todos, query_params)

        # Include schedule context if available
        if self.schedule_context:
            try:
                full_ctx = await self.schedule_context.get_full_context(user_id, days=days)
                events = full_ctx.get("calendar_events", [])
                if events:
                    response += f"\n\nYou also have {len(events)} calendar event(s) in this period."
            except Exception:
                pass

        return AgentResponse(
            response=response,
            data={"todos": todos, "count": len(todos)},
        )

    async def _handle_complete(self, user_input, context, memory) -> AgentResponse:
        """Mark a to-do as completed."""
        user_id = context.get("user_id", "unknown")

        # Get pending todos to match against
        todos = await self.todo_service.get_todos(
            user_id, status="pending", limit=20,
        )

        if not todos:
            return AgentResponse(response="You don't have any pending tasks to complete!")

        # Match which task the user is referring to
        match = await self._match_todo(user_input, todos)

        if not match.get("todo_id"):
            task_list = "\n".join([f"• {t['title']} (due {t['due_date']})" for t in todos[:5]])
            return AgentResponse(
                response=f"Which task did you complete?\n{task_list}",
                requires_followup=True,
                pending_field="todo_selection",
                data={"todos": todos},
            )

        result = await self.todo_service.complete_todo(user_id, match["todo_id"])
        if result:
            return AgentResponse(
                response=f"Nice! ✅ '{result['title']}' marked as done.",
                actions_taken=["todo_completed"],
                data={"todo": result},
            )
        return AgentResponse(response="Sorry, I couldn't mark that task as complete.")

    async def _handle_update(self, user_input, context, memory) -> AgentResponse:
        """Update an existing to-do."""
        user_id = context.get("user_id", "unknown")

        todos = await self.todo_service.get_todos(
            user_id, status="pending", limit=20,
        )
        if not todos:
            return AgentResponse(response="You don't have any tasks to update.")

        match = await self._match_todo(user_input, todos, extract_updates=True)
        if not match.get("todo_id"):
            return AgentResponse(
                response="Which task would you like to update?",
                requires_followup=True,
                pending_field="todo_selection",
            )

        updates = match.get("updates", {})
        if not updates:
            return AgentResponse(
                response="What would you like to change about this task?",
                requires_followup=True,
                pending_field="todo_updates",
            )

        result = await self.todo_service.update_todo(user_id, match["todo_id"], updates)
        if result:
            return AgentResponse(
                response=f"Updated '{result['title']}'.",
                actions_taken=["todo_updated"],
                data={"todo": result},
            )
        return AgentResponse(response="Sorry, I couldn't update that task.")

    async def _handle_delete(self, user_input, context, memory) -> AgentResponse:
        """Delete a to-do item."""
        user_id = context.get("user_id", "unknown")

        todos = await self.todo_service.get_todos(user_id, limit=20)
        if not todos:
            return AgentResponse(response="You don't have any tasks to delete.")

        match = await self._match_todo(user_input, todos)
        if not match.get("todo_id"):
            task_list = "\n".join([f"• {t['title']}" for t in todos[:5]])
            return AgentResponse(
                response=f"Which task should I delete?\n{task_list}",
                requires_followup=True,
                pending_field="todo_selection",
            )

        todo_title = match.get("todo_title", "the task")
        result = await self.todo_service.delete_todo(user_id, match["todo_id"])

        if result:
            return AgentResponse(
                response=f"Done, '{todo_title}' has been removed.",
                actions_taken=["todo_deleted"],
            )
        return AgentResponse(response="Sorry, I couldn't delete that task.")

    # ------------------------------------------------------------------
    # GPT helpers
    # ------------------------------------------------------------------

    async def _extract_task_data(
        self, user_input: str, context: Dict, schedule_summary: str = ""
    ) -> Dict:
        """Use GPT to extract task details from natural language."""
        now = datetime.now()
        context_parts = [
            f"Current date/time: {now.strftime('%Y-%m-%d %H:%M')} (IST)",
        ]
        if schedule_summary:
            context_parts.append(f"CURRENT SCHEDULE:\n{schedule_summary}")

        if context.get("pending_data"):
            context_parts.append(f"Previous data: {json.dumps(context['pending_data'])}")

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._task_extraction_prompt()},
                    {
                        "role": "user",
                        "content": f"CONTEXT:\n"
                        + "\n".join(context_parts)
                        + f"\n\nUSER: {user_input}",
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=400,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[TODO_AGENT] Extraction error: {e}")
            return {}

    async def _extract_list_params(self, user_input: str) -> Dict:
        """Extract listing parameters from user input."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """Extract to-do list query parameters. Return JSON:
{"days": number (1=today, 7=this week, 30=this month), "period_label": "today|tomorrow|this week|this month", "status": "pending|completed|null"}
Current date: """
                        + datetime.now().strftime("%Y-%m-%d"),
                    },
                    {"role": "user", "content": user_input},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=100,
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
            return {"days": 1, "period_label": "today", "status": "pending"}

    async def _match_todo(
        self,
        user_input: str,
        todos: List[Dict],
        extract_updates: bool = False,
    ) -> Dict:
        """Use GPT to match user input to a specific to-do item."""
        todo_list = json.dumps(
            [
                {
                    "id": t["_id"],
                    "title": t["title"],
                    "due_date": t["due_date"],
                    "priority": t["priority"],
                }
                for t in todos
            ]
        )

        updates_instruction = ""
        if extract_updates:
            updates_instruction = (
                ', "updates": {"title": "new title or null", "due_date": "YYYY-MM-DD or null", '
                '"priority": "high|medium|low or null", "category": "string or null"}'
            )

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": f"""Match the user's request to one of these tasks. Return JSON:
{{"todo_id": "matched task id or null", "todo_title": "title"{updates_instruction}}}
Tasks: {todo_list}
Current date: {datetime.now().strftime("%Y-%m-%d")}""",
                    },
                    {"role": "user", "content": user_input},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=200,
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    def _task_extraction_prompt(self) -> str:
        return (
            """You are RIVA's to-do task extractor. Extract task details from user input.
Analyze the user's CURRENT SCHEDULE (if provided) to suggest smart due dates.

RETURN THIS JSON:
{
  "title": "Task title (e.g. 'Buy groceries', 'Submit report')",
  "due_date": "YYYY-MM-DD (default: today)",
  "due_time": "HH:MM or null (optional specific time)",
  "priority": "high | medium | low (default: medium)",
  "category": "work | personal | health | study | other",
  "description": "Brief description or empty string"
}

RULES:
- "tomorrow" → next day's date
- "next Monday" → the coming Monday
- "by Friday" → that Friday
- If no date specified, default to today
- Infer priority from urgency words: "urgent", "asap" → high; "when possible" → low
- Infer category from context: "gym", "workout" → health; "meeting", "report" → work
- If the schedule shows a busy day, mention it in description
- Keep titles concise but descriptive
- TODAY'S DATE: """
            + datetime.now().strftime("%Y-%m-%d %H:%M")
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_list_response(self, todos: List[Dict], params: Dict) -> str:
        """Build natural language response for to-do listing."""
        period = params.get("period_label", "today")

        if len(todos) == 1:
            t = todos[0]
            date_str = self._format_date_for_speech(t["due_date"])
            return f"You have one task {period}: '{t['title']}' due {date_str}."

        # Group by priority
        high = [t for t in todos if t.get("priority") == "high"]
        rest = [t for t in todos if t.get("priority") != "high"]

        parts = [f"You have {len(todos)} tasks {period}:"]

        if high:
            parts.append(f"\n🔴 High priority:")
            for t in high[:3]:
                parts.append(f"  • {t['title']} (due {t['due_date']})")

        for t in rest[:5]:
            emoji = "🟡" if t.get("priority") == "medium" else "🟢"
            parts.append(f"  {emoji} {t['title']} (due {t['due_date']})")

        return "\n".join(parts)

    @staticmethod
    def _format_date_for_speech(date_str: str) -> str:
        """Format YYYY-MM-DD for voice-friendly output."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            now = datetime.now()
            if dt.date() == now.date():
                return "today"
            elif dt.date() == (now + timedelta(days=1)).date():
                return "tomorrow"
            elif dt.date() == (now - timedelta(days=1)).date():
                return "yesterday"
            else:
                return dt.strftime("%A, %B %d")
        except Exception:
            return date_str

    async def execute_background_task(
        self, task_type: str, payload: Dict[str, Any], user_id: str
    ):
        """Execute to-do tasks in the background."""
        if task_type == "create_todo":
            print(f"[TODO_AGENT] Background creating task: {payload.get('title')}")
            await self.todo_service.add_todo(
                user_id=user_id,
                title=payload.get("title", ""),
                due_date=payload.get("due_date"),
                due_time=payload.get("due_time"),
                priority=payload.get("priority", "medium"),
                category=payload.get("category", "other"),
                description=payload.get("description", ""),
            )
        elif task_type == "update_todo":
            await self.todo_service.update_todo(
                user_id=user_id,
                todo_id=payload.get("todo_id"),
                updates=payload.get("updates", {}),
            )
        elif task_type == "delete_todo":
            await self.todo_service.delete_todo(
                user_id=user_id,
                todo_id=payload.get("todo_id"),
            )
