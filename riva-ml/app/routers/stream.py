"""
Audio Streaming Router
Handles WebSocket for real-time voice processing.
"""
import os
import traceback
import numpy as np
from fastapi import APIRouter, WebSocket

from providers import create_stt_provider, STTProviderType
from services.assistant import classify_user_request
from services.finance_manager import FinanceManager
from services.task_manager import TaskManager
from services.conversational_manager import ConversationManager

router = APIRouter(tags=["Voice Stream"])

# Audio Config - Optimized for lower latency
SAMPLERATE = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2
SILENCE_THRESHOLD = 100
SILENCE_DURATION_MS = 800  # Reduced from 1500 for faster response
CHUNK_MS = 200

# STT Provider Config - Change this ONE value to switch providers
# Options: "google", "vosk", "openai"
STT_PROVIDER = os.getenv("STT_PROVIDER", "google")

# Global STT provider (initialized on startup)
stt_provider = None


def init_stt_provider():
    """Initialize STT provider based on STT_PROVIDER env variable."""
    global stt_provider
    
    # Map string to enum
    provider_map = {
        "google": STTProviderType.GOOGLE,
        "vosk": STTProviderType.VOSK,
        "openai": STTProviderType.OPENAI_WHISPER,
    }
    
    selected = STT_PROVIDER.lower()
    print(f"[INFO] STT_PROVIDER configured: {selected}")
    
    if selected not in provider_map:
        print(f"[WARNING] Unknown STT_PROVIDER '{selected}', using google")
        selected = "google"
    
    try:
        stt_provider = create_stt_provider(
            provider_type=provider_map[selected],
            sample_rate=SAMPLERATE,
            api_key=os.getenv("OPENAI_API_KEY") if selected == "openai" else None
        )
        print(f"[OK] STT provider initialized: {stt_provider.provider_type.value}")
    except Exception as e:
        print(f"[WARNING] Failed to init {selected} STT: {e}")
        # Fallback chain: google -> vosk
        fallbacks = ["google", "vosk"] if selected != "google" else ["vosk"]
        for fallback in fallbacks:
            try:
                stt_provider = create_stt_provider(
                    provider_type=provider_map[fallback],
                    sample_rate=SAMPLERATE
                )
                print(f"[OK] Fallback to {fallback} STT")
                return
            except:
                continue
        print("[ERROR] No STT provider available")
        stt_provider = None


async def process_user_request(user_input: str, openai_client, user_id: str = None) -> str:
    """Process user input through the assistant and return response."""
    import asyncio
    
    if not openai_client:
        return "OpenAI API key not configured. Please set OPENAI_API_KEY."
    
    try:
        loop = asyncio.get_event_loop()
        response_data = await loop.run_in_executor(None, classify_user_request, user_input)
        
        responses = []
        
        for req in response_data.requests:
            print(f"[ASSISTANT] Service: {req.DesiredService}, desc: {req.desc}")
            
            if req.DesiredService == "fin-manager":
                finance_manager = FinanceManager()
                response = await loop.run_in_executor(
                    None, finance_manager.process_request, openai_client, req.desc, user_input, user_id
                )
                responses.append(response)
                
            elif req.DesiredService == "task":
                task_manager = TaskManager()
                response = await loop.run_in_executor(
                    None, task_manager.process_request, openai_client, user_input
                )
                responses.append(response)
                
            elif req.DesiredService == "talk":
                conversation_manager = ConversationManager()
                response_obj = await loop.run_in_executor(
                    None, conversation_manager.process_conversation, openai_client, user_input
                )
                response = response_obj.responseToUser if hasattr(response_obj, 'responseToUser') else str(response_obj)
                responses.append(response)
                
            elif req.DesiredService == "goodbye":
                responses.append(req.desc)
        
        return " ".join(responses) if responses else "I didn't understand that. Could you repeat?"
        
    except Exception as e:
        print(f"[ASSISTANT ERROR] {e}")
        traceback.print_exc()
        return "I encountered an error. Please try again."


@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time audio streaming."""
    from openai import OpenAI
    import jwt
    
    await websocket.accept()
    
    # Extract user_id from token query param
    user_id = None
    try:
        token = websocket.query_params.get("token")
        if token:
            # Decode JWT to get user_id (Firebase tokens are JWTs)
            decoded = jwt.decode(token, options={"verify_signature": False})
            user_id = decoded.get("user_id") or decoded.get("sub")
            print(f"[STREAM] User ID: {user_id}")
    except Exception as e:
        print(f"[STREAM] Could not extract user_id: {e}")
    
    # Get OpenAI client
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_client = OpenAI(api_key=openai_key) if openai_key else None
    
    chunk_size = int(SAMPLERATE * BYTES_PER_SAMPLE * CHANNELS * CHUNK_MS / 1000)
    audio_buffer = bytearray()
    speech_buffer = bytearray()
    silence_ms = 0

    print("[STREAM] WebSocket connected")

    try:
        while True:
            data = await websocket.receive_bytes()
            audio_buffer.extend(data)

            while len(audio_buffer) >= chunk_size:
                chunk = audio_buffer[:chunk_size]
                audio_buffer = audio_buffer[chunk_size:]

                # Voice Activity Detection
                audio_np = np.frombuffer(chunk, dtype=np.int16)
                rms = np.sqrt(np.mean(audio_np.astype(np.float32) ** 2))

                if rms > SILENCE_THRESHOLD:
                    silence_ms = 0
                    speech_buffer.extend(chunk)
                else:
                    silence_ms += CHUNK_MS
                    
                    # Process when silence detected after speech
                    if silence_ms >= SILENCE_DURATION_MS and len(speech_buffer) > 0:
                        if stt_provider:
                            try:
                                text = stt_provider.transcribe(speech_buffer)
                                if text:
                                    print(f"[TRANSCRIPT] {text}")
                                    
                                    try:
                                        response = await process_user_request(text, openai_client, user_id)
                                        await websocket.send_json({
                                            "response": response,
                                            "type": "assistant_response"
                                        })
                                        print(f"[ASSISTANT] Sent: {response[:50]}...")
                                    except Exception as e:
                                        print(f"[ASSISTANT ERROR] {e}")
                                        await websocket.send_json({
                                            "response": "Sorry, I encountered an error.",
                                            "type": "assistant_response",
                                            "error": str(e)
                                        })
                            except Exception as stt_error:
                                # Log STT error but keep the connection alive
                                print(f"[STT ERROR] {stt_error}")
                                # Don't crash - just continue listening
                        
                        speech_buffer = bytearray()
                        silence_ms = 0

    except Exception as e:
        print(f"[STREAM] Error: {e}")
    finally:
        # Final transcription on disconnect
        if len(speech_buffer) > 0 and stt_provider:
            final_text = stt_provider.transcribe(speech_buffer)
            if final_text:
                print(f"[TRANSCRIPT] Final: {final_text}")
                try:
                    response = await process_user_request(final_text, openai_client, user_id)
                    await websocket.send_json({
                        "response": response,
                        "type": "assistant_response"
                    })
                except:
                    pass
        print("[STREAM] WebSocket disconnected")
