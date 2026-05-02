"""
Speech-to-Text Provider Abstraction
Allows swapping between Vosk (free), Deepgram, OpenAI Whisper, etc.
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from enum import Enum


class STTProviderType(Enum):
    VOSK = "vosk"
    OPENAI_WHISPER = "openai_whisper"
    DEEPGRAM = "deepgram"
    GOOGLE = "google"


class STTProvider(ABC):
    """Abstract base class for Speech-to-Text providers."""
    
    @abstractmethod
    def transcribe(self, audio_bytes: bytearray) -> Optional[str]:
        """
        Transcribe audio bytes to text.
        
        Args:
            audio_bytes: Raw PCM16 audio data
            
        Returns:
            Transcribed text or None if no speech detected
        """
        pass
    
    @abstractmethod
    def transcribe_streaming(self, audio_bytes: bytearray) -> Tuple[Optional[str], bool]:
        """
        Transcribe audio in streaming mode.
        
        Args:
            audio_bytes: Raw PCM16 audio data chunk
            
        Returns:
            Tuple of (transcribed_text, is_final)
        """
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """Reset the provider for a new transcription session."""
        pass
    
    @property
    @abstractmethod
    def provider_type(self) -> STTProviderType:
        """Return the provider type."""
        pass


class VoskSTTProvider(STTProvider):
    """Vosk-based STT provider (free, offline)."""
    
    def __init__(self, sample_rate: int = 16000):
        from services.vosk_service import VoskTranscriber, is_vosk_available
        
        if not is_vosk_available():
            raise ImportError("Vosk is not available")
        
        self._transcriber = VoskTranscriber(sample_rate=sample_rate)
    
    def transcribe(self, audio_bytes: bytearray) -> Optional[str]:
        return self._transcriber.transcribe_audio(audio_bytes)
    
    def transcribe_streaming(self, audio_bytes: bytearray) -> Tuple[Optional[str], bool]:
        return self._transcriber.transcribe_streaming(audio_bytes)
    
    def reset(self) -> None:
        self._transcriber.reset()
    
    @property
    def provider_type(self) -> STTProviderType:
        return STTProviderType.VOSK


class GoogleSTTProvider(STTProvider):
    """Google Speech Recognition provider (free with limits, online)."""
    
    def __init__(self, sample_rate: int = 16000):
        import speech_recognition as sr
        self._recognizer = sr.Recognizer()
        self._sample_rate = sample_rate
    
    def transcribe(self, audio_bytes: bytearray) -> Optional[str]:
        import tempfile
        import wave
        import os
        import speech_recognition as sr
        
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
                with wave.open(tmp_path, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self._sample_rate)
                    wf.writeframes(audio_bytes)
            
            with sr.AudioFile(tmp_path) as source:
                audio = self._recognizer.record(source)
                return self._recognizer.recognize_google(audio)
        except Exception as e:
            print(f"[GOOGLE STT] Error: {e}")
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
    
    def transcribe_streaming(self, audio_bytes: bytearray) -> Tuple[Optional[str], bool]:
        # Google doesn't support true streaming in free tier
        text = self.transcribe(audio_bytes)
        return (text, True) if text else (None, False)
    
    def reset(self) -> None:
        pass  # No state to reset
    
    @property
    def provider_type(self) -> STTProviderType:
        return STTProviderType.GOOGLE


# Placeholder for future OpenAI Realtime integration
class OpenAIRealtimeSTTProvider(STTProvider):
    """
    OpenAI Realtime API provider (premium, lowest latency).
    TODO: Implement when user upgrades to paid plan.
    """
    
    def __init__(self, api_key: str, sample_rate: int = 16000):
        self._api_key = api_key
        self._sample_rate = sample_rate
        # Will use WebRTC for actual implementation
        raise NotImplementedError(
            "OpenAI Realtime API integration coming soon. "
            "This will provide ChatGPT-like voice experience."
        )
    
    def transcribe(self, audio_bytes: bytearray) -> Optional[str]:
        raise NotImplementedError()
    
    def transcribe_streaming(self, audio_bytes: bytearray) -> Tuple[Optional[str], bool]:
        raise NotImplementedError()
    
    def reset(self) -> None:
        raise NotImplementedError()
    
    @property
    def provider_type(self) -> STTProviderType:
        return STTProviderType.OPENAI_WHISPER


def create_stt_provider(
    provider_type: STTProviderType = STTProviderType.VOSK,
    sample_rate: int = 16000,
    **kwargs
) -> STTProvider:
    """
    Factory function to create STT provider based on type.
    
    Args:
        provider_type: Which STT provider to use
        sample_rate: Audio sample rate
        **kwargs: Provider-specific arguments
        
    Returns:
        Configured STT provider instance
    """
    if provider_type == STTProviderType.VOSK:
        try:
            return VoskSTTProvider(sample_rate=sample_rate)
        except ImportError:
            print("[WARNING] Vosk not available, falling back to Google")
            return GoogleSTTProvider(sample_rate=sample_rate)
    
    elif provider_type == STTProviderType.GOOGLE:
        return GoogleSTTProvider(sample_rate=sample_rate)
    
    elif provider_type == STTProviderType.OPENAI_WHISPER:
        api_key = kwargs.get("api_key")
        if not api_key:
            raise ValueError("OpenAI API key required for OpenAI provider")
        return OpenAIRealtimeSTTProvider(api_key=api_key, sample_rate=sample_rate)
    
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
