from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import os
import json
import asyncio
import base64
from google import genai
from google.genai import types
from typing import Dict, Any

from agents import FinanceAgent, ProductivityAgent
from services.memory_service import MemoryService
from services.calendar_service import CalendarService
from services.db import user_memory_collection, transactions_collection, calendar_tokens_collection
from openai import OpenAI

router = APIRouter(tags=["Gemini Live"])


async def get_tools_and_handlers(user_id: str):
    """Build tool declarations and handler map for a given user session."""
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    memory_service = MemoryService(user_memory_collection)
    calendar_service = CalendarService(calendar_tokens_collection)

    finance_agent = FinanceAgent(
        openai_client=openai_client,
        transactions_collection=transactions_collection,
        memory_service=memory_service,
    )
    productivity_agent = ProductivityAgent(
        calendar_service=calendar_service,
        openai_client=openai_client,
    )

    # Gemini function declarations
    tools = [
        {
            "function_declarations": [
                {
                    "name": "add_expense",
                    "description": "Add a new expense or income transaction for the user.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "amount":      {"type": "NUMBER", "description": "The transaction amount."},
                            "category":    {"type": "STRING", "description": "Category: food, transport, shopping, bills, entertainment, health, personal, other."},
                            "description": {"type": "STRING", "description": "Short description of the transaction."},
                            "date":        {"type": "STRING", "description": "Date in YYYY-MM-DD format (optional, defaults to today)."},
                        },
                        "required": ["amount", "category"],
                    },
                },
                {
                    "name": "query_spending",
                    "description": "Query the user's spending history and totals.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "time_range": {"type": "STRING", "description": "Time range: today, this_week, this_month, last_month, all."},
                            "category":   {"type": "STRING", "description": "Filter by category (optional)."},
                        },
                    },
                },
                {
                    "name": "schedule_event",
                    "description": "Schedule a new event on the user's Google Calendar.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "title":       {"type": "STRING", "description": "Event title."},
                            "start_time":  {"type": "STRING", "description": "Start time in ISO 8601 format."},
                            "end_time":    {"type": "STRING", "description": "End time in ISO 8601 format (optional, defaults to 1 hour after start)."},
                            "description": {"type": "STRING", "description": "Event description (optional)."},
                        },
                        "required": ["title", "start_time"],
                    },
                },
                {
                    "name": "list_events",
                    "description": "List the user's upcoming calendar events.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "days": {"type": "NUMBER", "description": "How many days ahead to look (default 1)."},
                        },
                    },
                },
            ]
        }
    ]

    async def handle_tool_call(name: str, args: Dict[str, Any]) -> Dict:
        print(f"[GEMINI_LIVE] Tool call: {name}  args={args}")
        context = {"user_id": user_id}

        if name == "add_expense":
            resp = await finance_agent._handle_add_transaction(
                intent="add_expense",
                user_input=f"Add {args.get('amount')} for {args.get('description', args.get('category'))}",
                context=context,
                memory={},
            )
            return {"status": "success", "response": resp.response}

        elif name == "query_spending":
            resp = await finance_agent._handle_query(
                intent="query_spending",
                user_input=f"How much did I spend {args.get('time_range', 'this month')}?",
                context=context,
                memory={},
            )
            return {"status": "success", "response": resp.response}

        elif name == "schedule_event":
            from dateutil.parser import parse
            from datetime import timedelta

            start_time = args["start_time"]
            end_time = args.get("end_time")
            if not end_time:
                try:
                    end_time = (parse(start_time) + timedelta(hours=1)).isoformat()
                except Exception:
                    end_time = start_time

            result = await calendar_service.create_event(
                user_id=user_id,
                title=args["title"],
                start_time=start_time,
                end_time=end_time,
                description=args.get("description", ""),
            )
            if result:
                return {"status": "success", "message": f"Event '{args['title']}' scheduled."}
            return {"status": "error", "message": "Failed to create event."}

        elif name == "list_events":
            from datetime import datetime, timedelta

            days = int(args.get("days", 1))
            events = await calendar_service.list_events(
                user_id,
                time_min=datetime.utcnow(),
                time_max=datetime.utcnow() + timedelta(days=days),
            )
            return {"status": "success", "events": events or []}

        return {"error": f"Unknown tool: {name}"}

    return tools, handle_tool_call


@router.websocket("/gemini-live")
async def gemini_live_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("[GEMINI_LIVE] WebSocket connected")

    # --- Auth ---
    user_id = "anonymous"
    try:
        token = websocket.query_params.get("token")
        if token and token != "mock_token":
            import jwt
            decoded = jwt.decode(token, options={"verify_signature": False})
            user_id = decoded.get("user_id") or decoded.get("sub") or "anonymous"
    except Exception as e:
        print(f"[GEMINI_LIVE] Auth warning: {e}")

    # --- API key check ---
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        await websocket.send_json({"error": "GEMINI_API_KEY not configured on backend."})
        await websocket.close()
        return

    print(f"[GEMINI_LIVE] API key loaded ({api_key[:8]}…), user={user_id}")

    # --- Build client and tools ---
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    tools, handle_tool_call = await get_tools_and_handlers(user_id)

    # --- Session config ---
    # response_modalities must be at the top level of LiveConnectConfig
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        tools=tools,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part(text=(
                "You are RIVA, a helpful personal AI assistant specializing in personal finance "
                "and productivity. Help users track their spending, manage budgets, and organize "
                "their calendar. Be concise and conversational since this is a voice interface."
            ))],
        ),
    )

    # Model that supports Live / bidiGenerateContent
    model_id = "gemini-2.5-flash-native-audio-latest"

    try:
        async with client.aio.live.connect(model=model_id, config=config) as session:
            print("[GEMINI_LIVE] Connected to Gemini Live API")

            # ── Task 1: Gemini → Frontend ─────────────────────────────────────
            async def receive_from_gemini():
                # session.receive() yields messages for ONE turn then exits.
                # We loop continuously to handle multi-turn conversations.
                while True:
                    async for message in session.receive():
                        if message.server_content:
                            if message.server_content.model_turn:
                                for part in message.server_content.model_turn.parts:
                                    if part.inline_data:
                                        audio_b64 = base64.b64encode(
                                            part.inline_data.data
                                        ).decode("utf-8")
                                        await websocket.send_json(
                                            {"type": "audio", "data": audio_b64}
                                        )
                            if message.server_content.turn_complete:
                                await websocket.send_json({"type": "turn_complete"})

                        if message.tool_call:
                            for call in message.tool_call.function_calls:
                                result = await handle_tool_call(call.name, call.args)
                                # Dedicated SDK method — no deprecation warnings, correct format
                                await session.send_tool_response(
                                    function_responses=types.FunctionResponse(
                                        name=call.name,
                                        id=call.id,
                                        response=result,
                                    )
                                )

            # ── Task 2: Frontend → Gemini ─────────────────────────────────────
            async def receive_from_frontend():
                try:
                    while True:
                        data = await websocket.receive()
                        if "bytes" in data:
                            # Raw PCM audio from the browser microphone (16 kHz, 16-bit)
                            await session.send_realtime_input(
                                audio=types.Blob(
                                    data=data["bytes"],
                                    mime_type="audio/pcm;rate=16000",
                                )
                            )
                        elif "text" in data:
                            msg = json.loads(data["text"])
                            if msg.get("type") == "input_text":
                                await session.send_client_content(
                                    turns=types.Content(
                                        role="user",
                                        parts=[types.Part(text=msg["text"])],
                                    ),
                                    turn_complete=True,
                                )
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    print(f"[GEMINI_LIVE] Frontend receive error: {e}")

            # Run both tasks concurrently
            await asyncio.gather(receive_from_gemini(), receive_from_frontend())

    except WebSocketDisconnect:
        print("[GEMINI_LIVE] WebSocket disconnected")
    except Exception as e:
        print(f"[GEMINI_LIVE] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("[GEMINI_LIVE] Session ended")
