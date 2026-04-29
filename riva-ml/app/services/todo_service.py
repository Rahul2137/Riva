"""
Todo Service - MongoDB CRUD for date-wise to-do items.

Stores tasks per user with due dates, priorities, categories,
and completion status. Designed to work alongside CalendarService
through the shared ScheduleContext layer.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from bson import ObjectId


class TodoService:
    """CRUD operations for the `todos` MongoDB collection."""

    def __init__(self, todos_collection):
        self.collection = todos_collection

    @staticmethod
    def _serialize_doc(doc: Dict) -> Dict:
        """Convert ObjectId and datetime fields to JSON-safe strings."""
        from bson import ObjectId as _ObjId
        for key, val in list(doc.items()):
            if isinstance(val, _ObjId):
                doc[key] = str(val)
            elif isinstance(val, datetime):
                doc[key] = val.isoformat()
        return doc

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def add_todo(
        self,
        user_id: str,
        title: str,
        due_date: str = None,
        due_time: str = None,
        priority: str = "medium",
        category: str = "other",
        description: str = "",
    ) -> Dict[str, Any]:
        """Create a new to-do item.

        Args:
            user_id: Firebase UID.
            title: Task title (e.g. "Buy groceries").
            due_date: YYYY-MM-DD string (defaults to today).
            due_time: HH:MM string (optional).
            priority: high | medium | low.
            category: work | personal | health | study | other.
            description: Extended notes.

        Returns:
            The inserted document with string _id.
        """
        valid_priorities = {"high", "medium", "low"}
        valid_categories = {"work", "personal", "health", "study", "other"}

        priority = priority.lower() if priority.lower() in valid_priorities else "medium"
        category = category.lower() if category.lower() in valid_categories else "other"

        if not due_date:
            due_date = datetime.now().strftime("%Y-%m-%d")

        doc = {
            "user_id": user_id,
            "title": title,
            "description": description,
            "due_date": due_date,
            "due_time": due_time,
            "priority": priority,
            "category": category,
            "status": "pending",
            "completed_at": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        result = await self.collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return self._serialize_doc(doc)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_todos(
        self,
        user_id: str,
        status: str = None,
        due_date: str = None,
        start_date: str = None,
        end_date: str = None,
        priority: str = None,
        category: str = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query to-do items with optional filters.

        Priority sort order: high → medium → low, then by due_date ASC.
        """
        query: Dict[str, Any] = {"user_id": user_id}

        if status:
            query["status"] = status
        if due_date:
            query["due_date"] = due_date
        if start_date and end_date:
            query["due_date"] = {"$gte": start_date, "$lte": end_date}
        elif start_date:
            query["due_date"] = {"$gte": start_date}
        elif end_date:
            query["due_date"] = {"$lte": end_date}
        if priority:
            query["priority"] = priority.lower()
        if category:
            query["category"] = category.lower()

        # Sort: priority (high first), then due_date ascending
        priority_order = {"high": 0, "medium": 1, "low": 2}
        cursor = (
            self.collection.find(query)
            .sort([("due_date", 1), ("created_at", 1)])
            .limit(limit)
        )
        todos = await cursor.to_list(length=limit)

        for t in todos:
            self._serialize_doc(t)

        # In-memory priority sort (Mongo doesn't natively sort by custom order)
        todos.sort(key=lambda x: (x["due_date"], priority_order.get(x["priority"], 1)))
        return todos

    async def get_todos_grouped_by_date(
        self,
        user_id: str,
        start_date: str = None,
        end_date: str = None,
        include_completed: bool = False,
    ) -> Dict[str, List[Dict]]:
        """Return todos grouped by due_date, ideal for UI rendering.

        Returns:
            {"2026-04-28": [todo, ...], "2026-04-29": [...], ...}
        """
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
        if not end_date:
            end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        status_filter = None if include_completed else "pending"
        todos = await self.get_todos(
            user_id,
            status=status_filter,
            start_date=start_date,
            end_date=end_date,
            limit=200,
        )

        grouped: Dict[str, List[Dict]] = {}
        for todo in todos:
            date_key = todo.get("due_date", "unscheduled")
            if date_key not in grouped:
                grouped[date_key] = []
            grouped[date_key].append(todo)

        return grouped

    async def get_todo_by_id(self, user_id: str, todo_id: str) -> Optional[Dict]:
        """Fetch a single to-do by its ID."""
        try:
            doc = await self.collection.find_one(
                {"_id": ObjectId(todo_id), "user_id": user_id}
            )
            if doc:
                self._serialize_doc(doc)
            return doc
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_todo(
        self, user_id: str, todo_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict]:
        """Update fields of an existing to-do item."""
        allowed_fields = {
            "title", "description", "due_date", "due_time",
            "priority", "category", "status", "completed_at",
        }
        clean_updates = {k: v for k, v in updates.items() if k in allowed_fields}
        clean_updates["updated_at"] = datetime.utcnow()

        try:
            result = await self.collection.find_one_and_update(
                {"_id": ObjectId(todo_id), "user_id": user_id},
                {"$set": clean_updates},
                return_document=True,
            )
            if result:
                self._serialize_doc(result)
            return result
        except Exception:
            return None

    async def complete_todo(self, user_id: str, todo_id: str) -> Optional[Dict]:
        """Mark a to-do as completed."""
        return await self.update_todo(
            user_id,
            todo_id,
            {"status": "completed", "completed_at": datetime.utcnow()},
        )

    async def uncomplete_todo(self, user_id: str, todo_id: str) -> Optional[Dict]:
        """Reopen a completed to-do."""
        try:
            result = await self.collection.find_one_and_update(
                {"_id": ObjectId(todo_id), "user_id": user_id},
                {
                    "$set": {
                        "status": "pending",
                        "completed_at": None,
                        "updated_at": datetime.utcnow(),
                    }
                },
                return_document=True,
            )
            if result:
                self._serialize_doc(result)
            return result
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_todo(self, user_id: str, todo_id: str) -> bool:
        """Permanently delete a to-do item."""
        try:
            result = await self.collection.delete_one(
                {"_id": ObjectId(todo_id), "user_id": user_id}
            )
            return result.deleted_count > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Helpers (used by ScheduleContext)
    # ------------------------------------------------------------------

    async def get_upcoming_todos(
        self, user_id: str, days: int = 3
    ) -> List[Dict[str, Any]]:
        """Get pending todos for the next N days (used by shared context)."""
        start = datetime.now().strftime("%Y-%m-%d")
        end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        return await self.get_todos(
            user_id, status="pending", start_date=start, end_date=end, limit=30
        )

    async def get_overdue_todos(self, user_id: str) -> List[Dict[str, Any]]:
        """Get pending todos with due_date before today."""
        today = datetime.now().strftime("%Y-%m-%d")
        return await self.get_todos(
            user_id, status="pending", end_date=today, limit=20
        )

    async def get_stats(self, user_id: str) -> Dict[str, int]:
        """Quick stats: total pending, completed today, overdue."""
        today = datetime.now().strftime("%Y-%m-%d")

        pending = await self.collection.count_documents(
            {"user_id": user_id, "status": "pending"}
        )
        completed_today = await self.collection.count_documents(
            {"user_id": user_id, "status": "completed", "due_date": today}
        )
        overdue = await self.collection.count_documents(
            {"user_id": user_id, "status": "pending", "due_date": {"$lt": today}}
        )

        return {
            "pending": pending,
            "completed_today": completed_today,
            "overdue": overdue,
        }
