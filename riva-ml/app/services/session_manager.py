"""
Session Manager - Short-term conversation context.
Stores active intent, last topic, pending questions for multi-turn conversations.

Supports two backends:
1. Redis (production) — persistent across restarts, multi-instance safe
2. In-memory (fallback) — if Redis is unavailable

Set REDIS_URL env var to enable Redis. Falls back to in-memory automatically.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import threading
import time
import json
import os
from dotenv import load_dotenv

load_dotenv()


class SessionManager:
    """
    Manages short-term session context for multi-turn conversations.

    Example use cases:
    - "spent 500" -> "on what?" -> "dinner" (tracks pending question)
    - "went to movie" -> "spent 500 there" (tracks last_topic=movie)
    """

    def __init__(self, expiry_minutes: int = 15):
        self._expiry_minutes = expiry_minutes
        self._redis = None
        self._use_redis = False

        # Try to connect to Redis
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis
                self._redis = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_timeout=3,
                    socket_connect_timeout=3,
                )
                # Test connection
                self._redis.ping()
                self._use_redis = True
                print(f"[SESSION] Connected to Redis: {redis_url}")
            except Exception as e:
                print(f"[SESSION] Redis unavailable ({e}), using in-memory fallback")
                self._redis = None
                self._use_redis = False

        if not self._use_redis:
            print("[SESSION] Using in-memory session storage")
            self._sessions: Dict[str, Dict] = {}
            self._lock = threading.Lock()

            # Start background cleanup thread for in-memory mode
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_expired, daemon=True
            )
            self._cleanup_thread.start()

    # ------------------------------------------------------------------
    # Redis key helpers
    # ------------------------------------------------------------------

    def _redis_key(self, user_id: str) -> str:
        return f"riva:session:{user_id}"

    def _redis_ttl(self) -> int:
        return self._expiry_minutes * 60

    # ------------------------------------------------------------------
    # In-memory cleanup
    # ------------------------------------------------------------------

    def _cleanup_expired(self):
        """Background thread to clean expired sessions (in-memory only)."""
        while True:
            time.sleep(60)
            with self._lock:
                now = datetime.utcnow()
                expired = [
                    uid
                    for uid, data in self._sessions.items()
                    if data.get("expires_at") and now > data["expires_at"]
                ]
                for uid in expired:
                    del self._sessions[uid]

    def _get_expiry(self) -> datetime:
        return datetime.utcnow() + timedelta(minutes=self._expiry_minutes)

    # ------------------------------------------------------------------
    # New session template
    # ------------------------------------------------------------------

    @staticmethod
    def _new_session(user_id: str) -> Dict:
        return {
            "user_id": user_id,
            "active_intent": None,
            "last_topic": None,
            "last_category": None,
            "pending_question": None,
            "pending_data": {},
            "conversation_history": [],
            "created_at": datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # Session Management
    # ------------------------------------------------------------------

    def get_session(self, user_id: str) -> Dict:
        """Get or create session for user."""
        if self._use_redis:
            raw = self._redis.get(self._redis_key(user_id))
            if raw:
                session = json.loads(raw)
                # Refresh TTL on access
                self._redis.expire(self._redis_key(user_id), self._redis_ttl())
                return session
            else:
                session = self._new_session(user_id)
                self._redis.setex(
                    self._redis_key(user_id),
                    self._redis_ttl(),
                    json.dumps(session, default=str),
                )
                return session
        else:
            with self._lock:
                if user_id not in self._sessions:
                    session = self._new_session(user_id)
                    session["expires_at"] = self._get_expiry()
                    self._sessions[user_id] = session
                else:
                    self._sessions[user_id]["expires_at"] = self._get_expiry()
                return self._sessions[user_id].copy()

    def _save_session(self, user_id: str, session: Dict):
        """Persist session (Redis) or update in-memory."""
        if self._use_redis:
            self._redis.setex(
                self._redis_key(user_id),
                self._redis_ttl(),
                json.dumps(session, default=str),
            )
        # In-memory: session dict is already a reference in self._sessions

    def update_session(self, user_id: str, **kwargs) -> Dict:
        """Update session fields."""
        if self._use_redis:
            session = self.get_session(user_id)
            for key, value in kwargs.items():
                if key in session:
                    session[key] = value
            self._save_session(user_id, session)
            return session
        else:
            with self._lock:
                if user_id not in self._sessions:
                    self.get_session(user_id)
                session = self._sessions[user_id]
                for key, value in kwargs.items():
                    if key in session:
                        session[key] = value
                session["expires_at"] = self._get_expiry()
                return session.copy()

    def clear_session(self, user_id: str):
        """Clear a user's session."""
        if self._use_redis:
            self._redis.delete(self._redis_key(user_id))
        else:
            with self._lock:
                if user_id in self._sessions:
                    del self._sessions[user_id]

    # ------------------------------------------------------------------
    # Intent & Context Tracking
    # ------------------------------------------------------------------

    def set_active_intent(self, user_id: str, intent: str):
        """Set the current active intent."""
        return self.update_session(user_id, active_intent=intent)

    def set_last_topic(self, user_id: str, topic: str):
        """Set the last discussed topic."""
        return self.update_session(user_id, last_topic=topic)

    def set_last_category(self, user_id: str, category: str):
        """Set the last expense category used."""
        return self.update_session(user_id, last_category=category)

    def set_pending_question(
        self, user_id: str, question: str, pending_data: Dict = None
    ):
        """Set a pending question that needs user response."""
        return self.update_session(
            user_id,
            pending_question=question,
            pending_data=pending_data or {},
        )

    def clear_pending(self, user_id: str):
        """Clear pending question after it's resolved."""
        return self.update_session(
            user_id,
            pending_question=None,
            pending_data={},
        )

    # ------------------------------------------------------------------
    # Conversation History
    # ------------------------------------------------------------------

    def add_message(self, user_id: str, role: str, content: str):
        """Add a message to session history. Keeps last 20 messages."""
        if self._use_redis:
            session = self.get_session(user_id)
            history = session.get("conversation_history", [])
            history.append({
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
            })
            if len(history) > 20:
                history = history[-20:]
            session["conversation_history"] = history
            self._save_session(user_id, session)
        else:
            session = self.get_session(user_id)
            history = session.get("conversation_history", [])
            history.append({
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
            })
            if len(history) > 20:
                history = history[-20:]
            with self._lock:
                self._sessions[user_id]["conversation_history"] = history
                self._sessions[user_id]["expires_at"] = self._get_expiry()

    def get_recent_messages(self, user_id: str, count: int = 5) -> list:
        """Get recent messages for context."""
        session = self.get_session(user_id)
        history = session.get("conversation_history", [])
        return history[-count:] if history else []

    # ------------------------------------------------------------------
    # Context for Prompt Building
    # ------------------------------------------------------------------

    def get_context_for_prompt(self, user_id: str) -> Dict:
        """Get session context formatted for prompt building."""
        session = self.get_session(user_id)
        return {
            "active_intent": session.get("active_intent"),
            "last_topic": session.get("last_topic"),
            "last_category": session.get("last_category"),
            "pending_question": session.get("pending_question"),
            "pending_data": session.get("pending_data", {}),
            "recent_messages": session.get("conversation_history", [])[-5:],
        }


# ------------------------------------------------------------------
# Global session manager instance
# ------------------------------------------------------------------
_session_manager = None


def get_session_manager() -> SessionManager:
    """Get or create global session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(expiry_minutes=15)
    return _session_manager
