"""
Todo Routes - REST API for to-do list management.
Web UI calls these endpoints for CRUD operations.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from services.todo_service import TodoService
from services.db import todos_collection

router = APIRouter(prefix="/todos", tags=["Todos"])

# Singleton todo service
_todo_service = TodoService(todos_collection)


# ----------------------------
# Request/Response Models
# ----------------------------
class TodoCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    due_date: Optional[str] = None  # YYYY-MM-DD
    due_time: Optional[str] = None  # HH:MM
    priority: Optional[str] = "medium"  # high | medium | low
    category: Optional[str] = "other"  # work | personal | health | study | other


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None


# ----------------------------
# CRUD Endpoints
# ----------------------------

@router.get("")
async def list_todos(
    user_id: str = Query(..., description="User ID"),
    days: int = Query(7, description="Number of days to fetch"),
    status: Optional[str] = Query(None, description="Filter: pending | completed"),
    grouped: bool = Query(False, description="Group by date"),
):
    """List to-do items, optionally grouped by date."""
    if grouped:
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        result = await _todo_service.get_todos_grouped_by_date(
            user_id,
            start_date=start_date,
            end_date=end_date,
            include_completed=(status != "pending"),
        )
        return {"todos": result, "grouped": True}

    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    todos = await _todo_service.get_todos(
        user_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    return {"todos": todos, "count": len(todos)}


@router.get("/stats")
async def get_stats(
    user_id: str = Query(..., description="User ID"),
):
    """Get quick to-do stats."""
    stats = await _todo_service.get_stats(user_id)
    return stats


@router.post("")
async def create_todo(
    user_id: str = Query(..., description="User ID"),
    todo: TodoCreate = None,
):
    """Create a new to-do item."""
    result = await _todo_service.add_todo(
        user_id=user_id,
        title=todo.title,
        description=todo.description or "",
        due_date=todo.due_date,
        due_time=todo.due_time,
        priority=todo.priority or "medium",
        category=todo.category or "other",
    )
    return {"success": True, "todo": result}


@router.put("/{todo_id}")
async def update_todo(
    todo_id: str,
    user_id: str = Query(..., description="User ID"),
    todo: TodoUpdate = None,
):
    """Update an existing to-do item."""
    updates = {}
    if todo.title is not None:
        updates["title"] = todo.title
    if todo.description is not None:
        updates["description"] = todo.description
    if todo.due_date is not None:
        updates["due_date"] = todo.due_date
    if todo.due_time is not None:
        updates["due_time"] = todo.due_time
    if todo.priority is not None:
        updates["priority"] = todo.priority
    if todo.category is not None:
        updates["category"] = todo.category
    if todo.status is not None:
        updates["status"] = todo.status

    result = await _todo_service.update_todo(user_id, todo_id, updates)
    if result:
        return {"success": True, "todo": result}
    raise HTTPException(status_code=404, detail="Todo not found")


@router.post("/{todo_id}/complete")
async def complete_todo(
    todo_id: str,
    user_id: str = Query(..., description="User ID"),
):
    """Mark a to-do as completed."""
    result = await _todo_service.complete_todo(user_id, todo_id)
    if result:
        return {"success": True, "todo": result}
    raise HTTPException(status_code=404, detail="Todo not found")


@router.post("/{todo_id}/uncomplete")
async def uncomplete_todo(
    todo_id: str,
    user_id: str = Query(..., description="User ID"),
):
    """Reopen a completed to-do."""
    result = await _todo_service.uncomplete_todo(user_id, todo_id)
    if result:
        return {"success": True, "todo": result}
    raise HTTPException(status_code=404, detail="Todo not found")


@router.delete("/{todo_id}")
async def delete_todo(
    todo_id: str,
    user_id: str = Query(..., description="User ID"),
):
    """Delete a to-do item."""
    result = await _todo_service.delete_todo(user_id, todo_id)
    if result:
        return {"success": True}
    raise HTTPException(status_code=404, detail="Todo not found")
