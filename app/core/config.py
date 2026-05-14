from typing import List, Dict, Any, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "AnD-ai-recommendation-engine"
    DEBUG: bool = True
    CORS_ALLOWED_ORIGINS: Union[list[str], str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        return ["http://localhost:3000"]

    OPENROUTER_API_KEYS: list[str] = Field(
        ...,
        description="Comma-separated list of OpenRouter API Keys"
    )

    @field_validator("OPENROUTER_API_KEYS", mode="before")
    @classmethod
    def assemble_api_keys(cls, v: Any) -> list[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        return []
    MODEL_PRIMARY: str = "z-ai/glm-4.5-air:free"
    FALLBACK_MODELS: list[str] = [
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "google/gemma-4-31b-it:free",
        "z-ai/glm-4.5-air:free"
    ]

    MAX_TOKENS: int = 1024

    HF_TOKEN: str = Field(
        default="",
        description="Hugging Face API Token"
    )

    DEFAULT_USER_BUDGET: float = 0

    # Occasion mapping for keyword-based boosting
    OCCASION_KEYWORDS: Dict[str, List[str]] = {
        "date night": ["romance", "intimate", "exclusive"],
        "business dinner": ["fine dining", "prestige", "exclusive"],
        "party": ["spicy", "high-energy", "celebration"],
        "movie night": ["nollywood", "comedy", "family"],
        "quick dinner": ["quick", "fast", "value"],
        "breakfast": ["breakfast", "morning", "light"]
    }

    # Archetype Profiles for Probabilistic Cold-Start
    # Each profile defines 'ideal' values and 'weights' for different features
    ARCHETYPE_PROFILES: Dict[str, Dict[str, Any]] = {
        "haggler": {
            "ideal_price_ratio": 0.4,  # Wants items at 40% of budget
            "min_rating": 3.0,
            "boost_keywords": ["budget-friendly", "value", "deal", "cheap"],
            "sensitivity": 1.5
        },
        "big woman": {
            "ideal_price_ratio": 0.9,  # Wants items near budget limit (status)
            "min_rating": 4.5,
            "boost_keywords": ["premium", "luxury", "high-end", "exclusive"],
            "sensitivity": 2.0
        },
        "community": {
            "ideal_price_ratio": 0.6,
            "min_rating": 4.6,        # Highly driven by others' ratings
            "boost_keywords": ["popular", "classic", "trusted", "trending"],
            "sensitivity": 1.2
        },
        "default": {
            "ideal_price_ratio": 0.7,
            "min_rating": 4.0,
            "boost_keywords": ["quality", "reliable"],
            "sensitivity": 1.0
        }
    }

    # Time of day based tag preferences
    TIME_OF_DAY_PREFERENCES: Dict[str, List[str]] = {
        "morning": ["breakfast"],
        "night": ["nollywood", "movie", "dinner"]
    }

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )

settings = Settings()
