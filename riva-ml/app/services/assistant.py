import pyttsx3
import speech_recognition as sr
from openai import OpenAI
import os
import json
import asyncio
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List
from .finance_manager import FinanceManager
from .task_manager import TaskManager
from .conversational_manager import ConversationManager
from .db import get_user_context, get_user_data_by_fields  # you'll implement these
from .gptDataRequest import get_relevant_fields

# Load API Key
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Define Pydantic Model for Response
class BaseRequest(BaseModel):
    DesiredService: str  # Either 'task', 'fin-manager', or 'talk'
    desc: str            # Refined user request description

class UserRequest(BaseModel):
    requests: List[BaseRequest]

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

def classify_user_request(user_input):
    """Calls ChatGPT to classify the user's request using the structured response model."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are an AI assistant that categorizes user requests into three types: "
                "1. 'task' for scheduling tasks, "
                "2. 'fin-manager' for expense tracking, "
                "3. 'talk' for general conversations or advice. "
                "4. 'goodbye' for ending the conversation."
                "Return JSON in the defined format. Can return an array if multiple requests are detected."
            ),
        },
        {"role": "user", "content": f"User said: '{user_input}'. Classify the request."},
    ]

    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.3,
        max_tokens=100,
        response_format=UserRequest,  # Structured response
    )

    return response.choices[0].message.parsed  # Parsed response in Pydantic format

if __name__ == "__main__":
    speak("Hello! How can I help you today?")
    flag = True
    goodbyeMsg = "Goodbye! Have a great day!"
    while flag:
        user_input = listen()
        if user_input.lower() in ["exit", "quit", "bye"]:
            break
        elif user_input == "Sorry, I didn't catch that.":
            speak("Sorry, I didn't catch that. Can you repeat?")
            continue

        print(f"You: {user_input}")
        # 1. Load current user context from DB (simulate with dummy if needed)
        user_id = "123"  # Normally pulled from session or auth
        # user_context = asyncio.run(get_user_context(user_id))  # returns UserContextCache Pydantic model
        # print("Field Selection: {}, data: ", user_context)

        # # 2. Use GPT to decide which fields are needed
        # field_selection = get_relevant_fields(user_input, user_context)

        # # 3. Fetch only needed data from Mongo
        # user_data = get_user_data_by_fields(user_id, field_selection.required_fields)

        # print("User Data: {}", user_data)
        # Now pass this enriched user_data to your respective manager below...
        response_data = classify_user_request(user_input)

        # Handle single or multiple responses
        # Process and speak out each request
        for req in response_data.requests:
            if(req.DesiredService == "fin-manager"):
                finance_manager = FinanceManager()
                response = finance_manager.process_request(client, req.desc, user_input)
                print(f"{response}")
                speak(response)
            elif(req.DesiredService == "task"):
                task_manager = TaskManager()
                response = task_manager.process_request(client, user_input)
                print(f"Task: {response}")
                speak(f"{response}")
            elif(req.DesiredService == "talk"):
                conversation_manager = ConversationManager()
                response = conversation_manager.process_conversation(client, user_input)
                print(f"Conversation: {response.responseToUser}")
                speak(f"{response.responseToUser}")
            elif(req.DesiredService == "goodbye"):
                goodbyeMsg = req.desc
                flag = False
            print(f"I detected that user need help with {req.DesiredService}. {req.desc}")

    speak(goodbyeMsg)