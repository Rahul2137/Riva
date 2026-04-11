"""
GeneralAgent - Handles general conversation, Q&A, and memory updates.

This is the fallback agent: if no other agent claims an intent,
the GeneralAgent handles it.

Intents handled:
- conversation (greetings, casual chat, advice)
- update_memory (user shares personal info / preferences)
- general_question (Q&A, web info, factual questions)
"""
from typing import Dict, Any, List
from openai import OpenAI
import os
import json
from dotenv import load_dotenv

from .base_agent import BaseAgent, AgentResponse

load_dotenv()


class GeneralAgent(BaseAgent):
    """GPT-powered agent for general conversation, Q&A, and memory updates."""

    SUPPORTED_INTENTS = [
        "conversation",
        "update_memory",
        "general_question",
    ]

    def __init__(self, openai_client: OpenAI = None, memory_service=None):
        self.client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.memory_service = memory_service

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    @property
    def domain(self) -> str:
        return "general"

    def get_supported_intents(self) -> List[str]:
        return self.SUPPORTED_INTENTS

    async def handle(
        self,
        intent: str,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> AgentResponse:
        """Handle general conversation intents."""
        print(f"[GENERAL_AGENT] Handling intent={intent}")

        if intent == "update_memory":
            return await self._handle_memory_update(user_input, context, memory)
        else:
            # conversation + general_question + unknown intents
            return await self._handle_conversation(user_input, context, memory)

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    async def _handle_conversation(
        self,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> AgentResponse:
        """Handle general conversation / Q&A."""
        # Build conversation history for context
        messages = [
            {"role": "system", "content": self._conversation_prompt(memory)},
        ]

        # Add recent conversation for continuity
        recent = context.get("recent_messages", [])
        for msg in recent[-5:]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        messages.append({"role": "user", "content": user_input})

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=300,
            )
            response_text = response.choices[0].message.content

            # Check if GPT detected a memory-worthy statement
            memory_updates = await self._detect_memory_updates(user_input, response_text)

            return AgentResponse(
                response=response_text,
                memory_updates=memory_updates,
            )
        except Exception as e:
            print(f"[GENERAL_AGENT] Conversation error: {e}")
            return AgentResponse(
                response="I'm here to help! Could you say that again?",
                metadata={"error": str(e)},
            )

    async def _handle_memory_update(
        self,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> AgentResponse:
        """Handle explicit memory updates (user shares preferences/facts)."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._memory_extraction_prompt()},
                    {"role": "user", "content": user_input},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=300,
            )
            result = json.loads(response.choices[0].message.content)

            memory_updates = result.get("memory_updates", [])
            response_text = result.get("response", "Noted! I'll remember that.")

            return AgentResponse(
                response=response_text,
                memory_updates=memory_updates,
            )
        except Exception as e:
            print(f"[GENERAL_AGENT] Memory update error: {e}")
            return AgentResponse(response="I'll try to remember that!")

    # ------------------------------------------------------------------
    # Memory detection
    # ------------------------------------------------------------------

    async def _detect_memory_updates(
        self,
        user_input: str,
        response_text: str,
    ) -> List[Dict[str, Any]]:
        """Detect if the user's message contains memory-worthy information.

        This runs passively during conversation to capture
        preferences, facts, and habits without explicit memory intents.
        """
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._passive_memory_prompt()},
                    {"role": "user", "content": user_input},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=200,
            )
            result = json.loads(response.choices[0].message.content)
            updates = result.get("memory_updates", [])
            # Only return high-confidence updates
            return [u for u in updates if u.get("confidence", 0) >= 0.8]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    def _conversation_prompt(self, memory: Dict) -> str:
        base = """You are RIVA, a personal AI assistant. You are:
- Friendly, warm, and supportive
- Concise (2-3 sentences max for voice delivery)
- Proactive with suggestions when relevant
- Never judgmental"""

        # Inject known facts about the user
        if memory:
            facts = memory.get("facts", [])
            preferences = memory.get("preferences", [])
            if facts or preferences:
                base += "\n\nAbout the user:"
                for f in facts:
                    base += f"\n- {f['key']}: {f['value']}"
                for p in preferences:
                    base += f"\n- Prefers: {p['key']} = {p['value']}"

        return base

    def _memory_extraction_prompt(self) -> str:
        return """You are RIVA's memory extractor. The user has shared personal information.
Extract it into structured memory updates.

RETURN THIS JSON:
{
  "response": "Natural acknowledgement (e.g. 'Noted! I'll remember that.')",
  "memory_updates": [
    {
      "type": "preference | habit | fact | constraint",
      "key": "descriptive_key (e.g. 'diet', 'wake_time', 'monthly_budget')",
      "value": "the value",
      "confidence": 0.0-1.0
    }
  ]
}

EXAMPLES:
- "I'm vegetarian" → fact: diet=vegetarian (confidence 0.95)
- "I usually wake up at 6am" → habit: wake_time=6am (confidence 0.85)
- "I prefer morning meetings" → preference: meeting_time=morning (confidence 0.9)"""

    def _passive_memory_prompt(self) -> str:
        return """Analyze this user message. If it contains personal facts, preferences, 
or habits worth remembering, extract them. If nothing is worth remembering, return empty.

RETURN THIS JSON:
{
  "memory_updates": [
    {
      "type": "preference | habit | fact",
      "key": "descriptive_key",
      "value": "the value",
      "confidence": 0.0-1.0
    }
  ]
}

Only extract with confidence >= 0.8. Return empty array if nothing notable."""
