"""
Audio Streaming Router
Handles WebSocket for real-time voice processing.

v2: Uses agent-based Orchestrator exclusively (legacy path removed).
"""
import os
import traceback
import numpy as np
from fastapi import APIRouter, WebSocket

from providers import create_stt_provider, STTProviderType

router = APIRouter(tags=["Voice Stream"])

# Audio Config - Optimized for lower latency
SAMPLERATE = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2
SILENCE_THRESHOLD = 800  # Increased to prevent ambient noise from triggering
SILENCE_DURATION_MS = 600 # Decreased to respond faster after user stops speaking
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
            api_key=os.getenv("OPENAI_API_KEY") if selected == "openai" else None,
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
                    sample_rate=SAMPLERATE,
                )
                print(f"[OK] Fallback to {fallback} STT")
                return
            except Exception:
                continue
        print("[ERROR] No STT provider available")
        stt_provider = None


# ---------------------------------------------------------------------------
# Agent registry & orchestrator — initialised once and reused across requests
# ---------------------------------------------------------------------------
_orchestrator = None


async def _get_orchestrator():
    """Lazy-initialise the agent-based orchestrator (singleton)."""
    global _orchestrator
    if _orchestrator is not None:
        return _orchestrator

    from openai import OpenAI
    from agents import AgentRegistry, FinanceAgent, ProductivityAgent, GeneralAgent
    from services.orchestrator import Orchestrator
    from services.memory_service import MemoryService
    from services.calendar_service import CalendarService
    from services.db import user_memory_collection, transactions_collection, calendar_tokens_collection

    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Build services
    memory_service = MemoryService(user_memory_collection)
    calendar_service = CalendarService(calendar_tokens_collection)

    # Build agent registry
    registry = AgentRegistry()

    # Register agents
    await registry.register(
        FinanceAgent(
            openai_client=openai_client,
            transactions_collection=transactions_collection,
            memory_service=memory_service,
        )
    )
    await registry.register(
        ProductivityAgent(
            calendar_service=calendar_service,
            openai_client=openai_client,
        )
    )
    await registry.register(
        GeneralAgent(openai_client=openai_client, memory_service=memory_service),
        is_fallback=True,
    )

    # Build orchestrator
    _orchestrator = Orchestrator(
        agent_registry=registry,
        memory_service=memory_service,
        openai_client=openai_client,
    )

    print("[OK] Agent-based orchestrator initialised")
    return _orchestrator


async def process_user_request_stream(user_input: str, user_id: str = None):
    """Process user input through the orchestrator and yield responses."""
    if not os.getenv("OPENAI_API_KEY"):
        yield {"type": "final", "response": "OpenAI API key not configured. Please set OPENAI_API_KEY."}
        return

    if not user_id:
        user_id = "anonymous"

    try:
        orchestrator = await _get_orchestrator()
        async for update in orchestrator.process_request_stream(user_id, user_input):
            if update["type"] == "final":
                print(
                    f"[STREAM] Intent: {update.get('intent')}, "
                    f"Domain: {update.get('domain')}, "
                    f"Actions: {update.get('actions_taken')}"
                )
            yield update

    except Exception as e:
        print(f"[STREAM] Orchestrator error: {e}")
        traceback.print_exc()
        yield {"type": "final", "response": "I encountered an error. Please try again."}


@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time audio streaming."""
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
                                    
                                    await websocket.send_json({
                                        "text": text,
                                        "type": "transcript",
                                    })

                                    try:
                                        async for update in process_user_request_stream(text, user_id):
                                            # Send each update (immediate filler or final response)
                                            await websocket.send_json({
                                                "response": update["response"],
                                                "type": "assistant_response",
                                                "is_final": update["type"] == "final"
                                            })
                                            print(f"[ASSISTANT] {update['type'].upper()}: {update['response'][:50]}...")
                                    except Exception as e:
                                        print(f"[ASSISTANT ERROR] {e}")
                                        await websocket.send_json({
                                            "response": "Sorry, I encountered an error.",
                                            "type": "assistant_response",
                                            "is_final": True,
                                            "error": str(e),
                                        })
                            except Exception as stt_error:
                                # Log STT error but keep the connection alive
                                print(f"[STT ERROR] {stt_error}")

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
                    await websocket.send_json({
                        "text": final_text,
                        "type": "transcript",
                    })
                    async for update in process_user_request_stream(final_text, user_id):
                        await websocket.send_json({
                            "response": update["response"],
                            "type": "assistant_response",
                            "is_final": update["type"] == "final"
                        })
                except Exception:
                    pass
        print("[STREAM] WebSocket disconnected")
