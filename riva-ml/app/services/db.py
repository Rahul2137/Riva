from motor.motor_asyncio import AsyncIOMotorClient
from .UserModel import UserContextCache
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize MongoDB Client
client = AsyncIOMotorClient(os.getenv("MONGO_URI"))  # Use a single env var
db = client["riva"]

# ----------------------------
# Get User Context
# ----------------------------
async def get_user_context(user_id: str) -> UserContextCache:
    doc = await db["UserContextCache"].find_one({"user_id": user_id})
    if not doc:
        raise ValueError(f"No context found for user_id {user_id}")
    return UserContextCache(**doc)

# ----------------------------
# Get Required User Data
# ----------------------------
async def get_user_data_by_fields(user_id: str, fields: dict) -> dict:
    user_data = {}

    for collection_name, keys in fields.items():
        projection = {key: 1 for key in keys}
        projection["user_id"] = 1

        doc = await db[collection_name].find_one({"user_id": user_id}, projection)
        if doc:
            user_data[collection_name] = doc

    return user_data

# Expose the 'users' collection
users_collection = db["users"]
