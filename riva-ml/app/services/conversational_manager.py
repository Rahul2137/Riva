import pyttsx3
import speech_recognition as sr
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
        self.engine = pyttsx3.init()
        self.recognizer = sr.Recognizer()

    def speak(self, text):
        """Converts text to speech."""
        self.engine.say(text)
        self.engine.runAndWait()

    def listen(self):
        """Captures user's voice input and converts it to text."""
        with sr.Microphone() as source:
            print("Listening...")
            try:
                audio = self.recognizer.listen(source)
                return self.recognizer.recognize_google(audio)
            except sr.UnknownValueError:
                return "Sorry, I didn't catch that."
            except sr.RequestError:
                return "Service unavailable."

    def process_conversation(self,client,  user_input):
        """Calls OpenAI API to respond to user input with appropriate tone and advice."""
        messages = [
            {"role": "system", "content": "You are an AI that provides support, advice, or general conversation. Adjust your tone based on user sentiment. Keep your answers short, not more tha 2-3 lines"},
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

if __name__ == "__main__":
    conv_manager = ConversationManager()
    conv_manager.speak("Hello! How are you feeling today?")
    
    while True:
        user_input = conv_manager.listen()
        if user_input.lower() in ["exit", "quit", "bye"]:
            conv_manager.speak("Take care! Goodbye!")
            break
        elif user_input == "Sorry, I didn't catch that.":
            conv_manager.speak("Can you repeat that?")
            continue
        
        print(f"You: {user_input}")
        
        response = conv_manager.process_conversation(client, user_input)
        print(f"AI ({response.emotionalTone}): {response.responseToUser}")
        conv_manager.speak(response.responseToUser)
