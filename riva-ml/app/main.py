"""
RIVA Backend - Main Application
Personal AI Secretary for productivity and finance.
"""
import os
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import routers
from routers import auth_router, user_router, stream_router, init_stt_provider, finance_router, calendar_router, gemini_live_router

# Lifespan manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[INFO] Starting RIVA Backend...")
    # Initialize STT provider
    init_stt_provider()
    print("[OK] RIVA Backend ready")
    yield
    print("[INFO] Shutting down RIVA Backend...")

# Create FastAPI app
app = FastAPI(
    title="RIVA API",
    description="Voice-first AI Personal Assistant API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Routes ---

# Include routers
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(stream_router)
app.include_router(finance_router)
app.include_router(calendar_router)
app.include_router(gemini_live_router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "RIVA API",
        "version": "1.0.0"
    }


@app.get("/home")
async def home():
    """Home endpoint."""
    return {"message": "Welcome Home! You are logged in."}


# --- Server Entry Point ---

if __name__ == "__main__":
    import uvicorn
    print("[INFO] Starting RIVA Backend Server...")
    print("[INFO] Server: http://0.0.0.0:8000")
    print("[INFO] API Docs: http://0.0.0.0:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)