"""
LLM Provider Abstraction
Allows swapping between OpenAI, local models, etc.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from enum import Enum


class LLMProviderType(Enum):
    OPENAI = "openai"
    OPENAI_REALTIME = "openai_realtime"  # For future voice-to-voice
    LOCAL = "local"  # For future local LLM support


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """
        Generate a response from the LLM.
        
        Args:
            messages: Chat messages in OpenAI format
            **kwargs: Provider-specific arguments
            
        Returns:
            Generated response text
        """
        pass
    
    @abstractmethod
    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        response_format: Any,
        **kwargs
    ) -> Any:
        """
        Generate a structured response from the LLM.
        
        Args:
            messages: Chat messages
            response_format: Expected response structure (Pydantic model)
            
        Returns:
            Parsed structured response
        """
        pass
    
    @property
    @abstractmethod
    def provider_type(self) -> LLMProviderType:
        """Return the provider type."""
        pass


class OpenAILLMProvider(LLMProvider):
    """OpenAI GPT provider."""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self._model = model
    
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        import asyncio
        
        def _call():
            response = self._client.chat.completions.create(
                model=kwargs.get("model", self._model),
                messages=messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 500),
            )
            return response.choices[0].message.content
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _call)
    
    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        response_format: Any,
        **kwargs
    ) -> Any:
        import asyncio
        
        def _call():
            response = self._client.beta.chat.completions.parse(
                model=kwargs.get("model", self._model),
                messages=messages,
                temperature=kwargs.get("temperature", 0.3),
                max_tokens=kwargs.get("max_tokens", 100),
                response_format=response_format,
            )
            return response.choices[0].message.parsed
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _call)
    
    @property
    def client(self):
        """Get the underlying OpenAI client for direct access."""
        return self._client
    
    @property
    def provider_type(self) -> LLMProviderType:
        return LLMProviderType.OPENAI


def create_llm_provider(
    provider_type: LLMProviderType = LLMProviderType.OPENAI,
    **kwargs
) -> LLMProvider:
    """
    Factory function to create LLM provider.
    
    Args:
        provider_type: Which LLM provider to use
        **kwargs: Provider-specific arguments
        
    Returns:
        Configured LLM provider instance
    """
    if provider_type == LLMProviderType.OPENAI:
        api_key = kwargs.get("api_key")
        if not api_key:
            raise ValueError("OpenAI API key required")
        model = kwargs.get("model", "gpt-4o-mini")
        return OpenAILLMProvider(api_key=api_key, model=model)
    
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
