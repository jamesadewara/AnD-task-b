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
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def _call_llm(self, model: str, messages: List[Dict[str, str]], temperature: float, max_tokens: int) -> str:
        """Internal helper using the official OpenRouter SDK with a strict timeout."""
        import asyncio
        logger.info(f"LLM Call (Task B - SDK): {model}")
        
        async def _do_call():
            async with OpenRouter(api_key=self.api_key) as client:
                response = await client.chat.send_async(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response.choices[0].message.content or ""

        try:
            return await asyncio.wait_for(_do_call(), timeout=20.0)
        except asyncio.TimeoutError:
            logger.error(f"LLM Timeout for model {model} (Task B)")
            raise Exception(f"Timeout (20s) exceeded for {model}")

    async def get_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 500,
        on_fallback = None
    ) -> str:
        """Get completion with multi-model fallback and rotation logic."""
        models_to_try = [self.primary_model] + self.fallback_models
        
        last_error = None
        for i, model in enumerate(models_to_try):
            try:
                return await self._call_llm(model, messages, temperature, max_tokens)
            except Exception as e:
                last_error = e
                logger.warning(f"LLM attempt failed for {model}: {e}.")
                
                if i < len(models_to_try) - 1 and on_fallback:
                    next_model = models_to_try[i+1]
                    await on_fallback(model, next_model, str(e))
                continue
        
        logger.error(f"All LLM attempts failed (Task B). Last error: {last_error}")
        return f"ERROR: Unable to generate reasoning after multiple attempts. Last error: {str(last_error)}"

llm_service = LLMService()

llm_service = LLMService()
