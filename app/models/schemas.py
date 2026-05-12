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
    budget: float = 10000.0
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

class RecommendationItem(BaseModel):
    item_id: str
    name: str
    category: str
    price_naira: float
    rating: float
    location: str
    tags: List[str]
    score: float = 0.0
    reason: str = ""

class ReasoningStep(BaseModel):
    step: str
    action: str
    output: str

class RecommendationResponse(BaseModel):
    recommendations: List[RecommendationItem]
    reasoning_chain: List[ReasoningStep]
    confidence: float
    cold_start_used: bool
    cross_domain: bool
