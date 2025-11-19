"""Voice message handling with OpenAI Whisper and TTS."""
import logging
import tempfile
import os
from pathlib import Path
from typing import Optional
import httpx
from telegram import Update, File

from src.config import OPENAI_API_KEY, OPENAI_BASE_URL

logger = logging.getLogger(__name__)


class VoiceHandler:
    """Handle voice message transcription and text-to-speech."""
    
    def __init__(self):
        self.api_key = OPENAI_API_KEY
        self.base_url = OPENAI_BASE_URL.rstrip('/v1')  # Remove /v1 if present
        
        if not self.api_key:
            logger.warning("OpenAI API key not set. Voice features will be disabled.")
    
    async def transcribe_voice(self, voice_file: File) -> Optional[str]:
        """
        Transcribe a voice message using OpenAI Whisper.
        
        Args:
            voice_file: Telegram voice file object
            
        Returns:
            Transcribed text or None on failure
        """
        if not self.api_key:
            logger.error("Cannot transcribe: OpenAI API key not set")
            return None
        
        # Download voice file to temporary location
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
            temp_path = temp_file.name
            
        try:
            # Download the voice file
            await voice_file.download_to_drive(temp_path)
            logger.info(f"Downloaded voice file to {temp_path}")
            
            # Transcribe using Whisper API
            async with httpx.AsyncClient(timeout=30.0) as client:
                with open(temp_path, 'rb') as audio_file:
                    files = {
                        'file': ('audio.ogg', audio_file, 'audio/ogg'),
                    }
                    data = {
                        'model': 'whisper-1',
                        'language': 'es',  # Spanish
                    }
                    
                    response = await client.post(
                        f"{self.base_url}/v1/audio/transcriptions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                        },
                        files=files,
                        data=data,
                    )
                    
                    response.raise_for_status()
                    result = response.json()
                    transcribed_text = result.get('text', '').strip()
                    
                    logger.info(f"Transcription: {transcribed_text}")
                    return transcribed_text
                    
        except Exception as e:
            logger.error(f"Error transcribing voice: {e}", exc_info=True)
            return None
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Could not delete temp file {temp_path}: {e}")
    
    async def text_to_speech(self, text: str, voice: str = "nova") -> Optional[bytes]:
        """
        Convert text to speech using OpenAI TTS.
        
        Args:
            text: Text to convert to speech
            voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer)
            
        Returns:
            Audio data as bytes or None on failure
        """
        if not self.api_key:
            logger.error("Cannot generate speech: OpenAI API key not set")
            return None
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "tts-1",
                        "input": text,
                        "voice": voice,
                        "response_format": "mp3",
                    },
                )
                
                response.raise_for_status()
                audio_data = response.content
                
                logger.info(f"Generated TTS audio ({len(audio_data)} bytes)")
                return audio_data
                
        except Exception as e:
            logger.error(f"Error generating speech: {e}", exc_info=True)
            return None


# Global instance
voice_handler = VoiceHandler()

