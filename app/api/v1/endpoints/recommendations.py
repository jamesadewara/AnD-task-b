from fastapi import APIRouter, HTTPException
from fastapi.requests import Request
from loguru import logger
import traceback
from app.schemas.responses import RecommendationResponse, ReasoningStep
from fastapi.responses import StreamingResponse
from app.agents.recommend_agent import RecommendAgent

router = APIRouter()

import json

@router.post(
    "/",
    response_model=RecommendationResponse,
    summary="Get personalized recommendations (Stateless)",
    description="Accepts any input format/prompt and returns structured recommendation response."
)
async def get_recommendations(request: Request):
    """Accept any input format and return structured RecommendationResponse."""
    try:
        body = await request.json()
    except Exception as e:
        # If JSON parse fails, treat entire body as a message
        body = await request.body()
        body = {"message": body.decode() if isinstance(body, bytes) else str(body)}
    
    logger.info(f"Received recommendation request from input: {str(body)[:100]}...")
    
    try:
        agent = RecommendAgent()
        result = await agent.recommend_flexible(body)
        
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

@router.post("/stream")
async def stream_recommendations(request: Request):
    """Stream reasoning steps and final recommendation result."""
    try:
        body = await request.json()
    except:
        body = await request.body()
        body = {"message": body.decode() if isinstance(body, bytes) else str(body)}

    agent = RecommendAgent()
    
    async def event_generator():
        try:
            from app.models.schemas import UserPersona, Context
            
            persona_data = body.get("user_persona", {})
            context_data = body.get("context", {})
            
            # Ensure required fields for pydantic models
            persona = UserPersona(**persona_data)
            context = Context(**context_data)
            
            async for event in agent.recommend_streaming(persona, context):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Stream failed: {e}")
            logger.error(traceback.format_exc())
            yield f"data: {json.dumps({'event': 'error', 'data': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")