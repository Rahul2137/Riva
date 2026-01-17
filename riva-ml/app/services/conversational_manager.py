"""
Conversation Manager - Handles general conversation with AI.
TTS/STT is handled by frontend - this module only does conversation processing.
"""
from openai import OpenAI
import os
from dotenv import load_dotenv
from pydantic import BaseModel

# Load API key
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

class ConversationResponse(BaseModel):
    responseToUser: str
    emotionalTone: str  # Example values: "supportive", "motivational", "informative"

class ConversationManager:
    def __init__(self):
        pass  # No TTS/STT init - handled by frontend

    def process_conversation(self, client, user_input):
        """Calls OpenAI API to respond to user input with appropriate tone and advice."""
        messages = [
            {"role": "system", "content": "You are an AI that provides support, advice, or general conversation. Adjust your tone based on user sentiment. Keep your answers short, not more than 2-3 lines"},
            {"role": "user", "content": user_input}
        ]
        
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=500,
            response_format=ConversationResponse
        )
        
        response_msg = response.choices[0].message
        if response_msg.refusal is None:
            return response_msg.parsed
        else:
            return ConversationResponse(responseToUser="I'm here to listen whenever you need.", emotionalTone="neutral")
