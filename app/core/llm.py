import logging
import os
import json
import time
from filelock import FileLock
from typing import Any, Dict, List, Optional
from openrouter import OpenRouter
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import settings

logger = logging.getLogger(__name__)

class KeyRotationManager:
    def __init__(self, api_keys: list[str], cache_file: str = ".cache/rate.dt"):
        self.api_keys = api_keys
        self.cache_file = cache_file
        self.cache_dir = os.path.dirname(cache_file)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._load_cache()

    def _load_cache(self):
        """Load the rate limit cache from disk."""
        if not os.path.exists(self.cache_file):
            self.cache = {
                "keys": [
                    {
                        "index": i,
                        "blocked_at": None,
                        "cooldown_seconds": 60,
                        "fail_count": 0,
                        "last_success": int(time.time()),
                        "dead": False
                    } for i in range(len(self.api_keys))
                ],
                "last_updated": int(time.time())
            }
            self._save_cache()
        else:
            try:
                with open(self.cache_file, 'r') as f:
                    self.cache = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache file {self.cache_file}: {e}. Resetting cache.")
                self._load_cache()  # Recreate cache

    def _save_cache(self):
        """Save the rate limit cache to disk with file locking."""
        try:
            lock = FileLock(self.cache_file + ".lock", timeout=10)
            with lock:
                with open(self.cache_file, 'w') as f:
                    json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache file {self.cache_file}: {e}")

    def get_next_key(self) -> Optional[str]:
        """Get the next available API key, skipping blocked/dead keys."""
        now = int(time.time())
        available_keys = []

        for key_data in self.cache["keys"]:
            if key_data["dead"]:
                continue
            if key_data["blocked_at"] is not None:
                if now - key_data["blocked_at"] < key_data["cooldown_seconds"]:
                    continue
            available_keys.append(key_data)

        if available_keys:
            # Return the key with the lowest fail_count, then by index
            available_keys.sort(key=lambda x: (x["fail_count"], x["index"]))
            key_index = available_keys[0]["index"]
            return self.api_keys[key_index]

        # All keys are blocked - pick the one that will recover soonest
        if self.cache["keys"]:
            recoverable_keys = [k for k in self.cache["keys"] if not k["dead"]]
            if recoverable_keys:
                recoverable_keys.sort(key=lambda x: x["blocked_at"] or 0)
                key_index = recoverable_keys[0]["index"]
                return self.api_keys[key_index]

        return None

    def mark_failed(self, key_index: int, error: Exception = None):
        """Mark a key as failed, potentially marking it as dead."""
        now = int(time.time())
        key_data = self.cache["keys"][key_index]
        key_data["blocked_at"] = now
        key_data["fail_count"] += 1

        # Mark as dead if too many failures or auth error
        error_str = str(error).lower() if error else ""
        if key_data["fail_count"] >= 5 or any(code in error_str for code in ["401", "403", "unauthorized", "forbidden"]):
            key_data["dead"] = True
            logger.warning(f"Key {key_index} marked as dead due to repeated failures or auth error")

        self.cache["last_updated"] = now
        self._save_cache()

    def mark_success(self, key_index: int):
        """Mark a key as successful, resetting its failure state."""
        now = int(time.time())
        key_data = self.cache["keys"][key_index]
        key_data["blocked_at"] = None
        key_data["fail_count"] = 0
        key_data["last_success"] = now
        self.cache["last_updated"] = now
        self._save_cache()

class LLMService:
    def __init__(self):
        self.primary_model = settings.MODEL_PRIMARY
        self.fallback_models = settings.FALLBACK_MODELS
        
        # Initialize key rotation manager
        self.key_manager = KeyRotationManager(settings.OPENROUTER_API_KEYS)
        
        if not settings.OPENROUTER_API_KEYS:
            logger.error("❌ No OpenRouter API keys found in Settings!")

    @retry(
        stop=stop_after_attempt(1),
        wait=wait_exponential(multiplier=1, min=1, max=2),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def _call_llm(self, model: str, messages: List[Dict[str, str]], temperature: float, max_tokens: int, api_key: str) -> str:
        """Internal helper using the official OpenRouter SDK with a strict timeout."""
        import asyncio
        logger.info(f"LLM Call (Task B - SDK): {model}")
        
        async def _do_call():
            async with OpenRouter(api_key=api_key) as client:
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
        for model in models_to_try:
            while True:
                api_key = self.key_manager.get_next_key()
                if not api_key:
                    logger.error(f"No available API keys for model {model}")
                    break
                    
                key_index = self.key_manager.api_keys.index(api_key)
                try:
                    logger.info(f"LLM attempt: model={model}, key_index={key_index}")
                    result = await self._call_llm(model, messages, temperature, max_tokens, api_key=api_key)
                    self.key_manager.mark_success(key_index)
                    return result
                except Exception as e:
                    last_error = e
                    self.key_manager.mark_failed(key_index, e)
                    err_msg = str(e).lower()
                    
                    # If the error is clearly model-related (congestion/capacity), switch models immediately
                    if any(m in err_msg for m in ["congested", "overloaded", "503", "capacity", "no provider", "free-models-per-day"]):
                        logger.warning(f"Model {model} appears congested or limit reached: {e}. Switching model...")
                        break
                    
                    logger.warning(f"LLM attempt failed for {model} with key {key_index}: {e}. Trying next key...")
                    continue
            
            # If we are here, all keys failed for this model (or it was congested)
            if on_fallback and model != models_to_try[-1]:
                next_model = models_to_try[models_to_try.index(model) + 1]
                await on_fallback(model, next_model, str(last_error))
        
        logger.error(f"All LLM attempts failed (Task B). Last error: {last_error}")
        return f"ERROR: Unable to generate reasoning after multiple attempts. Last error: {str(last_error)}"

llm_service = LLMService()
