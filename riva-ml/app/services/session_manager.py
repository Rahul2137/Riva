"""
Session Manager - Short-term conversation context.
Stores active intent, last topic, pending questions for multi-turn conversations.

Uses in-memory storage with auto-expiry. Can be migrated to Redis later.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import threading
import time


class SessionManager:
    """
    Manages short-term session context for multi-turn conversations.
    
    Example use cases:
    - "spent 500" → "on what?" → "dinner" (tracks pending question)
    - "went to movie" → "spent 500 there" (tracks last_topic=movie)
    """
    
    def __init__(self, expiry_minutes: int = 10):
        self._sessions: Dict[str, Dict] = {}
        self._expiry_minutes = expiry_minutes
        self._lock = threading.Lock()
        
        # Start background cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_expired, daemon=True)
        self._cleanup_thread.start()
    
    def _cleanup_expired(self):
        """Background thread to clean expired sessions."""
        while True:
            time.sleep(60)  # Check every minute
            with self._lock:
                now = datetime.utcnow()
                expired = [
                    uid for uid, data in self._sessions.items()
                    if data.get("expires_at") and now > data["expires_at"]
                ]
                for uid in expired:
                    del self._sessions[uid]
    
    def _get_expiry(self) -> datetime:
        return datetime.utcnow() + timedelta(minutes=self._expiry_minutes)
    
    # ----------------------------
    # Session Management
    # ----------------------------
    
    def get_session(self, user_id: str) -> Dict:
        """Get or create session for user."""
        with self._lock:
            if user_id not in self._sessions:
                self._sessions[user_id] = {
                    "user_id": user_id,
                    "active_intent": None,
                    "last_topic": None,
                    "last_category": None,
                    "pending_question": None,
                    "pending_data": {},
                    "conversation_history": [],
                    "created_at": datetime.utcnow(),
                    "expires_at": self._get_expiry()
                }
            else:
                # Refresh expiry on access
                self._sessions[user_id]["expires_at"] = self._get_expiry()
            
            return self._sessions[user_id].copy()
    
    def update_session(self, user_id: str, **kwargs) -> Dict:
        """Update session fields."""
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
        with self._lock:
            if user_id in self._sessions:
                del self._sessions[user_id]
    
    # ----------------------------
    # Intent & Context Tracking
    # ----------------------------
    
    def set_active_intent(self, user_id: str, intent: str):
        """Set the current active intent (e.g., 'add_expense', 'get_insights')."""
        return self.update_session(user_id, active_intent=intent)
    
    def set_last_topic(self, user_id: str, topic: str):
        """Set the last discussed topic (e.g., 'movie', 'restaurant')."""
        return self.update_session(user_id, last_topic=topic)
    
    def set_last_category(self, user_id: str, category: str):
        """Set the last expense category used."""
        return self.update_session(user_id, last_category=category)
    
    def set_pending_question(self, user_id: str, question: str, pending_data: Dict = None):
        """
        Set a pending question that needs user response.
        
        Example: After "spent 500", set pending_question="category"
                 with pending_data={"amount": 500}
        """
        return self.update_session(
            user_id,
            pending_question=question,
            pending_data=pending_data or {}
        )
    
    def clear_pending(self, user_id: str):
        """Clear pending question after it's resolved."""
        return self.update_session(
            user_id,
            pending_question=None,
            pending_data={}
        )
    
    # ----------------------------
    # Conversation History
    # ----------------------------
    
    def add_message(self, user_id: str, role: str, content: str):
        """
        Add a message to session history.
        Keeps last 10 messages for context.
        """
        session = self.get_session(user_id)
        history = session.get("conversation_history", [])
        
        history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Keep only last 10 messages
        if len(history) > 10:
            history = history[-10:]
        
        with self._lock:
            self._sessions[user_id]["conversation_history"] = history
            self._sessions[user_id]["expires_at"] = self._get_expiry()
    
    def get_recent_messages(self, user_id: str, count: int = 5) -> list:
        """Get recent messages for context."""
        session = self.get_session(user_id)
        history = session.get("conversation_history", [])
        return history[-count:] if history else []
    
    # ----------------------------
    # Context for Prompt Building
    # ----------------------------
    
    def get_context_for_prompt(self, user_id: str) -> Dict:
        """
        Get session context formatted for prompt building.
        """
        session = self.get_session(user_id)
        return {
            "active_intent": session.get("active_intent"),
            "last_topic": session.get("last_topic"),
            "last_category": session.get("last_category"),
            "pending_question": session.get("pending_question"),
            "pending_data": session.get("pending_data", {}),
            "recent_messages": session.get("conversation_history", [])[-5:]
        }


# Global session manager instance
# In production, this would be replaced with Redis
_session_manager = None

def get_session_manager() -> SessionManager:
    """Get or create global session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(expiry_minutes=10)
    return _session_manager
