from fastapi import APIRouter, HTTPException
from loguru import logger
import traceback
from app.models.schemas import RecommendRequest, RecommendationResponse, ReasoningStep
from app.agents.recommend_agent import RecommendAgent

router = APIRouter()

@router.post(
    "/",
    response_model=RecommendationResponse,
    summary="Get personalized recommendations (Stateless)",
    description="Agentic recommendation engine using CoT and Nigerian cultural grounding."
)
async def get_recommendations(request: RecommendRequest):
    logger.info(f"Received recommendation request for user: {request.user_persona.name}")
    
    try:
        agent = RecommendAgent()
        result = await agent.recommend(request.user_persona, request.context)
        
        # DEBUG: Log what the agent returned
        logger.info(f"Agent returned keys: {result.keys()}")
        logger.info(f"Reasoning chain length: {len(result.get('reasoning_chain', []))}")
        
        # MUST pass reasoning_chain to response model explicitly for diagnostic clarity
        return RecommendationResponse(
            recommendations=result["recommendations"],
            reasoning_chain=[ReasoningStep(**step) for step in result["reasoning_chain"]],
            confidence=result["confidence"],
            cold_start_used=result["cold_start_used"],
            cross_domain=result["cross_domain"]
        )
        
    except Exception as e:
        logger.error(f"Recommendation failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))