import logging
from typing import Any, Dict, List
from openrouter import OpenRouter
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        self.primary_model = settings.LITELLM_MODEL_PRIMARY
        self.fallback_models = settings.LITELLM_FALLBACK_MODELS
        self.api_key = settings.OPENROUTER_API_KEY

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def _call_llm(self, model: str, messages: List[Dict[str, str]], temperature: float, max_tokens: int) -> str:
        """Internal helper using the official OpenRouter SDK."""
        logger.info(f"LLM Call (Task B - SDK): {model}")
        
        async with OpenRouter(api_key=self.api_key) as client:
            response = await client.chat.send_async(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content or ""

    async def get_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 500,
    ) -> str:
        """Get completion with multi-model fallback and rotation logic."""
        models_to_try = [self.primary_model] + self.fallback_models
        
        last_error = None
        for model in models_to_try:
            try:
                return await self._call_llm(model, messages, temperature, max_tokens)
            except Exception as e:
                last_error = e
                logger.warning(f"LLM attempt failed for {model}: {e}. Rotating to next model...")
                continue
        
        logger.error(f"All LLM attempts failed (Task B). Last error: {last_error}")
        return "ERROR: Unable to generate reasoning after multiple attempts."

llm_service = LLMService()
