from pydantic import BaseModel
from typing import List, Dict
from openai import OpenAI
import os
from models.user.user_model import UserContextCache

# -----------------------------
# Pydantic response schema
# -----------------------------
class FieldSelection(BaseModel):
    required_fields: Dict[str, List[str]]  # e.g. { "WorkProfile": ["productivity_rating"] }

# -----------------------------
# System Prompt
# -----------------------------
RELEVANCE_SYSTEM_PROMPT = """
You are a personalization assistant for a virtual AI assistant. You are given a user's request and their current context. 
Your job is to decide what user data fields are needed to fulfill the request, or can matter in making a decision. Here are the user data categories and their fields:
1. WorkProfile: occupation, education_level, work_hours_per_day, work_days_per_week, productivity_rating, current_goals, priorities, tools_used, task_completion_rate  
2. LifestyleProfile: sleep_pattern, avg_sleep_hours, wake_time, bed_time, height_cm, weight_kg, number_of_friends, hobbies, fitness_routine, diet_type  
3. PersonalityProfile: mbti_type, strengths, weaknesses, motivation_level, stress_level, emotion_baseline, values, social_energy, decision_style  
4. User: name, email, phone, timezone  
5. UserContextCache: current_focus, inferred_mood, recent_activity, session_timestamp
Respond with a JSON in this format:
{
  "required_fields": {
    "WorkProfile": ["productivity_rating", "current_goals"],
    "PersonalityProfile": ["motivation_level"]
  }
}
Only include categories that are relevant to the request.
"""

# -----------------------------
# GPT API call function
# -----------------------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_relevant_fields(user_input: str, context: UserContextCache) -> FieldSelection:
    messages = [
        {"role": "system", "content": RELEVANCE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"User said: '{user_input}'.\nContext: {context.model_dump_json()}",
        },
    ]

    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=messages,
        temperature=0.2,
        max_tokens=300,
        response_format=FieldSelection
    )

    return response.choices[0].message.parsed
