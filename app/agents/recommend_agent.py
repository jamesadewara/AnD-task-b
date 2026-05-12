import json
import re
import os
import traceback
from typing import List, Dict, Any
from loguru import logger
from app.core.llm import llm_service
from app.core.retriever import Retriever
from app.core.ranker import Ranker
from app.core.cold_start import ColdStart
from app.models.schemas import UserPersona, Context

def load_prompt(filename: str) -> str:
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load prompt {filename}: {e}")
        return ""

class RecommendAgent:
    def __init__(self):
        self.retriever = Retriever()
        self.ranker = Ranker()
        self.cold_start = ColdStart()

    async def cot_reason(self, user_persona: UserPersona, context: Context, candidates: List[Dict]) -> Dict[str, Any]:
        """Chain-of-thought reasoning with strict validation and fallback."""
        logger.info(f"[RecommendAgent] Step 3: Generating reasoning plan for {user_persona.name}")
        principles = load_prompt("behavioral_principles.txt")
        
        prompt = f"""
{principles}

Analyze this user for recommendations. Output ONLY valid JSON.

User: {user_persona.name}
Archetype: {user_persona.archetype}
Budget: ₦{user_persona.budget}
Interests: {user_persona.interests}
Occasion: {context.occasion}

Output ONLY this exact JSON format (no markdown, no explanation):
{{
    "preferred_categories": ["cat1", "cat2"],
    "priorities": ["tag1", "tag2"],
    "reasoning": "explanation"
}}
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text = await llm_service.get_completion(messages, temperature=0.3, max_tokens=250)
        
        result = {
            "preferred_categories": [i for i in (user_persona.interests or [])[:2] if i],
            "priorities": ["authentic", "value"],
            "reasoning": f"Fallback: using interests for {user_persona.name}."
        }
        
        try:
            text = response_text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                parsed = json.loads(text[start:end+1])
                pc = parsed.get("preferred_categories", [])
                if isinstance(pc, list) and all(isinstance(x, str) for x in pc):
                    result["preferred_categories"] = pc
                pr = parsed.get("priorities", [])
                if isinstance(pr, list) and all(isinstance(x, str) for x in pr):
                    result["priorities"] = pr
                elif isinstance(pr, dict):
                    result["priorities"] = list(pr.keys()) if pr else ["authentic"]
                r = parsed.get("reasoning", "")
                if isinstance(r, str):
                    result["reasoning"] = r
        except Exception as e:
            logger.warning(f"CoT parsing failed: {e}. Response was: {response_text[:200]}")
        
        return result

    async def recommend(self, user_persona: UserPersona, context: Context) -> Dict[str, Any]:
        """Agentic workflow that builds a visible reasoning chain with step-by-step logging."""
        reasoning_chain = []
        
        try:
            # Step 1: RETRIEVE
            logger.info(f"[RecommendAgent] Step 1: Retrieving candidates for {user_persona.name}")
            candidates = self.retriever.filter(user_persona, context)
            reasoning_chain.append({
                "step": "retrieve",
                "action": "Filtering seed pool",
                "output": f"Retrieved {len(candidates)} candidates matching interests and budget."
            })
            
            # Step 2: CONVERSATION ANALYSIS
            logger.info(f"[RecommendAgent] Step 2: Analyzing conversation history for rejections")
            if context.conversation_history:
                user_msgs = [turn.get("message", "").lower() for turn in context.conversation_history 
                             if turn.get("role") == "user"]
                
                max_price = None
                for msg in user_msgs:
                    match = re.search(r'not more than ₦?(\d{1,7})', msg)
                    if match:
                        max_price = float(match.group(1))
                
                if max_price:
                    candidates = [c for c in candidates if c["price_naira"] <= max_price]
                    reasoning_chain.append({
                        "step": "filter",
                        "action": "Budget extraction",
                        "output": f"Extracted budget limit of ₦{max_price} from conversation history."
                    })
                
                rejections = {
                    "expensive": lambda i: i["price_naira"] > user_persona.budget * 0.8,
                    "far": lambda i: context.location and context.location.lower() not in i["location"].lower(),
                    "spicy": lambda i: "spicy" not in i["tags"],
                }
                applied_filters = []
                for signal, check in rejections.items():
                    if any(signal in m for m in user_msgs):
                        original_count = len(candidates)
                        candidates = [c for c in candidates if not check(c)]
                        if len(candidates) < original_count:
                            applied_filters.append(signal)
                
                if applied_filters:
                    reasoning_chain.append({
                        "step": "filter",
                        "action": "Rejection analysis",
                        "output": f"Removed candidates matching rejection signals: {applied_filters}."
                    })

            # Step 3: COT_REASON (Logging inside the method)
            analysis = await self.cot_reason(user_persona, context, candidates)
            reasoning_chain.append({
                "step": "reason",
                "action": "Chain-of-thought analysis",
                "output": analysis.get("reasoning", "Analyzing preferences")
            })
            
            # Step 4: RANK
            logger.info(f"[RecommendAgent] Step 4: Scoring and ranking candidates")
            ranked = self.ranker.score(candidates, analysis, user_persona, context)
            reasoning_chain.append({
                "step": "rank",
                "action": "Scoring candidates",
                "output": f"Ranked {len(ranked)} items by price, location, and occasion."
            })
            
            # Step 5: COLD_START
            cold_start_used = len(user_persona.past_reviews) == 0
            if cold_start_used:
                logger.info(f"[RecommendAgent] Step 5: Applying cold-start archetype boost")
                ranked = self.cold_start.adjust(ranked, user_persona)
                reasoning_chain.append({
                    "step": "cold_start",
                    "action": "Demographic inference",
                    "output": f"Boosted scores for {user_persona.archetype} archetype"
                })
                
            # Step 6: VALIDATE
            logger.info(f"[RecommendAgent] Step 6: Validating results and cross-domain diversity")
            categories = set(r["category"] for r in ranked[:10])
            cross_domain = len(categories) > 1
            reasoning_chain.append({
                "step": "validate",
                "action": "Cross-domain check",
                "output": f"Cross-domain: {cross_domain}, categories: {list(categories)}"
            })
            
            final_recs = []
            for r in ranked[:10]:
                reason = f"Aligned with your {user_persona.archetype} persona"
                if any(p.lower() in r["name"].lower() for p in analysis.get("priorities", [])):
                    reason = "Highly relevant to your specific priorities and occasion."
                
                clean_item = {k: v for k, v in r.items() if not k.startswith("_")}
                clean_item["reason"] = reason
                final_recs.append(clean_item)

            return {
                "recommendations": final_recs,
                "reasoning_chain": reasoning_chain,
                "confidence": 0.85 if not cold_start_used else 0.70,
                "cold_start_used": cold_start_used,
                "cross_domain": cross_domain
            }
        except Exception as e:
            logger.error(f"RECOMMENDATION ERROR: {str(e)}")
            logger.error(traceback.format_exc())
            if not reasoning_chain:
                reasoning_chain.append({"step": "error", "action": "Catch-all", "output": str(e)})
            raise
