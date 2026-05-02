"""
Vosk Speech Recognition Service
Free, offline speech-to-text transcription using Vosk
"""
import os
import json
import numpy as np
from typing import Optional
from pathlib import Path

try:
    import vosk
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    print("[WARNING] Vosk not installed. Install with: pip install vosk")


class VoskTranscriber:
    """
    Vosk-based audio transcriber.
    Provides free, offline speech recognition.
    """
    
    def __init__(self, model_path: Optional[str] = None, sample_rate: int = 16000):
        """
        Initialize Vosk transcriber.
        
        Args:
            model_path: Path to Vosk model directory. If None, uses default path.
            sample_rate: Audio sample rate (default: 16000 Hz)
        """
        if not VOSK_AVAILABLE:
            raise ImportError("Vosk is not installed. Install with: pip install vosk")
        
        self.sample_rate = sample_rate
        
        # Determine model path
        if model_path is None:
            # Try multiple default locations
            base_dir = Path(__file__).parent.parent
            possible_paths = [
                base_dir / "models" / "vosk-model-small-en-us-0.15",
                base_dir / "models" / "vosk-model-en-us-0.22",
                Path("models") / "vosk-model-small-en-us-0.15",
            ]
            
            for path in possible_paths:
                if path.exists():
                    model_path = str(path)
                    break
        
        if model_path is None or not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Vosk model not found. Please download a model from "
                f"https://alphacephei.com/vosk/models and place it in the 'models' directory.\n"
                f"Quick start: Download vosk-model-small-en-us-0.15.zip (~40MB)"
            )
        
        print(f"[VOSK] Loading model from: {model_path}")
        
        try:
            self.model = vosk.Model(model_path)
            self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
            self.recognizer.SetWords(True)  # Enable word timestamps
            print(f"[OK] Vosk model loaded successfully")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Vosk model: {e}")
    
    def transcribe_audio(self, audio_bytes: bytearray) -> Optional[str]:
        """
        Transcribe audio bytes to text.
        
        Args:
            audio_bytes: Raw PCM16 audio data
            
        Returns:
            Transcribed text or None if no speech detected
        """
        try:
            # Convert bytearray to bytes
            audio_data = bytes(audio_bytes)
            
            # Process audio data
            if self.recognizer.AcceptWaveform(audio_data):
                result = json.loads(self.recognizer.Result())
                text = result.get('text', '').strip()
                
                if text:
                    return text
            
            # Get partial result if no final result
            partial_result = json.loads(self.recognizer.PartialResult())
            partial_text = partial_result.get('partial', '').strip()
            
            # Reset recognizer for next utterance
            self.reset()
            
            return partial_text if partial_text else None
            
        except Exception as e:
            print(f"[VOSK ERROR] Transcription error: {e}")
            return None
    
    def transcribe_streaming(self, audio_bytes: bytearray) -> tuple[Optional[str], bool]:
        """
        Transcribe audio in streaming mode (for continuous recognition).
        
        Args:
            audio_bytes: Raw PCM16 audio data chunk
            
        Returns:
            Tuple of (transcribed_text, is_final)
            - transcribed_text: The recognized text or None
            - is_final: True if this is a final result, False for partial
        """
        try:
            audio_data = bytes(audio_bytes)
            
            if self.recognizer.AcceptWaveform(audio_data):
                result = json.loads(self.recognizer.Result())
                text = result.get('text', '').strip()
                return (text if text else None, True)
            else:
                partial_result = json.loads(self.recognizer.PartialResult())
                partial_text = partial_result.get('partial', '').strip()
                return (partial_text if partial_text else None, False)
                
        except Exception as e:
            print(f"[VOSK ERROR] Streaming transcription error: {e}")
            return (None, False)
    
    def reset(self):
        """Reset the recognizer for a new transcription session."""
        try:
            self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
            self.recognizer.SetWords(True)
        except Exception as e:
            print(f"[VOSK ERROR] Reset error: {e}")
    
    def get_final_result(self) -> Optional[str]:
        """Get any remaining final result from the recognizer."""
        try:
            final_result = json.loads(self.recognizer.FinalResult())
            text = final_result.get('text', '').strip()
            self.reset()
            return text if text else None
        except Exception as e:
            print(f"[VOSK ERROR] Final result error: {e}")
            return None


def is_vosk_available() -> bool:
    """Check if Vosk is available and properly configured."""
    return VOSK_AVAILABLE

