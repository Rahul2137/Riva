import pickle
import os
from datetime import datetime, timedelta
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pyttsx3
import speech_recognition as sr
from openai import OpenAI
import json
import pytz
from pydantic import BaseModel
from dotenv import load_dotenv

# Define OAuth scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = "token.pickle"
ist = pytz.timezone('Asia/Kolkata')

# Load API Key
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

class gCalTime(BaseModel):
    dateTime: str
    timeZone: str

class gCalAPIBody(BaseModel):
    summary: str
    description: str
    start: gCalTime
    end: gCalTime
    
class AssistantResponse(BaseModel):
    updatedSchedule: str
    updatedContext: str
    responseToUser: str
    instructionToAssistant: str
    addOrQuery: str
    reqBody: gCalAPIBody  

def authenticate_user():
    """
    Try local-server OAuth first. If binding to a local port fails (PermissionError,
    OSError) fall back to a dynamic port or to console-based auth.
    """
    flow = InstalledAppFlow.from_client_secrets_file("C:/Users/rkrau/OneDrive/Desktop/Riva_final/riva-ml/riva-ml/app/services/client_secret.json", SCOPES, redirect_uri="http://localhost:8000/")
    creds = None

    # 1) Preferred: bind to localhost on a fixed port
    try:
        creds = flow.run_local_server(host="127.0.0.1", port=8080, open_browser=True)
        return creds
    except (PermissionError, OSError) as e:
        # 2) Try ephemeral port (port=0)
        try:
            creds = flow.run_local_server(host="127.0.0.1", port=8000, open_browser=True)
            return creds
        except Exception:
            pass

    # 3) Final fallback: console flow (prints URL for manual copy/paste)
    print("Could not open a local server for OAuth. Falling back to console-based auth.")
    creds = flow.run_console()
    return creds

def get_calendar_service():
    """Get Google Calendar API service using OAuth credentials."""
    creds = authenticate_user()
    return build("calendar", "v3", credentials=creds)

def create_event(summary, description, start_time, end_time):
    """Create a new event in the user's Google Calendar."""
    print(f"Creating event: {summary} from {start_time} to {end_time}")
    service = get_calendar_service()
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_time, "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": end_time, "timeZone": "Asia/Kolkata"},
    }
    event = service.events().insert(calendarId="primary", body=event).execute()
    print(f"✅ Event '{summary}' created successfully!")
    print(f"Event '{summary}' created successfully!")
    return event

def get_upcoming_events():
    """Fetch the user's upcoming events."""
    service = get_calendar_service()
    now = datetime.utcnow().isoformat() + "Z"
    events_result = service.events().list(
        calendarId="primary", timeMin=now, maxResults=10, singleEvents=True, orderBy="startTime"
    ).execute()
    events = events_result.get("items", [])
    if not events:
        return "No upcoming events found."
    return [{"summary": event["summary"], "start": event["start"]} for event in events]

class TaskManager:
    SCHEDULE_FILE = "schedule.json"
    CONTEXT_FILE = "context.json"

    def __init__(self):
        self.today_schedule, self.user_context = self.load_data()
    
    def load_data(self):
        """Loads today's schedule and user context from JSON files."""
        if os.path.exists(self.SCHEDULE_FILE):
            with open(self.SCHEDULE_FILE, "r") as file:
                today_schedule = json.load(file)
        else:
            today_schedule = [
                {"task": "Gym", "time": "19:00-21:00", "priority": "High"},
                {"task": "Office work", "time": "14:00-15:00", "priority": "High"}
            ]
        
        if os.path.exists(self.CONTEXT_FILE):
            with open(self.CONTEXT_FILE, "r") as file:
                user_context = json.load(file)
        else:
            user_context = {
                "preferences": "User prefers reading in the morning. Gets sleepy after lunch.",
                "important_tasks": "Needs to complete one guitar lesson. Office tasks are high priority."
            }
        
        return today_schedule, user_context

    def save_data(self):
        """Saves the updated schedule and user context to JSON files."""
        with open(self.SCHEDULE_FILE, "w") as file:
            json.dump(self.today_schedule, file, indent=4)
        with open(self.CONTEXT_FILE, "w") as file:
            json.dump(self.user_context, file, indent=4)

    def process_request(self, client, user_prompt):
        """Calls OpenAI API to update the user's schedule, context, and interact with the calendar."""
        messages = [ 
            {
                "role": "system",
                "content": "You are an AI assistant managing a user's schedule, context, and Google Calendar. Modify the schedule based on the user's request while keeping priorities. If the user preferences change, update the user context. Your output will serve as a body to Google calendar APIs, provide structured details including title, time, and description. If the user wants to query the calendar, retrieve relevant events. The instruction to Assistant should clarify whether to add an event or fetch events."
            },
            {
                "role": "user",
                "content": f"Current schedule: {self.today_schedule}. User context: {self.user_context}. The user said: '{user_prompt}'. The current time is {datetime.now(ist)}. Update the schedule, context, or interact with the calendar accordingly. Return JSON with 'updatedSchedule', 'updatedContext', 'responseToUser', 'instructionToAssistant'."
            }
        ]
        print(f"Messages sent to OpenAI: {messages}")
        response = client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, temperature=0.5, max_tokens=10000, response_format=AssistantResponse)
        response_msg = response.choices[0].message
        print(f"Response from OpenAI: {response_msg}")
        if response_msg.refusal is None:
            result = response_msg.parsed
            self.today_schedule = result.updatedSchedule
            self.user_context = result.updatedContext
            self.save_data()
            if result.addOrQuery == "add":
                print(f"Adding event to calendar: {result.reqBody.summary} at {result.reqBody.start.dateTime}")
                event = create_event(result.reqBody.summary, result.reqBody.description, result.reqBody.start.dateTime, result.reqBody.end.dateTime)
                print(f"Event '{event['summary']}' created successfully.")
            else:
                upcoming_events = get_upcoming_events()
                print(upcoming_events)
                response = ""
                for event in upcoming_events:
                    response += f"""You have a {result["summary"]} event at {result["start"]["dateTime"]}."""
                return response
            return result.responseToUser
        else:
            return "Error updating schedule."

def speak(text):
    """Converts text to speech."""
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()

def listen():
    """Listens to the user's voice input and converts it to text."""
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening...")
        try:
            audio = recognizer.listen(source)
            return recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return "Sorry, I didn't catch that."
        except sr.RequestError:
            return "Service unavailable."

if __name__ == "__main__":
    manager = TaskManager()
    speak("Hello! How can I assist you today?")
    
    while True:
        user_input = listen()
        if user_input.lower() in ["exit", "quit", "bye"]:
            speak("Goodbye!")
            break
        elif user_input == "Sorry, I didn't catch that.":
            speak("Sorry, I didn't catch that. Can you repeat?")
            continue
        
        print(f"You: {user_input}")
        response = manager.process_request(client, user_input)
        print(f"Response to user: {response}")
        speak(response)
