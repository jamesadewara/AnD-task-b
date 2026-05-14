from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class ReasoningStep(BaseModel):
    step: str = Field(..., example="filter")
    action: str = Field(..., example="Intelligent candidate retrieval from the SEED_ITEMS pool")
    output: str = Field(..., example="15 items within budget and category affinity found.")

class RecommendationItem(BaseModel):
    item_id: str = Field(..., example="sf_001")
    name: str = Field(..., example="Party Jollof Rice")
    category: str = Field(..., example="street_food")
    price_naira: float = Field(..., example=2500)
    rating: float = Field(..., example=4.8)
    location: str = Field(..., example="Lagos")
    tags: List[str] = Field(..., example=["spicy", "authentic"])
    score: float = Field(0.0, example=12.5)
    reason: str = Field("", example="Perfect match for your budget and preference for spicy food.")

class RecommendationResponse(BaseModel):
    recommendations: List[RecommendationItem] = Field(..., description="Top 10 recommended items")
    reasoning_chain: List[ReasoningStep] = Field(default_factory=list, description="Chain of Thought reasoning steps")
    confidence: float = Field(..., example=0.85)
    cold_start_used: bool = Field(..., example=False)
    cross_domain: bool = Field(..., example=True)

class ErrorResponse(BaseModel):
    detail: str = Field(..., example="An error occurred processing your request.")
