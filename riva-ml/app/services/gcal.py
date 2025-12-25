import pickle
import os
from datetime import datetime, timedelta
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Define OAuth scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# File to store user credentials
TOKEN_FILE = "token.pickle"

def authenticate_user():
    """Authenticate the user via OAuth and store credentials."""
    creds = None

    # Load credentials if available
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)

    # If no valid credentials, authenticate user
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
        creds = flow.run_local_server(port=8080)

        # Save the credentials for future use
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)

    return creds

def get_calendar_service():
    """Get Google Calendar API service using OAuth credentials."""
    creds = authenticate_user()
    return build("calendar", "v3", credentials=creds)

def create_event(summary, description, start_time, end_time):
    """Create a new event in the user's Google Calendar."""
    service = get_calendar_service()
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_time, "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": end_time, "timeZone": "Asia/Kolkata"},
    }
    event = service.events().insert(calendarId="primary", body=event).execute()
    print(f"✅ Event '{summary}' created successfully!")
    return event

def get_upcoming_events():
    """Fetch the user's upcoming events."""
    service = get_calendar_service()
    now = datetime.utcnow().isoformat() + "Z"  # Current time in UTC
    events_result = service.events().list(
        calendarId="primary", timeMin=now, maxResults=10, singleEvents=True, orderBy="startTime"
    ).execute()
    events = events_result.get("items", [])
    
    if not events:
        return "No upcoming events found."
    
    return [{"summary": event["summary"], "start": event["start"]["dateTime"]} for event in events]

if __name__ == "__main__":
    print("🔹 Welcome! Please log in to Google.")
    service = get_calendar_service()  # This will open the browser for authentication

    # Create an event example
    start_time = (datetime.now() + timedelta(hours=1)).isoformat()
    end_time = (datetime.now() + timedelta(hours=2)).isoformat()
    create_event("Meeting with RIVA", "Discuss AI project", start_time, end_time)

    # Fetch upcoming events
    print(get_upcoming_events())
