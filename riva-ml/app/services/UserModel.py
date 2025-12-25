from pydantic import BaseModel, EmailStr
from typing import Optional, List

# -- Base User Identity --
class User(BaseModel):
    id: Optional[str] = None  # MongoDB _id
    name: str
    email: EmailStr
    phone: Optional[str]
    timezone: Optional[str]
    created_at: Optional[str]

# -- Lifestyle Profile --
class LifestyleProfile(BaseModel):
    user_id: str
    sleep_pattern: str  # "regular" or "irregular"
    avg_sleep_hours: float
    wake_time: Optional[str]
    bed_time: Optional[str]
    height_cm: Optional[float]
    weight_kg: Optional[float]
    number_of_friends: Optional[int]
    hobbies: List[str]
    fitness_routine: Optional[str]  # e.g. "gym", "yoga", "none"
    diet_type: Optional[str]        # e.g. "vegan", "balanced"

# -- Work & Productivity --
class WorkProfile(BaseModel):
    user_id: str
    occupation: str
    education_level: Optional[str]
    work_hours_per_day: Optional[float]
    work_days_per_week: Optional[int]
    productivity_rating: Optional[float]  # 0-10
    current_goals: List[str]
    priorities: List[str]                # e.g. ["career", "health"]
    tools_used: List[str]                # e.g. ["Notion", "Slack"]
    task_completion_rate: Optional[float]  # percentage

# -- Personality & Emotional Profile --
class PersonalityProfile(BaseModel):
    user_id: str
    mbti_type: Optional[str]             # e.g. "INTJ"
    strengths: List[str]
    weaknesses: List[str]
    motivation_level: Optional[float]    # 0-10
    stress_level: Optional[float]        # 0-10
    emotion_baseline: Optional[str]      # e.g. "calm", "anxious"
    values: List[str]                    # e.g. ["honesty", "growth"]
    social_energy: Optional[str]         # e.g. "introvert", "extrovert"
    decision_style: Optional[str]        # "logical", "intuitive"

# -- Optional Runtime Context --
class UserContextCache(BaseModel):
    user_id: str
    current_focus: Optional[str]
    inferred_mood: Optional[str]
    recent_activity: List[str]
    session_timestamp: Optional[str]
