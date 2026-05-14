from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class UserPersona(BaseModel):
    name: str
    location: Optional[str] = "Nigeria"
    archetype: str = "default_consumer"
    interests: List[str] = []
    traits: List[str] = []
    tone: str = "neutral"
    style_sample: Optional[str] = None
    nigerian_context: bool = True
    budget: float = 0.0
    price_sensitivity: str = "medium"
    past_reviews: List[Dict] = []

class Context(BaseModel):
    location: Optional[str] = None
    time_of_day: Optional[str] = None
    occasion: Optional[str] = None
    conversation_history: List[Dict] = []

class RecommendRequest(BaseModel):
    user_persona: UserPersona
    context: Context
