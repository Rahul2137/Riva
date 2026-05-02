"""
Calendar Routes - REST API for calendar management.
Flutter UI calls these endpoints directly.
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

from services.calendar_service import CalendarService
from services.db import calendar_tokens_collection

load_dotenv()

router = APIRouter(prefix="/calendar", tags=["Calendar"])

# Singleton calendar service
_calendar_service = CalendarService(calendar_tokens_collection)

# Base URL for OAuth redirects
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


# ----------------------------
# Request/Response Models
# ----------------------------
class EventCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    start_time: str  # ISO format: 2026-04-15T10:00:00
    end_time: str
    timezone: Optional[str] = "Asia/Kolkata"


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    timezone: Optional[str] = None


# ----------------------------
# OAuth Endpoints
# ----------------------------

@router.get("/status")
async def calendar_status(user_id: str = Query(..., description="User ID")):
    """Check if user has connected their Google Calendar."""
    connected = await _calendar_service.is_connected(user_id)
    return {"connected": connected, "user_id": user_id}


@router.get("/oauth/url")
async def get_oauth_url(user_id: str = Query(..., description="User ID")):
    """Get the Google OAuth URL for calendar authorization."""
    redirect_uri = f"{BASE_URL}/calendar/oauth/callback"
    url = await _calendar_service.get_oauth_url(user_id, redirect_uri)
    return {"oauth_url": url}


@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
):
    """Handle OAuth callback from Google."""
    if error:
        return {"success": False, "error": error}

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    user_id = state  # We passed user_id as the state parameter
    redirect_uri = f"{BASE_URL}/calendar/oauth/callback"

    success = await _calendar_service.exchange_code(code, user_id, redirect_uri)

    if success:
        # Return success page that the mobile app can detect
        return {
            "success": True,
            "message": "Google Calendar connected successfully!",
            "user_id": user_id,
        }
    else:
        raise HTTPException(status_code=400, detail="Failed to connect Google Calendar")


@router.post("/disconnect")
async def disconnect_calendar(user_id: str = Query(..., description="User ID")):
    """Disconnect user's Google Calendar."""
    result = await _calendar_service.disconnect(user_id)
    return {"success": result, "message": "Calendar disconnected"}


# ----------------------------
# Event CRUD Endpoints
# ----------------------------

@router.get("/events")
async def list_events(
    user_id: str = Query(..., description="User ID"),
    days: int = Query(7, description="Number of days to fetch"),
    max_results: int = Query(20, le=50),
):
    """List upcoming calendar events."""
    connected = await _calendar_service.is_connected(user_id)
    if not connected:
        return {"events": [], "connected": False, "message": "Calendar not connected"}

    time_min = datetime.utcnow()
    time_max = time_min + timedelta(days=days)

    events = await _calendar_service.list_events(
        user_id, time_min=time_min, time_max=time_max, max_results=max_results
    )
    return {"events": events, "connected": True, "count": len(events)}


@router.post("/events")
async def create_event(
    user_id: str = Query(..., description="User ID"),
    event: EventCreate = None,
):
    """Create a new calendar event."""
    connected = await _calendar_service.is_connected(user_id)
    if not connected:
        raise HTTPException(status_code=400, detail="Calendar not connected")

    result = await _calendar_service.create_event(
        user_id=user_id,
        title=event.title,
        start_time=event.start_time,
        end_time=event.end_time,
        description=event.description or "",
        timezone=event.timezone or "Asia/Kolkata",
    )

    if result:
        return {"success": True, "event": result}
    else:
        raise HTTPException(status_code=500, detail="Failed to create event")


@router.put("/events/{event_id}")
async def update_event(
    event_id: str,
    user_id: str = Query(..., description="User ID"),
    event: EventUpdate = None,
):
    """Update an existing calendar event."""
    connected = await _calendar_service.is_connected(user_id)
    if not connected:
        raise HTTPException(status_code=400, detail="Calendar not connected")

    updates = {}
    if event.title is not None:
        updates["title"] = event.title
    if event.description is not None:
        updates["description"] = event.description
    if event.start_time is not None:
        updates["start_time"] = event.start_time
    if event.end_time is not None:
        updates["end_time"] = event.end_time
    if event.timezone is not None:
        updates["timezone"] = event.timezone

    result = await _calendar_service.update_event(user_id, event_id, updates)
    if result:
        return {"success": True, "event": result}
    else:
        raise HTTPException(status_code=500, detail="Failed to update event")


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    user_id: str = Query(..., description="User ID"),
):
    """Delete a calendar event."""
    connected = await _calendar_service.is_connected(user_id)
    if not connected:
        raise HTTPException(status_code=400, detail="Calendar not connected")

    result = await _calendar_service.delete_event(user_id, event_id)
    return {"success": result}
