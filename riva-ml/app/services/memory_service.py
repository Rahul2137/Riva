"""
Memory Service - CRUD operations for user memories.
Handles facts, preferences, habits, constraints, and goals.

Designed to be modular for future microservices migration.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from bson import ObjectId
from enum import Enum


class MemoryType(str, Enum):
    PREFERENCE = "preference"
    HABIT = "habit"
    FACT = "fact"
    CONSTRAINT = "constraint"
    GOAL = "goal"
    SYSTEM = "system"


class MemorySource(str, Enum):
    EXPLICIT = "explicit"      # User stated directly
    INFERRED = "inferred"      # System learned from behavior
    SYSTEM = "system"          # System-generated


class MemoryService:
    """
    Service for managing user memories in MongoDB.
    Memories are structured knowledge about the user (NOT chat history).
    """
    
    def __init__(self, collection):
        """
        Initialize with MongoDB collection.
        Allows dependency injection for testing and microservices.
        """
        self.collection = collection
    
    # ----------------------------
    # CRUD Operations
    # ----------------------------
    
    async def add_memory(
        self,
        user_id: str,
        memory_type: MemoryType,
        key: str,
        value: Any,
        confidence: float = 1.0,
        source: MemorySource = MemorySource.EXPLICIT
    ) -> str:
        """
        Add a new memory for a user.
        
        Examples:
        - add_memory(user_id, "preference", "meeting_time", {"avoid": "morning"})
        - add_memory(user_id, "constraint", "monthly_budget", {"amount": 30000})
        """
        memory = {
            "user_id": user_id,
            "memory_type": memory_type.value if isinstance(memory_type, MemoryType) else memory_type,
            "key": key,
            "value": value,
            "confidence": min(max(confidence, 0.0), 1.0),  # Clamp 0-1
            "source": source.value if isinstance(source, MemorySource) else source,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = await self.collection.insert_one(memory)
        return str(result.inserted_id)
    
    async def get_memories(
        self,
        user_id: str,
        memory_type: Optional[MemoryType] = None,
        is_active: bool = True
    ) -> List[Dict]:
        """
        Get all memories for a user, optionally filtered by type.
        """
        query = {"user_id": user_id, "is_active": is_active}
        if memory_type:
            query["memory_type"] = memory_type.value if isinstance(memory_type, MemoryType) else memory_type
        
        cursor = self.collection.find(query).sort("updated_at", -1)
        memories = await cursor.to_list(length=100)
        
        # Convert ObjectId to string
        for mem in memories:
            mem["_id"] = str(mem["_id"])
        
        return memories
    
    async def get_memory_by_key(
        self,
        user_id: str,
        key: str
    ) -> Optional[Dict]:
        """
        Get a specific memory by key.
        """
        memory = await self.collection.find_one({
            "user_id": user_id,
            "key": key,
            "is_active": True
        })
        if memory:
            memory["_id"] = str(memory["_id"])
        return memory
    
    async def update_memory(
        self,
        user_id: str,
        key: str,
        value: Any,
        confidence: Optional[float] = None
    ) -> bool:
        """
        Update an existing memory's value.
        """
        update_data = {
            "value": value,
            "updated_at": datetime.utcnow()
        }
        if confidence is not None:
            update_data["confidence"] = min(max(confidence, 0.0), 1.0)
        
        result = await self.collection.update_one(
            {"user_id": user_id, "key": key, "is_active": True},
            {"$set": update_data}
        )
        return result.modified_count > 0
    
    async def upsert_memory(
        self,
        user_id: str,
        memory_type: MemoryType,
        key: str,
        value: Any,
        confidence: float = 1.0,
        source: MemorySource = MemorySource.EXPLICIT
    ) -> str:
        """
        Insert or update a memory. Useful for preferences that should be unique.
        """
        existing = await self.get_memory_by_key(user_id, key)
        if existing:
            await self.update_memory(user_id, key, value, confidence)
            return existing["_id"]
        else:
            return await self.add_memory(user_id, memory_type, key, value, confidence, source)
    
    async def deactivate_memory(
        self,
        user_id: str,
        key: str
    ) -> bool:
        """
        Soft-delete a memory (set is_active=False).
        """
        result = await self.collection.update_one(
            {"user_id": user_id, "key": key},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0
    
    # ----------------------------
    # Convenience Methods
    # ----------------------------
    
    async def get_user_preferences(self, user_id: str) -> List[Dict]:
        """Get all active preferences for a user."""
        return await self.get_memories(user_id, MemoryType.PREFERENCE)
    
    async def get_user_constraints(self, user_id: str) -> List[Dict]:
        """Get all active constraints (budgets, limits) for a user."""
        return await self.get_memories(user_id, MemoryType.CONSTRAINT)
    
    async def get_user_habits(self, user_id: str) -> List[Dict]:
        """Get all inferred habits for a user."""
        return await self.get_memories(user_id, MemoryType.HABIT)
    
    async def get_user_facts(self, user_id: str) -> List[Dict]:
        """Get all known facts about a user."""
        return await self.get_memories(user_id, MemoryType.FACT)
    
    async def get_budget(self, user_id: str, category: str = None) -> Optional[Dict]:
        """Get budget constraint for a category or overall."""
        key = f"monthly_{category}_budget" if category else "monthly_budget"
        return await self.get_memory_by_key(user_id, key)
    
    async def set_budget(
        self,
        user_id: str,
        amount: float,
        category: str = None,
        currency: str = "INR"
    ) -> str:
        """Set a budget constraint."""
        key = f"monthly_{category}_budget" if category else "monthly_budget"
        value = {"amount": amount, "currency": currency}
        if category:
            value["category"] = category
        
        return await self.upsert_memory(
            user_id,
            MemoryType.CONSTRAINT,
            key,
            value,
            confidence=1.0,
            source=MemorySource.EXPLICIT
        )
    
    # ----------------------------
    # Context Building
    # ----------------------------
    
    async def get_context_for_prompt(self, user_id: str) -> Dict:
        """
        Get all relevant memories for building LLM prompt context.
        Returns structured data that prompt_builder can use.
        """
        preferences = await self.get_user_preferences(user_id)
        constraints = await self.get_user_constraints(user_id)
        habits = await self.get_user_habits(user_id)
        facts = await self.get_user_facts(user_id)
        
        return {
            "preferences": [{"key": p["key"], "value": p["value"]} for p in preferences],
            "constraints": [{"key": c["key"], "value": c["value"]} for c in constraints],
            "habits": [{"key": h["key"], "value": h["value"], "confidence": h["confidence"]} for h in habits],
            "facts": [{"key": f["key"], "value": f["value"]} for f in facts],
        }
