"""
Authentication Router
Handles Firebase auth, user profile, and OAuth flows.
"""
from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import os
import httpx
from jose import jwt

from services.db import users_collection
from services.auth_service import verify_firebase_token, create_or_update_user, get_user_by_id

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Constants
GOOGLE_CLIENT_ID = os.getenv("client_id")
GOOGLE_CLIENT_SECRET = os.getenv("client_secret")
REDIRECT_URI = "http://localhost:8000/auth/callback"


# --- Pydantic Models ---

class LoginRequest(BaseModel):
    idToken: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    token: str
    user: dict
    is_new_user: bool


# --- Routes ---

@router.post("/login", status_code=200)
async def firebase_login(request: LoginRequest, response: Response):
    """
    Verify Firebase ID token and create/update user in database.
    This endpoint is called by the Flutter app after Google Sign-In.
    Returns 201 for new users, 200 for existing users.
    """
    try:
        decoded_token = await verify_firebase_token(request.idToken)
        
        if not decoded_token:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        
        user_info = {
            "uid": decoded_token.get("uid"),
            "email": decoded_token.get("email"),
            "name": decoded_token.get("name", ""),
            "picture": decoded_token.get("picture", ""),
        }
        
        user_data = await create_or_update_user(user_info)
        is_new_user = user_data.pop("is_new_user", False)
        
        response.status_code = 201 if is_new_user else 200
        
        return LoginResponse(
            success=True,
            message="New user created" if is_new_user else "Login successful",
            token=request.idToken,
            user=user_data,
            is_new_user=is_new_user
        )
    
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[ERROR] Login error: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@router.get("/login-web")
async def google_login():
    """Builds the Google OAuth URL and redirects."""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": "openid email profile",
        "access_type": "offline",
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{httpx.QueryParams(params)}"
    return RedirectResponse(url=url)


@router.get("/callback")
async def auth_callback(request: Request):
    """Handles the redirect from Google, exchanges code for user data."""
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing auth code")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            }
        )
        token_data = token_resp.json()
        id_token = token_data.get("id_token")

        if not id_token:
            raise HTTPException(status_code=400, detail="Failed to retrieve ID token")

        payload = jwt.get_unverified_claims(id_token)
        email = payload.get("email")
        name = payload.get("name")

    await users_collection.update_one(
        {"email": email},
        {"$set": {"email": email, "name": name, "last_token": id_token}},
        upsert=True
    )

    return RedirectResponse(url="http://192.168.1.16/home")


# --- User Profile Router (separate prefix) ---

user_router = APIRouter(prefix="/user", tags=["User"])


@user_router.get("/profile")
async def get_user_profile(request: Request):
    """Get user profile data. Requires Authorization header with Firebase ID token."""
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
        
        token = auth_header.split("Bearer ")[1]
        
        decoded_token = await verify_firebase_token(token)
        if not decoded_token:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = decoded_token.get("uid")
        
        user = await get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "success": True,
            "user": user
        }
    
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[ERROR] Get profile error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get profile: {str(e)}")
