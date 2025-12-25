import pyttsx3
import speech_recognition as sr
import openpyxl
import os
import json
from openai import OpenAI
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

# Load API key
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# File for storing transactions
EXCEL_FILE = "expenses.xlsx"

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

# Ensure Excel file exists
if not os.path.exists(EXCEL_FILE):
    df = pd.DataFrame(columns=["Date", "Transaction Type", "Amount", "Category", "Notes"])
    df.to_excel(EXCEL_FILE, index=False)

# Define structured response model
class FinanceActionResponse(BaseModel):
    action: str  # 'query', 'add', or 'error'
    message: str  # Human-readable response
    responseToUser: str
    transaction_type: Optional[str]  # 'income' or 'expense'
    amount: Optional[float]
    category: Optional[str]
    date: Optional[str]
    notes: Optional[str]

class FinanceManager:
    def __init__(self):
        self.excel_file = EXCEL_FILE

    def process_request(self, client, description: str, user_input: str):
        """Calls OpenAI API to determine action and process request accordingly."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an AI financial assistant. Analyze user input and determine the appropriate action. "
                    "If the user provides a transaction, return 'action': 'add' with necessary transaction details. "
                    "If the user wants spending analysis, return 'action': 'query'. "
                    "If the input is unclear, return 'action': 'error'."
                    "In the responseToUser return a liner to be spoken to the user."
                )
            },
            {"role": "user", "content": f"Description: {description}. User said: {user_input}."}
        ]

        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.5,
            max_tokens=100,
            response_format=FinanceActionResponse
        )

        responseBody = response.choices[0].message.parsed
        if responseBody.action == "add":
            self.add_transaction(responseBody)
            message = responseBody.responseToUser
        elif responseBody.action == "query":
            self.query_transactions(user_input)
            message = responseBody.responseToUser
        else:
            message = "I couldn't process your request."
        
        return message

    def add_transaction(self, transaction: FinanceActionResponse):
        """Saves transaction to Excel file."""
        df = pd.read_excel(self.excel_file)
        new_entry = pd.DataFrame([{
            "Date": transaction.date or datetime.now().strftime("%Y-%m-%d"),
            "Transaction Type": transaction.transaction_type,
            "Amount": transaction.amount,
            "Category": transaction.category,
            "Notes": transaction.notes or ""
        }])
        df = pd.concat([df, new_entry], ignore_index=True)
        df.to_excel(self.excel_file, index=False)
        return "Transaction added successfully!"

    def query_transactions(self, query: str) -> str:
        """Analyzes spending based on user queries."""
        df = pd.read_excel(self.excel_file)
        if df.empty:
            return "No transactions recorded yet."

        query_lower = query.lower()
        
        if "total spent" in query_lower or "how much did i spend" in query_lower:
            total_spent = df[df["Transaction Type"] == "expense"]["Amount"].sum()
            return f"You have spent a total of ₹{total_spent}."

        elif "highest expense" in query_lower:
            max_expense = df[df["Transaction Type"] == "expense"].max()
            return f"Your highest expense was ₹{max_expense['Amount']} on {max_expense['Date']} for {max_expense['Category']}."

        elif "category wise" in query_lower:
            category_spend = df[df["Transaction Type"] == "expense"].groupby("Category")["Amount"].sum()
            return category_spend.to_string()

        return "I couldn't find relevant data for your query."

if __name__ == "__main__":
    finance_manager = FinanceManager()
    speak("Hello! How can I assist with your finances today?")
    
    while True:
        user_input = listen()
        if user_input.lower() in ["exit", "quit", "bye"]:
            speak("Goodbye!")
            break
        elif user_input == "Sorry, I didn't catch that.":
            speak("Can you repeat?")
            continue

        print(f"You: {user_input}")
        response = finance_manager.process_request(client, "Financial inquiry", user_input)

        # if response.action == "add":
        #     message = finance_manager.add_transaction(response)
        # elif response.action == "query":
        #     message = finance_manager.query_transactions(user_input)
        # else:
        #     message = "I couldn't process your request."

        print(f"Response: {response}")
        # speak(message)
