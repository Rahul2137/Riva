"""
Assistant module - Request classification and routing.
TTS/STT is handled by frontend - this module only does request classification.
"""
from openai import OpenAI
import os
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List
from .finance_manager import FinanceManager
from .task_manager import TaskManager
from .conversational_manager import ConversationManager

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


# NOTE: This module is kept for backward compatibility.
# New code should use agents/ package instead.