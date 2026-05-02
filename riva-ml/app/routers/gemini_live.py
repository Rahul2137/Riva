"""
Gemini Multimodal Live Router

Architecture:
  Browser (mic PCM) → this router → Gemini Live API (bidi WebSocket)
  Gemini may call tools → we execute them and send results back.

Improvements:
  - update_event / delete_event tools added
  - Parallel tool execution: all tool_calls in one Gemini turn run concurrently
  - Fire-and-forget for write tools (add_expense, schedule_event, update_event,
    delete_event): Gemini gets an immediate ACK so it can start speaking, and
    the actual DB/API work happens in the background.
  - Query tools (query_spending, list_events) are still awaited because the
    result is part of the answer.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import os
import json
import asyncio
import base64
from google import genai
from google.genai import types
from typing import Dict, Any

from agents import FinanceAgent, ProductivityAgent, TodoAgent
from services.riva_brain import build_riva_system_prompt, get_time_context
from services.memory_service import MemoryService
from services.calendar_service import CalendarService
from services.todo_service import TodoService
from services.schedule_context import ScheduleContext
from services.db import user_memory_collection, transactions_collection, calendar_tokens_collection, todos_collection
from openai import OpenAI

router = APIRouter(tags=["Gemini Live"])

# ---------------------------------------------------------------------------
# Tools that can be fire-and-forget (write operations)
# ---------------------------------------------------------------------------
BACKGROUND_TOOLS = {"add_transaction", "update_event", "delete_event", "add_todo", "complete_todo", "delete_todo",
                    "update_expense", "delete_expense"}

# Immediate ACK messages sent to Gemini while the real work happens in background
ACK_MESSAGES = {
    "add_transaction": "recorded.",
    "schedule_event":  "scheduled.",
    "update_event":    "updated.",
    "delete_event":    "deleted.",
    "add_todo":        "added to your list.",
    "complete_todo":   "marked as done.",
    "delete_todo":     "removed from your list.",
    "update_expense":  "updated.",
    "delete_expense":  "deleted.",
}

# Closing phrases that trigger conversation end
END_PHRASES = {"bye", "goodbye", "see you", "that's all", "thanks bye", "exit", "quit", "close"}


# ---------------------------------------------------------------------------
# Tool declarations + handler factory
# ---------------------------------------------------------------------------
async def get_tools_and_handlers(user_id: str):
    """Build Gemini tool declarations and an async handler for a user session."""
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    memory_service  = MemoryService(user_memory_collection)
    calendar_service = CalendarService(calendar_tokens_collection)
    todo_service = TodoService(todos_collection)
    schedule_context = ScheduleContext(calendar_service=calendar_service, todo_service=todo_service)

    finance_agent = FinanceAgent(
        openai_client=openai_client,
        transactions_collection=transactions_collection,
        memory_service=memory_service,
    )
    productivity_agent = ProductivityAgent(
        calendar_service=calendar_service,
        openai_client=openai_client,
    )

    tools = [
        {
            "function_declarations": [
                # ── Finance ──────────────────────────────────────────────
                {
                    "name": "add_transaction",
                    "description": (
                        "Record any financial transaction — expense, income, money lent to someone, "
                        "or money borrowed. Always pass the correct transaction_type."
                    ),
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "transaction_type": {
                                "type": "STRING",
                                "description": (
                                    "Type of transaction: "
                                    "'expense' (money spent), "
                                    "'income' (money received/salary/payment), "
                                    "'lended' (money lent to someone), "
                                    "'borrowed' (money borrowed from someone)."
                                ),
                            },
                            "amount":      {"type": "NUMBER", "description": "Transaction amount in INR."},
                            "category":    {"type": "STRING", "description": "Category: food, transport, shopping, bills, entertainment, health, personal, salary, investment, other."},
                            "description": {"type": "STRING", "description": "Short description, e.g. 'lunch', 'Rahul borrowed ₹500', 'freelance payment'."},
                            "date":        {"type": "STRING", "description": "YYYY-MM-DD (optional, defaults to today)."},
                            "person":      {"type": "STRING", "description": "Name of person involved (only for lended/borrowed)."},
                        },
                        "required": ["transaction_type", "amount", "category"],
                    },
                },
                {
                    "name": "query_spending",
                    "description": "Query the user's spending history and totals.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "time_range": {"type": "STRING", "description": "today | this_week | this_month | last_month | all"},
                            "category":   {"type": "STRING", "description": "Filter by category (optional)."},
                        },
                    },
                },
                {
                    "name": "list_expenses",
                    "description": "List recent expenses so the user can pick one to edit or delete. Returns expense IDs.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "days":     {"type": "NUMBER", "description": "How many days back to look (default 7)."},
                            "category": {"type": "STRING", "description": "Filter by category (optional)."},
                            "limit":    {"type": "NUMBER", "description": "Max number to return (default 10)."},
                        },
                    },
                },
                {
                    "name": "update_expense",
                    "description": "Update an existing expense. Call list_expenses first to get the expense_id.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "expense_id":  {"type": "STRING", "description": "MongoDB _id of the expense."},
                            "amount":      {"type": "NUMBER", "description": "New amount (optional)."},
                            "category":    {"type": "STRING", "description": "New category (optional)."},
                            "description": {"type": "STRING", "description": "New description (optional)."},
                            "date":        {"type": "STRING", "description": "New date YYYY-MM-DD (optional)."},
                        },
                        "required": ["expense_id"],
                    },
                },
                {
                    "name": "delete_expense",
                    "description": "Permanently delete an expense. Call list_expenses first to confirm the expense_id.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "expense_id": {"type": "STRING", "description": "MongoDB _id of the expense to delete."},
                        },
                        "required": ["expense_id"],
                    },
                },
                {
                    "name": "get_budget_status",
                    "description": "Get the user's budget limits vs current spending for this month.",
                    "parameters": {"type": "OBJECT", "properties": {}},
                },
                {
                    "name": "set_budget",
                    "description": "Set or update the monthly budget limit for a spending category.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "category": {"type": "STRING", "description": "Category name: food, transport, shopping, bills, entertainment, health, personal, other."},
                            "limit":    {"type": "NUMBER", "description": "Monthly spending limit in INR."},
                        },
                        "required": ["category", "limit"],
                    },
                },
                # ── Calendar ─────────────────────────────────────────────
                {
                    "name": "schedule_event",
                    "description": "Create a new event on the user's Google Calendar.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "title":       {"type": "STRING", "description": "Event title."},
                            "start_time":  {"type": "STRING", "description": "ISO 8601 start datetime."},
                            "end_time":    {"type": "STRING", "description": "ISO 8601 end datetime (optional, defaults to 1 h after start)."},
                            "description": {"type": "STRING", "description": "Event notes (optional)."},
                        },
                        "required": ["title", "start_time"],
                    },
                },
                {
                    "name": "update_event",
                    "description": (
                        "Update an existing calendar event. "
                        "Use list_events first to get the event_id, then call this. "
                        "Only supply the fields you want to change."
                    ),
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "event_id":    {"type": "STRING", "description": "The Google Calendar event ID."},
                            "title":       {"type": "STRING", "description": "New title (optional)."},
                            "start_time":  {"type": "STRING", "description": "New start datetime ISO 8601 (optional)."},
                            "end_time":    {"type": "STRING", "description": "New end datetime ISO 8601 (optional)."},
                            "description": {"type": "STRING", "description": "New description (optional)."},
                        },
                        "required": ["event_id"],
                    },
                },
                {
                    "name": "delete_event",
                    "description": "Permanently delete a calendar event. Use list_events first to confirm the event_id.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "event_id": {"type": "STRING", "description": "The Google Calendar event ID to delete."},
                        },
                        "required": ["event_id"],
                    },
                },
                {
                    "name": "list_events",
                    "description": "List the user's upcoming calendar events.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "days": {"type": "NUMBER", "description": "How many days ahead to look (default 1)."},
                        },
                    },
                },
                # ── To-Do ─────────────────────────────────────────────────
                {
                    "name": "add_todo",
                    "description": "Add a new task/to-do item to the user's list.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "title":    {"type": "STRING", "description": "Task title (e.g. 'Buy groceries')."},
                            "due_date": {"type": "STRING", "description": "YYYY-MM-DD (optional, defaults to today)."},
                            "due_time": {"type": "STRING", "description": "HH:MM (optional)."},
                            "priority": {"type": "STRING", "description": "high | medium | low (default: medium)."},
                            "category": {"type": "STRING", "description": "work | personal | health | study | other."},
                        },
                        "required": ["title"],
                    },
                },
                {
                    "name": "list_todos",
                    "description": "List the user's pending to-do items.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "days":   {"type": "NUMBER", "description": "How many days ahead to look (default 1)."},
                            "status": {"type": "STRING", "description": "Filter: pending | completed (default: pending)."},
                        },
                    },
                },
                {
                    "name": "complete_todo",
                    "description": "Mark a to-do item as completed. Use list_todos first to find the todo_id.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "todo_id": {"type": "STRING", "description": "The MongoDB ID of the todo to complete."},
                        },
                        "required": ["todo_id"],
                    },
                },
                {
                    "name": "delete_todo",
                    "description": "Permanently delete a to-do item. Use list_todos first to confirm the todo_id.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "todo_id": {"type": "STRING", "description": "The MongoDB ID of the todo to delete."},
                        },
                        "required": ["todo_id"],
                    },
                },
                {
                    "name": "end_conversation",
                    "description": "Call this when the user says bye, goodbye, or clearly wants to end the session.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {},
                    },
                },
            ]
        }
    ]

    # ------------------------------------------------------------------
    # Actual tool execution
    # ------------------------------------------------------------------
    async def _execute_tool(name: str, args: Dict[str, Any]) -> Dict:
        context = {"user_id": user_id}

        if name == "add_transaction":
            try:
                from datetime import datetime as dt

                # ── Type resolution ─────────────────────────────────────────
                VALID_TYPES = {"expense", "income", "lended", "borrowed"}
                tx_type = str(args.get("transaction_type", "expense")).lower().strip()
                if tx_type not in VALID_TYPES:
                    tx_type = "expense"  # safe default

                # ── Category resolution ────────────────────────────────────
                VALID_CATS = {
                    "food", "transport", "shopping", "bills",
                    "entertainment", "health", "personal",
                    "salary", "investment", "other",
                }
                # Income-type transactions get a sensible default category
                DEFAULT_CAT = {
                    "income":   "salary",
                    "lended":   "other",
                    "borrowed": "other",
                    "expense":  "other",
                }
                category = str(args.get("category", "")).lower().strip()
                if not category or category not in VALID_CATS:
                    category = DEFAULT_CAT.get(tx_type, "other")

                amount   = float(args.get("amount", 0))
                desc     = str(args.get("description") or category)
                date_str = args.get("date") or dt.now().strftime("%Y-%m-%d")
                person   = args.get("person", "")  # for lended / borrowed

                doc = {
                    "user_id":     user_id,
                    "type":        tx_type,
                    "amount":      amount,
                    "currency":    "INR",
                    "category":    category,
                    "description": desc,
                    "date":        date_str,
                    "created_at":  dt.utcnow(),
                }
                if person:
                    doc["person"] = person

                await transactions_collection.insert_one(doc)
                print(f"[GEMINI_LIVE][BG] add_transaction: {tx_type} ₹{amount} / {category} / {desc}")
                return {"status": "success", "type": tx_type}
            except Exception as e:
                print(f"[GEMINI_LIVE][BG] add_transaction error: {e}")
                return {"status": "error", "message": str(e)}

        elif name == "query_spending":
            resp = await finance_agent._handle_query(
                intent="query_spending",
                user_input=f"How much did I spend {args.get('time_range', 'this month')}?",
                context=context,
                memory={},
            )
            return {"status": "success", "response": resp.response}

        elif name == "schedule_event":
            from dateutil.parser import parse as dtparse
            from datetime import timedelta
            import pytz

            IST = pytz.timezone("Asia/Kolkata")

            def to_ist_iso(time_str: str) -> str:
                """Parse any time string and return an IST-aware ISO 8601 string.
                Gemini often outputs naive datetimes like '2026-04-28T15:00:00'
                with no TZ suffix — we assume those mean IST, not UTC.
                """
                parsed = dtparse(time_str)
                if parsed.tzinfo is None:
                    parsed = IST.localize(parsed)
                else:
                    parsed = parsed.astimezone(IST)
                return parsed.isoformat()

            start_iso = to_ist_iso(args["start_time"])
            end_str   = args.get("end_time")
            if end_str:
                end_iso = to_ist_iso(end_str)
            else:
                # Default: 1 hour after start
                naive_start = dtparse(args["start_time"]).replace(tzinfo=None)
                end_iso = to_ist_iso((naive_start + timedelta(hours=1)).isoformat())

            # ── Conflict check before creating ────────────────────────────────
            conflicts = await calendar_service.check_conflicts(
                user_id=user_id,
                start_time=start_iso,
                end_time=end_iso,
            )
            if conflicts:
                names = ", ".join(
                    f"'{e['title']}' at {e['start_time']}" for e in conflicts[:3]
                )
                return {
                    "status": "conflict",
                    "message": (
                        f"There's a scheduling conflict: {names}. "
                        "Ask the user: should I schedule anyway, cancel the existing event, "
                        "or pick a different time?"
                    ),
                    "conflicting_events": [{"title": e["title"], "start": e["start_time"], "id": e["id"]} for e in conflicts],
                }

            result = await calendar_service.create_event(
                user_id=user_id,
                title=args["title"],
                start_time=start_iso,
                end_time=end_iso,
                description=args.get("description", ""),
                timezone="Asia/Kolkata",
            )
            if result:
                return {"status": "success", "event_id": result.get("id")}
            return {"status": "error", "message": "Calendar not connected or event creation failed."}

        elif name == "update_event":
            from dateutil.parser import parse as dtparse
            import pytz
            IST = pytz.timezone("Asia/Kolkata")

            # Normalise any time strings in updates to IST
            updates = {k: v for k, v in args.items() if k != "event_id"}
            for time_field in ("start_time", "end_time"):
                if time_field in updates:
                    parsed = dtparse(updates[time_field])
                    if parsed.tzinfo is None:
                        parsed = IST.localize(parsed)
                    else:
                        parsed = parsed.astimezone(IST)
                    updates[time_field] = parsed.isoformat()

            result = await calendar_service.update_event(
                user_id=user_id,
                event_id=args["event_id"],
                updates=updates,
            )
            if result:
                return {"status": "success"}
            return {"status": "error", "message": "Failed to update — check event_id."}

        elif name == "delete_event":
            deleted = await calendar_service.delete_event(
                user_id=user_id,
                event_id=args["event_id"],
            )
            if deleted:
                return {"status": "success"}
            return {"status": "error", "message": "Failed to delete — check event_id."}

        elif name == "list_events":
            from datetime import datetime, timedelta

            days = int(args.get("days", 1))
            events = await calendar_service.list_events(
                user_id,
                time_min=datetime.utcnow(),
                time_max=datetime.utcnow() + timedelta(days=days),
            )
            return {"status": "success", "events": events or []}

        # ── To-Do tools ───────────────────────────────────────────────
        elif name == "add_todo":
            from datetime import datetime as dt
            try:
                result = await todo_service.add_todo(
                    user_id=user_id,
                    title=args.get("title", "Untitled task"),
                    due_date=args.get("due_date") or dt.now().strftime("%Y-%m-%d"),
                    due_time=args.get("due_time"),
                    priority=args.get("priority", "medium"),
                    category=args.get("category", "other"),
                )
                print(f"[GEMINI_LIVE][BG] add_todo written: {result.get('title')}")
                return {"status": "success", "todo_id": result.get("_id")}
            except Exception as e:
                print(f"[GEMINI_LIVE][BG] add_todo error: {e}")
                return {"status": "error", "message": str(e)}

        elif name == "list_todos":
            from datetime import datetime, timedelta

            days = int(args.get("days", 1))
            status = args.get("status", "pending")
            start_date = datetime.now().strftime("%Y-%m-%d")
            end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

            todos = await todo_service.get_todos(
                user_id,
                status=status,
                start_date=start_date,
                end_date=end_date,
                limit=20,
            )

            # Also fetch schedule context for cross-domain awareness
            schedule_summary = ""
            try:
                schedule_summary = await schedule_context.get_context_for_prompt(user_id, days=days)
            except Exception:
                pass

            return {
                "status": "success",
                "todos": todos or [],
                "schedule_context": schedule_summary,
            }

        elif name == "complete_todo":
            try:
                result = await todo_service.complete_todo(user_id, args["todo_id"])
                if result:
                    return {"status": "success", "title": result.get("title")}
                return {"status": "error", "message": "Todo not found."}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        elif name == "delete_todo":
            try:
                deleted = await todo_service.delete_todo(user_id, args["todo_id"])
                if deleted:
                    return {"status": "success"}
                return {"status": "error", "message": "Todo not found."}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        elif name == "list_expenses":
            from datetime import datetime as dt, timedelta
            from bson import ObjectId
            days    = int(args.get("days", 7))
            limit   = int(args.get("limit", 10))
            cat     = args.get("category", "").lower().strip() or None
            start   = dt.utcnow() - timedelta(days=days)
            q = {
                "user_id": user_id,
                "$or": [
                    {"created_at": {"$gte": start}},
                    {"date": {"$gte": start.strftime("%Y-%m-%d")}},
                ],
            }
            if cat:
                q["category"] = cat
            cursor = transactions_collection.find(q).sort("created_at", -1).limit(limit)
            docs = await cursor.to_list(length=limit)
            items = []
            for d in docs:
                date_raw = d.get("date") or d.get("created_at", "")
                date_str = date_raw.strftime("%Y-%m-%d") if hasattr(date_raw, "strftime") else str(date_raw)[:10]
                items.append({
                    "id":          str(d["_id"]),
                    "amount":      d.get("amount"),
                    "category":    d.get("category"),
                    "description": d.get("description", ""),
                    "date":        date_str,
                })
            return {"status": "success", "expenses": items, "count": len(items)}

        elif name == "update_expense":
            from bson import ObjectId
            expense_id = args.get("expense_id", "")
            try:
                oid = ObjectId(expense_id)
            except Exception:
                return {"status": "error", "message": f"Invalid expense_id: {expense_id}"}

            updates: Dict[str, Any] = {}
            if "amount"      in args: updates["amount"]      = float(args["amount"])
            if "category"    in args: updates["category"]    = str(args["category"]).lower()
            if "description" in args: updates["description"] = str(args["description"])
            if "date"        in args: updates["date"]        = str(args["date"])
            if not updates:
                return {"status": "error", "message": "No fields to update."}

            from datetime import datetime as dt
            updates["updated_at"] = dt.utcnow()
            result = await transactions_collection.update_one(
                {"_id": oid, "user_id": user_id},
                {"$set": updates},
            )
            if result.matched_count == 0:
                return {"status": "error", "message": "Expense not found — check the ID."}
            print(f"[GEMINI_LIVE][BG] update_expense {expense_id}: {updates}")
            return {"status": "success"}

        elif name == "delete_expense":
            from bson import ObjectId
            expense_id = args.get("expense_id", "")
            try:
                oid = ObjectId(expense_id)
            except Exception:
                return {"status": "error", "message": f"Invalid expense_id: {expense_id}"}

            result = await transactions_collection.delete_one({"_id": oid, "user_id": user_id})
            if result.deleted_count == 0:
                return {"status": "error", "message": "Expense not found — check the ID."}
            print(f"[GEMINI_LIVE][BG] delete_expense {expense_id} done")
            return {"status": "success"}

        elif name == "get_budget_status":
            from services.budget_service import BudgetService
            from services.db import budgets_collection as bc
            from datetime import datetime as dt
            budget_svc = BudgetService(bc, transactions_collection)

            # Get this month's spending by category
            now = dt.utcnow()
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            pipeline = [
                {"$match": {
                    "user_id": user_id,
                    "type": "expense",
                    "$or": [
                        {"created_at": {"$gte": start}},
                        {"date": {"$gte": start.strftime("%Y-%m-%d")}},
                    ],
                }},
                {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
            ]
            cursor = transactions_collection.aggregate(pipeline)
            rows = await cursor.to_list(length=50)
            spending = {r["_id"]: r["total"] for r in rows}
            status = await budget_svc.get_budget_status(user_id, spending)
            return {"status": "success", "budget_status": status}

        elif name == "set_budget":
            from services.budget_service import BudgetService
            from services.db import budgets_collection as bc
            budget_svc = BudgetService(bc, transactions_collection)
            category = str(args.get("category", "other")).lower()
            limit    = float(args.get("limit", 0))
            if limit <= 0:
                return {"status": "error", "message": "Budget limit must be greater than 0."}
            await budget_svc.set_category_budget(user_id, category, limit)
            print(f"[GEMINI_LIVE] set_budget {category}=₹{limit}")
            return {"status": "success", "category": category, "limit": limit}

        elif name == "end_conversation":
            return {"status": "end_conversation"}

        return {"error": f"Unknown tool: {name}"}

    # ------------------------------------------------------------------
    # Background task wrapper with error logging
    # ------------------------------------------------------------------
    async def _run_in_background(name: str, args: Dict[str, Any]):
        try:
            result = await _execute_tool(name, args)
            if result.get("status") == "error":
                print(f"[GEMINI_LIVE][BG] Tool '{name}' returned error: {result}")
            else:
                print(f"[GEMINI_LIVE][BG] Tool '{name}' completed successfully.")
        except Exception as e:
            print(f"[GEMINI_LIVE][BG] Tool '{name}' raised exception: {e}")
            import traceback; traceback.print_exc()

    # ------------------------------------------------------------------
    # Public handler: write tools ACK immediately and run in background
    # ------------------------------------------------------------------
    async def handle_tool_call(name: str, args: Dict[str, Any]) -> Dict:
        print(f"[GEMINI_LIVE] Tool call: {name}  args={args}")

        if name in BACKGROUND_TOOLS:
            # Fire-and-forget with proper error logging
            asyncio.create_task(_run_in_background(name, args))
            return {"status": "queued", "message": ACK_MESSAGES.get(name, "done.")}

        # Query tools (and end_conversation): awaited
        return await _execute_tool(name, args)

    return tools, handle_tool_call


# ---------------------------------------------------------------------------
# System prompt builder for Gemini Live
# Sent ONCE per session (connection time) — zero per-turn token cost.
# ---------------------------------------------------------------------------
def _build_gemini_system_prompt(schedule_ctx_text: str = "") -> str:
    """
    Build the Gemini Live system_instruction by composing:
      1. RIVA Brain persona + current time context + productivity skills
      2. Gemini-specific tool rules (timezone, TO-DO vs Calendar, response style)
      3. Optional live schedule context

    The result is sent once at session start — not on every turn.
    Prompt length: ~1,200 tokens (was ~350). Cost impact: negligible because
    Gemini Live caches the system_instruction across the session.
    """
    time_ctx = get_time_context()

    # Core RIVA persona + productivity skills (planning mode = rich skills)
    base = build_riva_system_prompt(
        mode="planning",
        time_ctx=time_ctx,
        extra_skills=["finance", "wellness", "habits"],
    )

    # Gemini Live-specific rules (tool usage, timezone, voice style)
    gemini_rules = """
VOICE & TOOL RULES (Gemini Live):
- You are voice-first. Every response will be spoken aloud — be concise and natural.
- TIMEZONE: User is in India (IST, UTC+5:30). All datetimes must use +05:30 offset.
  Example: '2026-04-28T15:00:00+05:30'. Never assume UTC.

TO-DO vs CALENDAR (critical distinction):
- Tasks/to-dos → trackable items with no fixed time slot → add_todo, list_todos, complete_todo, delete_todo
- Events/meetings → time-bound calendar entries → schedule_event, list_events, update_event, delete_event
- When adding a task, check schedule context to suggest a good time if relevant.
- When listing tasks, mention overlapping calendar events.

TRANSACTION MANAGEMENT (add_transaction tool):
- Use add_transaction for ALL money movements — expense, income, lended, borrowed.
- ALWAYS pass the correct transaction_type:
    expense  → user spent money (food, shopping, bills, etc.)
    income   → user received money (salary, freelance, gift, refund)
    lended   → user gave money to someone ("I gave Rahul ₹500")
    borrowed → user received money as a loan ("I borrowed ₹1000 from mom")
- For lended/borrowed, also pass person="<name>" when mentioned.
- To update or delete a transaction: call list_expenses first to find the ID, then update_expense or delete_expense.
- Example: "I paid ₹200 for lunch" → add_transaction(transaction_type="expense", amount=200, category="food", description="lunch")
- Example: "I got my salary ₹50000" → add_transaction(transaction_type="income", amount=50000, category="salary", description="salary")
- Example: "I lent Rahul ₹500" → add_transaction(transaction_type="lended", amount=500, category="other", description="lent to Rahul", person="Rahul")

BUDGET TOOLS:
- get_budget_status → shows this month's spending vs limits. Call proactively after any large expense.
- set_budget → sets a monthly limit for a category. E.g. user says "set food budget to 8000".
- After recording an expense: if that category is at warning/over, mention it in one sentence.

TOOL BEHAVIOUR:
- For write operations: confirm in ONE short sentence. Never repeat back all the details.
- For query results (spending, events, tasks): give the key numbers/names directly, no filler.
- status=error: briefly tell the user what went wrong.
- status=conflict: name the conflicting event and ask what to do.
- For update/delete: call list_* first to get the ID, then act.
- You may call multiple tools in one turn when needed.
- If the user says bye/goodbye: say a brief farewell and call end_conversation.

PROACTIVE BEHAVIOUR:
- After any expense, call get_budget_status if the category might be near its limit.
- After adding a todo, if there's a free slot on the calendar, suggest using it.
- Keep proactive additions to ≤1 sentence — don't overwhelm.
"""

    parts = [base.strip(), gemini_rules.strip()]

    if schedule_ctx_text:
        parts.append(f"CURRENT SCHEDULE CONTEXT:\n{schedule_ctx_text}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
@router.websocket("/gemini-live")
async def gemini_live_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("[GEMINI_LIVE] WebSocket connected")

    # ── Auth ──────────────────────────────────────────────────────────
    user_id = "anonymous"
    try:
        token = websocket.query_params.get("token")
        if token and token != "mock_token":
            import jwt
            decoded = jwt.decode(token, options={"verify_signature": False})
            user_id = decoded.get("user_id") or decoded.get("sub") or "anonymous"
    except Exception as e:
        print(f"[GEMINI_LIVE] Auth warning: {e}")

    # ── API key ───────────────────────────────────────────────────────
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        await websocket.send_json({"error": "GEMINI_API_KEY not configured on backend."})
        await websocket.close()
        return

    print(f"[GEMINI_LIVE] API key loaded ({api_key[:8]}…), user={user_id}")

    # ── Build session ─────────────────────────────────────────────────
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    tools, handle_tool_call = await get_tools_and_handlers(user_id)

    # Build shared schedule context for the system prompt
    schedule_ctx_text = ""
    try:
        from services.todo_service import TodoService as _TS
        from services.schedule_context import ScheduleContext as _SC
        from services.calendar_service import CalendarService as _CS
        from services.db import calendar_tokens_collection as _ctc, todos_collection as _tc
        _sc = _SC(calendar_service=_CS(_ctc), todo_service=_TS(_tc))
        schedule_ctx_text = await _sc.get_context_for_prompt(user_id, days=2)
    except Exception as e:
        print(f"[GEMINI_LIVE] Schedule context build error: {e}")

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        tools=tools,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part(text=_build_gemini_system_prompt(
                schedule_ctx_text=schedule_ctx_text,
            ))],
        ),
    )

    # gemini-live-2.5-flash-preview is the canonical Live API model that supports:
    # - send_realtime_input (streaming PCM audio)
    # - speech_config with PrebuiltVoiceConfig
    # - response_modalities=["AUDIO"]
    # - function calling / tool responses
    # gemini-2.5-flash-native-audio-latest is a DIFFERENT model (native audio generation,
    # not the bidirectional Live API) and returns 1008 with these features.
    # Free tier: gemini-2.0-flash-live-001
    # Paid/preview tier: gemini-2.5-flash-preview-native-audio-dialog
    model_id = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
    MAX_RECONNECT_ATTEMPTS = 5

    # The browser WebSocket stays open across Gemini reconnects.
    # Only the Gemini session is re-established on transient errors.
    for attempt in range(MAX_RECONNECT_ATTEMPTS):
        try:
            if attempt > 0:
                wait = min(2 ** attempt, 16)  # 2, 4, 8, 16 seconds
                print(f"[GEMINI_LIVE] Reconnect attempt {attempt}/{MAX_RECONNECT_ATTEMPTS} in {wait}s…")
                await websocket.send_json({"type": "reconnecting", "attempt": attempt})
                await asyncio.sleep(wait)

            async with client.aio.live.connect(model=model_id, config=config) as session:
                print(f"[GEMINI_LIVE] Connected to Gemini Live API (attempt {attempt + 1})")
                if attempt > 0:
                    await websocket.send_json({"type": "reconnected"})

                # shared event so receive_from_frontend can stop sending when
                # the Gemini session is closing
                session_alive = asyncio.Event()
                session_alive.set()

                # ── Task 1: Gemini → Frontend ─────────────────────────────
                async def receive_from_gemini():
                    # session.receive() covers exactly ONE turn then exits.
                    # Loop to handle unlimited multi-turn conversations.
                    while True:
                        async for message in session.receive():
                            # ── Audio chunks ──────────────────────────────
                            if message.server_content:
                                if message.server_content.model_turn:
                                    for part in message.server_content.model_turn.parts:
                                        if part.inline_data:
                                            audio_b64 = base64.b64encode(
                                                part.inline_data.data
                                            ).decode("utf-8")
                                            await websocket.send_json(
                                                {"type": "audio", "data": audio_b64}
                                            )
                                if message.server_content.turn_complete:
                                    await websocket.send_json({"type": "turn_complete"})

                            # ── Tool calls (possibly multiple per turn) ───
                            if message.tool_call:
                                calls = message.tool_call.function_calls
                                should_close = False

                                # Execute all tool calls in this turn CONCURRENTLY
                                async def resolve_call(call):
                                    result = await handle_tool_call(call.name, call.args)
                                    return call, types.FunctionResponse(
                                        name=call.name,
                                        id=call.id,
                                        response=result,
                                    )

                                resolved = await asyncio.gather(
                                    *[resolve_call(c) for c in calls]
                                )

                                # Send all responses, check for end_conversation
                                for original_call, resp in resolved:
                                    if original_call.name == "end_conversation":
                                        should_close = True
                                    await session.send_tool_response(
                                        function_responses=resp
                                    )

                                if should_close:
                                    print("[GEMINI_LIVE] Conversation ended by user.")
                                    await websocket.send_json({"type": "session_end"})
                                    await websocket.close()
                                    return

                # ── Task 2: Frontend → Gemini ─────────────────────────────
                async def receive_from_frontend():
                    try:
                        while True:
                            data = await websocket.receive()
                            if "bytes" in data:
                                # Raw PCM from browser mic (16 kHz, 16-bit, mono)
                                await session.send_realtime_input(
                                    audio=types.Blob(
                                        data=data["bytes"],
                                        mime_type="audio/pcm;rate=16000",
                                    )
                                )
                            elif "text" in data:
                                msg = json.loads(data["text"])
                                msg_type = msg.get("type")

                                if msg_type == "barge_in":
                                    # User spoke while RIVA was talking.
                                    # Send activity_start so Gemini knows to stop
                                    # generating and pay attention to incoming audio.
                                    print("[GEMINI_LIVE] Barge-in detected — signalling Gemini")
                                    try:
                                        await session.send_realtime_input(
                                            activity_start=types.ActivityStart()
                                        )
                                    except Exception as e:
                                        print(f"[GEMINI_LIVE] activity_start error: {e}")

                                elif msg_type == "input_text":
                                    await session.send_client_content(
                                        turns=types.Content(
                                            role="user",
                                            parts=[types.Part(text=msg["text"])],
                                        ),
                                        turn_complete=True,
                                    )
                    except WebSocketDisconnect:
                        raise
                    except Exception as e:
                        print(f"[GEMINI_LIVE] Frontend receive error: {e}")

                await asyncio.gather(receive_from_gemini(), receive_from_frontend())
                break  # Clean exit — don't retry

        except WebSocketDisconnect:
            print("[GEMINI_LIVE] Browser WebSocket disconnected")
            break  # User closed the browser tab — stop completely

        except Exception as e:
            err_str = str(e)
            err_code = ""
            # Extract numeric WS close code from the error string
            import re as _re
            m = _re.search(r'(\d{4})', err_str)
            if m:
                err_code = m.group(1)

            # 1006 / 1011 / 1012 = network-level drops → transient, retry
            # 1008 (policy violation) / 1003 (unsupported data) = API rejects
            #   our request → fatal, do NOT retry (retrying won't help)
            TRANSIENT_CODES = {"1006", "1011", "1012"}
            FATAL_CODES     = {"1008", "1003", "1007", "1009", "1010"}

            is_transient = (
                err_code in TRANSIENT_CODES
                or "abnormal closure" in err_str
                or "ConnectionReset" in type(e).__name__
            )
            is_fatal_policy = err_code in FATAL_CODES

            if is_fatal_policy:
                # Policy/capability error — retrying will always fail
                print(f"[GEMINI_LIVE] Fatal API policy error ({err_code}): {e}")
                user_msg = (
                    "This Gemini model or feature is not enabled for your API key. "
                    "Check the model name and API key permissions."
                    if err_code == "1008" else
                    f"Gemini rejected the connection (error {err_code})."
                )
                try:
                    await websocket.send_json({"type": "error", "message": user_msg})
                except Exception:
                    pass
                break

            elif is_transient and attempt < MAX_RECONNECT_ATTEMPTS - 1:
                print(f"[GEMINI_LIVE] Transient disconnect ({err_code or e}) — will retry…")
                continue  # Go to next attempt

            else:
                print(f"[GEMINI_LIVE] Unhandled error: {e}")
                import traceback
                traceback.print_exc()
                try:
                    await websocket.send_json({"type": "error", "message": "Connection to Gemini lost. Please try again."})
                except Exception:
                    pass
                break
    else:
        # Exhausted all retries
        try:
            await websocket.send_json({"type": "error", "message": "Could not reconnect to Gemini after several attempts."})
        except Exception:
            pass

    print("[GEMINI_LIVE] Session ended")
