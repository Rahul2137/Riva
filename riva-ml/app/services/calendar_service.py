"""
Calendar Service - Google Calendar API wrapper.

Per-user OAuth token storage in MongoDB (not pickle files).
Handles token refresh, CRUD operations, and conflict detection.
"""
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

# Google OAuth Config
GOOGLE_CALENDAR_CLIENT_ID = os.getenv("GOOGLE_CALENDAR_CLIENT_ID", "")
GOOGLE_CALENDAR_CLIENT_SECRET = os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "")
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarService:
    """Google Calendar API wrapper with per-user OAuth."""

    def __init__(self, calendar_tokens_collection=None):
        self.tokens_collection = calendar_tokens_collection

    # ------------------------------------------------------------------
    # OAuth Token Management
    # ------------------------------------------------------------------

    async def get_oauth_url(self, user_id: str, redirect_uri: str) -> str:
        """Generate Google OAuth URL for calendar access."""
        from urllib.parse import urlencode

        params = {
            "client_id": GOOGLE_CALENDAR_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(CALENDAR_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": user_id,  # Pass user_id through OAuth state
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    async def exchange_code(self, code: str, user_id: str, redirect_uri: str) -> bool:
        """Exchange OAuth code for tokens and store them."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": GOOGLE_CALENDAR_CLIENT_ID,
                        "client_secret": GOOGLE_CALENDAR_CLIENT_SECRET,
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri,
                    },
                )
                token_data = response.json()

                if "access_token" not in token_data:
                    print(f"[CALENDAR] Token exchange failed: {token_data}")
                    return False

                # Store tokens in MongoDB
                await self._store_tokens(user_id, token_data)
                print(f"[CALENDAR] Tokens stored for user {user_id}")
                return True
        except Exception as e:
            print(f"[CALENDAR] Token exchange error: {e}")
            return False

    async def _store_tokens(self, user_id: str, token_data: Dict):
        """Store OAuth tokens in MongoDB."""
        if self.tokens_collection is None:
            return

        await self.tokens_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "access_token": token_data["access_token"],
                    "refresh_token": token_data.get("refresh_token"),
                    "token_type": token_data.get("token_type", "Bearer"),
                    "expires_at": datetime.utcnow()
                    + timedelta(seconds=token_data.get("expires_in", 3600)),
                    "scope": token_data.get("scope", ""),
                    "updated_at": datetime.utcnow(),
                },
                "$setOnInsert": {"created_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def _get_access_token(self, user_id: str) -> Optional[str]:
        """Get a valid access token, refreshing if expired."""
        if self.tokens_collection is None:
            return None

        token_doc = await self.tokens_collection.find_one({"user_id": user_id})
        if not token_doc:
            return None

        # Check if token is expired
        expires_at = token_doc.get("expires_at")
        if expires_at and datetime.utcnow() >= expires_at:
            # Refresh the token
            refreshed = await self._refresh_token(user_id, token_doc.get("refresh_token"))
            if not refreshed:
                return None
            token_doc = await self.tokens_collection.find_one({"user_id": user_id})

        return token_doc.get("access_token")

    async def _refresh_token(self, user_id: str, refresh_token: str) -> bool:
        """Refresh an expired access token."""
        if not refresh_token:
            return False

        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": GOOGLE_CALENDAR_CLIENT_ID,
                        "client_secret": GOOGLE_CALENDAR_CLIENT_SECRET,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
                token_data = response.json()

                if "access_token" not in token_data:
                    print(f"[CALENDAR] Token refresh failed: {token_data}")
                    return False

                # Keep the existing refresh_token (Google doesn't always return a new one)
                token_data.setdefault("refresh_token", refresh_token)
                await self._store_tokens(user_id, token_data)
                return True
        except Exception as e:
            print(f"[CALENDAR] Token refresh error: {e}")
            return False

    async def is_connected(self, user_id: str) -> bool:
        """Check if user has connected their Google Calendar."""
        if self.tokens_collection is None:
            return False
        token_doc = await self.tokens_collection.find_one({"user_id": user_id})
        return token_doc is not None and token_doc.get("access_token") is not None

    async def disconnect(self, user_id: str) -> bool:
        """Disconnect user's Google Calendar (remove tokens)."""
        if self.tokens_collection is None:
            return False
        await self.tokens_collection.delete_one({"user_id": user_id})
        return True

    # ------------------------------------------------------------------
    # Calendar CRUD Operations
    # ------------------------------------------------------------------

    async def _make_request(
        self, user_id: str, method: str, endpoint: str, body: Dict = None
    ) -> Optional[Dict]:
        """Make an authenticated request to the Google Calendar API."""
        import httpx

        access_token = await self._get_access_token(user_id)
        if not access_token:
            print(f"[CALENDAR] No access token for user {user_id}")
            return None

        base_url = "https://www.googleapis.com/calendar/v3"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                if method == "GET":
                    response = await client.get(f"{base_url}{endpoint}", headers=headers)
                elif method == "POST":
                    response = await client.post(
                        f"{base_url}{endpoint}", headers=headers, json=body
                    )
                elif method == "PUT":
                    response = await client.put(
                        f"{base_url}{endpoint}", headers=headers, json=body
                    )
                elif method == "PATCH":
                    # Partial update — only supplied fields are changed
                    response = await client.patch(
                        f"{base_url}{endpoint}", headers=headers, json=body
                    )
                elif method == "DELETE":
                    response = await client.delete(f"{base_url}{endpoint}", headers=headers)
                    return {"deleted": response.status_code == 204}
                else:
                    return None

                if response.status_code in (200, 201):
                    return response.json()
                else:
                    print(f"[CALENDAR] API error {response.status_code}: {response.text}")
                    return None
        except Exception as e:
            print(f"[CALENDAR] Request error: {e}")
            return None

    async def list_events(
        self,
        user_id: str,
        time_min: datetime = None,
        time_max: datetime = None,
        max_results: int = 20,
    ) -> List[Dict]:
        """List upcoming calendar events."""
        if time_min is None:
            time_min = datetime.utcnow()
        if time_max is None:
            time_max = time_min + timedelta(days=7)

        params = (
            f"?timeMin={time_min.isoformat()}Z"
            f"&timeMax={time_max.isoformat()}Z"
            f"&maxResults={max_results}"
            f"&singleEvents=true"
            f"&orderBy=startTime"
        )

        result = await self._make_request(user_id, "GET", f"/calendars/primary/events{params}")
        if result is None:
            return []

        events = result.get("items", [])
        return [self._format_event(e) for e in events]

    async def create_event(
        self,
        user_id: str,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        timezone: str = "Asia/Kolkata",
    ) -> Optional[Dict]:
        """Create a new calendar event."""
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_time, "timeZone": timezone},
            "end": {"dateTime": end_time, "timeZone": timezone},
        }

        result = await self._make_request(user_id, "POST", "/calendars/primary/events", body)
        if result:
            return self._format_event(result)
        return None

    async def update_event(
        self, user_id: str, event_id: str, updates: Dict
    ) -> Optional[Dict]:
        """Partially update an existing calendar event using PATCH.
        
        Only the fields present in `updates` are changed.
        Existing fields not mentioned are preserved (unlike PUT which wipes them).
        """
        body = {}
        if "title" in updates:
            body["summary"] = updates["title"]
        if "description" in updates:
            body["description"] = updates["description"]
        if "start_time" in updates:
            body["start"] = {
                "dateTime": updates["start_time"],
                "timeZone": "Asia/Kolkata",  # always IST
            }
        if "end_time" in updates:
            body["end"] = {
                "dateTime": updates["end_time"],
                "timeZone": "Asia/Kolkata",  # always IST
            }

        if not body:
            return None  # Nothing to update

        # PATCH = partial update, preserves all untouched fields
        result = await self._make_request(
            user_id, "PATCH", f"/calendars/primary/events/{event_id}", body
        )
        if result:
            return self._format_event(result)
        return None

    async def delete_event(self, user_id: str, event_id: str) -> bool:
        """Delete a calendar event."""
        result = await self._make_request(
            user_id, "DELETE", f"/calendars/primary/events/{event_id}"
        )
        return result is not None and result.get("deleted", False)

    async def check_conflicts(
        self, user_id: str, start_time: str, end_time: str
    ) -> List[Dict]:
        """Check for conflicting events in the given time range."""
        from dateutil.parser import parse

        start = parse(start_time)
        end = parse(end_time)

        events = await self.list_events(
            user_id, time_min=start, time_max=end, max_results=10
        )
        return events

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_event(event: Dict) -> Dict:
        """Format a Google Calendar event into our standard format."""
        start = event.get("start", {})
        end = event.get("end", {})

        return {
            "id": event.get("id", ""),
            "title": event.get("summary", "Untitled"),
            "description": event.get("description", ""),
            "start_time": start.get("dateTime", start.get("date", "")),
            "end_time": end.get("dateTime", end.get("date", "")),
            "timezone": start.get("timeZone", "Asia/Kolkata"),
            "location": event.get("location", ""),
            "status": event.get("status", "confirmed"),
            "html_link": event.get("htmlLink", ""),
            "created": event.get("created", ""),
            "updated": event.get("updated", ""),
        }
