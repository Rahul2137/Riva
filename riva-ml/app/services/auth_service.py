import os
import json
from datetime import datetime
from typing import Optional, Dict
from firebase_admin import credentials, auth, initialize_app
from services.db import users_collection
from dotenv import load_dotenv

load_dotenv()

# Initialize Firebase Admin SDK (supports both local file and env variable)
try:
    # Check for environment variable first (for cloud deployment like Railway)
    # Using FIREBASE_CONFIG as the variable name
    firebase_creds_json = os.getenv("FIREBASE_CONFIG") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    
    if firebase_creds_json:
        # Parse JSON from environment variable
        try:
            cred_dict = json.loads(firebase_creds_json)
            # Handle potential \n issues in private_key
            if "private_key" in cred_dict:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            print("[OK] Firebase initialized from environment variable")
        except Exception as json_err:
            print(f"[ERROR] Failed to parse FIREBASE_CONFIG JSON: {json_err}")
            # Fall back to local file if JSON parsing fails
            cred = credentials.Certificate("firebase_key.json")
            print("[OK] Falling back to local firebase_key.json")
    else:
        # Fall back to local file (for local development)
        cred = credentials.Certificate("firebase_key.json")
        print("[OK] Firebase initialized from local file")
    
    initialize_app(cred)
    print("[OK] Firebase Admin SDK ready")
except Exception as e:
    print(f"[WARNING] Firebase Admin init warning: {e}")


async def verify_firebase_token(id_token: str) -> Optional[Dict]:
    """
    Verify Firebase ID token and return decoded user info.
    """
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        print(f"[ERROR] Token verification failed: {e}")
        return None


async def create_or_update_user(user_data: Dict) -> Dict:
    """
    Create or update user in MongoDB after successful authentication.
    """
    try:
        user_id = user_data.get("uid")
        email = user_data.get("email")
        name = user_data.get("name", "")
        picture = user_data.get("picture", "")
        
        # Check if user exists
        existing_user = await users_collection.find_one({"user_id": user_id})
        
        user_doc = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "last_login": datetime.utcnow().isoformat(),
        }
        
        if existing_user:
            # Update existing user
            await users_collection.update_one(
                {"user_id": user_id},
                {"$set": user_doc}
            )
            print(f"[OK] User updated: {email}")
        else:
            # Create new user
            user_doc["created_at"] = datetime.utcnow().isoformat()
            user_doc["timezone"] = "UTC"  # Default timezone
            await users_collection.insert_one(user_doc)
            print(f"[OK] New user created: {email}")
        
        return {
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "is_new_user": existing_user is None
        }
    except Exception as e:
        print(f"[ERROR] Error creating/updating user: {e}")
        raise Exception(f"Database error: {str(e)}")


async def get_user_by_id(user_id: str) -> Optional[Dict]:
    """
    Retrieve user data from MongoDB by user_id.
    """
    try:
        user = await users_collection.find_one({"user_id": user_id})
        if user:
            user["_id"] = str(user["_id"])  # Convert ObjectId to string
            return user
        return None
    except Exception as e:
        print(f"[ERROR] Error fetching user: {e}")
        return None

