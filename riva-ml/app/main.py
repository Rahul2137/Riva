import os
import wave
import tempfile
import traceback
import time
import numpy as np
import httpx
from fastapi import FastAPI, Request, HTTPException, WebSocket, Response
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
from dotenv import load_dotenv
import speech_recognition as sr
from pydantic import BaseModel

# Local imports
from services.db import users_collection
from services.auth_service import verify_firebase_token, create_or_update_user, get_user_by_id
from services.assistant import classify_user_request
from services.finance_manager import FinanceManager
from services.task_manager import TaskManager
from services.conversational_manager import ConversationManager
from openai import OpenAI
import asyncio

load_dotenv()

app = FastAPI()

# Middleware Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for mobile app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
GOOGLE_CLIENT_ID = os.getenv("client_id")
GOOGLE_CLIENT_SECRET = os.getenv("client_secret")
REDIRECT_URI = "http://localhost:8000/auth/callback"

# Audio Config
SAMPLERATE = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2
SILENCE_THRESHOLD = 100
SILENCE_DURATION_MS = 1500
CHUNK_MS = 200

# OpenAI Client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

## --- Pydantic Models ---

class LoginRequest(BaseModel):
    idToken: str

class LoginResponse(BaseModel):
    success: bool
    message: str
    token: str
    user: dict
    is_new_user: bool

## --- Authentication Logic ---

@app.post("/auth/login", status_code=200)
async def firebase_login(request: LoginRequest, response: Response):
    """
    Verify Firebase ID token and create/update user in database.
    This endpoint is called by the Flutter app after Google Sign-In.
    Returns 201 for new users, 200 for existing users.
    """
    try:
        # Verify the Firebase ID token
        decoded_token = await verify_firebase_token(request.idToken)
        
        if not decoded_token:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        
        # Extract user info from the decoded token
        user_info = {
            "uid": decoded_token.get("uid"),
            "email": decoded_token.get("email"),
            "name": decoded_token.get("name", ""),
            "picture": decoded_token.get("picture", ""),
        }
        
        # Create or update user in database
        user_data = await create_or_update_user(user_info)
        is_new_user = user_data.pop("is_new_user", False)
        
        # Set status code: 201 for new user, 200 for existing
        response.status_code = 201 if is_new_user else 200
        
        return LoginResponse(
            success=True,
            message="New user created" if is_new_user else "Login successful",
            token=request.idToken,  # Return the Firebase token for frontend storage
            user=user_data,
            is_new_user=is_new_user
        )
    
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[ERROR] Login error: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.get("/user/profile")
async def get_user_profile(request: Request):
    """
    Get user profile data. Requires Authorization header with Firebase ID token.
    """
    try:
        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
        
        token = auth_header.split("Bearer ")[1]
        
        # Verify token
        decoded_token = await verify_firebase_token(token)
        if not decoded_token:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = decoded_token.get("uid")
        
        # Get user from database
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

@app.get("/auth/login-web")
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

@app.get("/home")
async def home():

    return {"message": "Welcome Home! You are logged in."}

@app.get("/auth/callback")
async def auth_callback(request: Request):
    """Handles the redirect from Google, exchanges code for user data."""
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing auth code")

    async with httpx.AsyncClient() as client:
        # 1. Exchange Code for Token
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

        # 2. Decode Payload (Skip signature check for internal prototyping)
        payload = jwt.get_unverified_claims(id_token)
        email = payload.get("email")
        name = payload.get("name")

    # 3. Update Database
    await users_collection.update_one(
        {"email": email},
        {"$set": {"email": email, "name": name, "last_token": id_token}},
        upsert=True
    )

    return RedirectResponse(url="http://192.168.1.14/home")

## --- Speech Processing Logic ---

def process_audio_chunk(data_buffer: bytearray) -> str:
    """Writes bytes to a temp WAV and transcribes."""
    recognizer = sr.Recognizer()
    tmp_file_path = None
    
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_file_path = tmp.name
            
            # Write WAV file
            with wave.open(tmp_file_path, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(BYTES_PER_SAMPLE)
                wf.setframerate(SAMPLERATE)
                wf.writeframes(data_buffer)
        
        # All file handles are now closed, safe to read
        try:
            with sr.AudioFile(tmp_file_path) as source:
                audio = recognizer.record(source)
                result = recognizer.recognize_google(audio)
                return result
        except Exception as e:
            print(f"[WARNING] Speech recognition error: {e}")
            return ""
    
    finally:
        # Clean up temp file with retry logic for Windows
        if tmp_file_path and os.path.exists(tmp_file_path):
            _safe_remove_file(tmp_file_path)


def _safe_remove_file(file_path: str, max_retries: int = 3, delay: float = 0.1):
    """Safely remove a file with retry logic for Windows file locking issues."""
    for attempt in range(max_retries):
        try:
            os.remove(file_path)
            return  # Success
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))  # Exponential backoff
            else:
                # Last attempt failed, log but don't crash
                print(f"[WARNING] Could not delete temp file after {max_retries} attempts: {file_path}")
        except Exception as e:
            # Other errors (file doesn't exist, etc.) - just log and continue
            print(f"[WARNING] Error removing temp file: {e}")
            return

async def process_user_request(user_input: str) -> str:
    """
    Process user input through the assistant service and return the response.
    This is an async wrapper around the synchronous assistant functions.
    """
    if not openai_client:
        return "OpenAI API key not configured. Please set OPENAI_API_KEY in your environment."
    
    try:
        # Run the synchronous classification in a thread pool
        loop = asyncio.get_event_loop()
        response_data = await loop.run_in_executor(
            None, 
            classify_user_request, 
            user_input
        )
        
        responses = []
        
        # Process each request type
        for req in response_data.requests:
            print(f"[ASSISTANT] Detected service: {req.DesiredService}, description: {req.desc}")
            
            if req.DesiredService == "fin-manager":
                finance_manager = FinanceManager()
                # Run in executor since it's synchronous
                response = await loop.run_in_executor(
                    None,
                    finance_manager.process_request,
                    openai_client,
                    req.desc,
                    user_input
                )
                responses.append(response)
                print(f"[ASSISTANT] Finance response: {response}")
                
            elif req.DesiredService == "task":
                task_manager = TaskManager()
                response = await loop.run_in_executor(
                    None,
                    task_manager.process_request,
                    openai_client,
                    user_input
                )
                responses.append(response)
                print(f"[ASSISTANT] Task response: {response}")
                
            elif req.DesiredService == "talk":
                conversation_manager = ConversationManager()
                response_obj = await loop.run_in_executor(
                    None,
                    conversation_manager.process_conversation,
                    openai_client,
                    user_input
                )
                response = response_obj.responseToUser if hasattr(response_obj, 'responseToUser') else str(response_obj)
                responses.append(response)
                print(f"[ASSISTANT] Conversation response: {response}")
                
            elif req.DesiredService == "goodbye":
                goodbye_msg = req.desc
                responses.append(goodbye_msg)
                print(f"[ASSISTANT] Goodbye: {goodbye_msg}")
        
        # Combine all responses into a single string
        final_response = " ".join(responses) if responses else "I'm sorry, I didn't understand that. Could you please repeat?"
        return final_response
        
    except Exception as e:
        error_msg = f"Error processing request: {str(e)}"
        print(f"[ASSISTANT ERROR] {error_msg}")
        traceback.print_exc()
        return "I'm sorry, I encountered an error processing your request. Please try again."

@app.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    chunk_size = int(SAMPLERATE * BYTES_PER_SAMPLE * CHANNELS * CHUNK_MS / 1000)
    audio_buffer = bytearray()
    speech_buffer = bytearray()
    silence_ms = 0

    print("WebSocket: Streaming started")

    try:
        while True:
            data = await websocket.receive_bytes()
            audio_buffer.extend(data)

            # Process buffer in defined chunk sizes
            while len(audio_buffer) >= chunk_size:
                chunk = audio_buffer[:chunk_size]
                audio_buffer = audio_buffer[chunk_size:]

                # Voice Activity Detection (RMS Calculation)
                audio_np = np.frombuffer(chunk, dtype=np.int16)
                rms = np.sqrt(np.mean(audio_np.astype(np.float32) ** 2))

                if rms > SILENCE_THRESHOLD:
                    silence_ms = 0
                    speech_buffer.extend(chunk)
                else:
                    silence_ms += CHUNK_MS
                    
                    # If user is silent after speaking, transcribe
                    if silence_ms >= SILENCE_DURATION_MS and len(speech_buffer) > 0:
                        text = process_audio_chunk(speech_buffer)
                        if text:
                            print(f"[TRANSCRIPT] User said: {text}")
                            
                            # Process through assistant and get response
                            try:
                                response = await process_user_request(text)
                                # Send only the assistant response to frontend (frontend will handle TTS)
                                await websocket.send_json({
                                    "response": response,
                                    "type": "assistant_response"
                                })
                                print(f"[ASSISTANT] Response sent to frontend: {response}")
                            except Exception as e:
                                error_msg = f"Error processing request: {str(e)}"
                                print(f"[ERROR] {error_msg}")
                                await websocket.send_json({
                                    "response": "I'm sorry, I encountered an error. Please try again.",
                                    "type": "assistant_response",
                                    "error": error_msg
                                })
                        
                        speech_buffer = bytearray()
                        silence_ms = 0

    except Exception as e:
        print(f"WebSocket Error: {e}")
    finally:
        # Final cleanup on disconnect
        if len(speech_buffer) > 0:
            final_text = process_audio_chunk(speech_buffer)
            if final_text:
                print(f"[TRANSCRIPT] Final transcription: {final_text}")
                # Process final text through assistant
                try:
                    response = await process_user_request(final_text)
                    await websocket.send_json({
                        "response": response,
                        "type": "assistant_response"
                    })
                    print(f"[ASSISTANT] Final response: {response}")
                except Exception as e:
                    print(f"[ERROR] Error processing final request: {e}")

## --- Server Startup ---

if __name__ == "__main__":
    import uvicorn
    print("[INFO] Starting RIVA Backend Server...")
    print(f"[INFO] Server will be available at: http://0.0.0.0:8000")
    print(f"[INFO] API documentation: http://0.0.0.0:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)