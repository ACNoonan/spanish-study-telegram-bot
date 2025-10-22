"""LLM client with OpenRouter integration and retry logic."""
import asyncio
import logging
from typing import Optional
import httpx
from src.config import (
    LLM_API_KEY,
    LLM_MODEL,
    LLM_BASE_URL,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for interacting with LLM via OpenRouter API."""
    
    def __init__(self):
        self.api_key = LLM_API_KEY
        self.model = LLM_MODEL
        self.base_url = LLM_BASE_URL
        self.max_retries = LLM_MAX_RETRIES
        self.timeout = LLM_TIMEOUT
        
        if not self.api_key:
            logger.warning("OpenRouter API key not set. LLM features will be limited.")
    
    async def generate_response(
        self,
        messages: list[dict],
        temperature: float = LLM_TEMPERATURE,
        max_tokens: int = LLM_MAX_TOKENS,
    ) -> Optional[str]:
        """
        Generate a response from the LLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text response or None on failure
        """
        if not self.api_key:
            return "Lo siento, cariño, pero no puedo conectarme ahora. ¿Podemos hablar más tarde? 💔"
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                        },
                    )
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # Log token usage for cost tracking
                    usage = data.get("usage", {})
                    logger.info(
                        f"LLM tokens used - Prompt: {usage.get('prompt_tokens', 0)}, "
                        f"Completion: {usage.get('completion_tokens', 0)}, "
                        f"Total: {usage.get('total_tokens', 0)}"
                    )
                    
                    return data["choices"][0]["message"]["content"]
                    
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limit
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Rate limited. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"HTTP error: {e}")
                    if attempt == self.max_retries - 1:
                        return None
                        
            except httpx.TimeoutException:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{self.max_retries})")
                if attempt == self.max_retries - 1:
                    return "Perdona, cariño... estoy teniendo problemas de conexión. ¿Puedes repetir eso? 😅"
                    
            except Exception as e:
                logger.error(f"Unexpected error in LLM client: {e}")
                if attempt == self.max_retries - 1:
                    return None
                    
        return None


# Global instance
llm_client = LLMClient()

