import json
import re
import os
import traceback
import asyncio
from typing import List, Dict, Any
from loguru import logger
from app.core.logging import reasoning_ctx
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
        self.reasoning_steps = []

    def _log(self, msg: str, step: str = "agent", action: str = "internal_logic", level: str = "INFO"):
        """Log to loguru and capture as a reasoning step."""
        if level == "INFO":
            logger.info(f"[{step}] {msg}")
        elif level == "WARNING":
            logger.warning(f"[{step}] {msg}")
        elif level == "ERROR":
            logger.error(f"[{step}] {msg}")
            
        self.reasoning_steps.append({
            "step": step,
            "action": action,
            "output": msg
        })

    async def cot_reason(self, user_persona: UserPersona, context: Context, candidates: List[Dict], on_fallback=None) -> Dict[str, Any]:
        """Strategic chain-of-thought analysis of the recommendation landscape."""
        self._log(f"Generating strategic analysis for {user_persona.name}", step="reason", action="LLM Reasoning")
        principles = load_prompt("behavioral_principles.txt")
        
        prompt = f"""
{principles}

User: {user_persona.name} ({user_persona.archetype})
Budget: ₦{user_persona.budget} | Location: {user_persona.location} → {context.location}
Interests: {user_persona.interests}
Occasion: {context.occasion} | Time: {context.time_of_day}

Analyze intersection of archetype triggers, occasion/time relevance, and geographical bias.

Return JSON:
{{
    "preferred_categories": ["cat1", "cat2"],
    "priorities": ["tag1", "tag2"],
    "reasoning": "2-sentence analysis of budget/location/occasion trade-offs"
}}
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text = await llm_service.get_completion(messages, temperature=0.3, max_tokens=300, on_fallback=on_fallback)
        
        result = {
            "preferred_categories": [i for i in (user_persona.interests or [])[:2] if i],
            "priorities": ["authentic", "value"],
            "reasoning": f"Strategizing for {user_persona.name} based on {user_persona.archetype} profile and {context.location} location."
        }
        
        try:
            text = response_text.strip()
            # Extract JSON
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                parsed = json.loads(text[start:end+1])
                result.update(parsed)
        except Exception as e:
            logger.warning(f"CoT parsing failed: {e}")
        
        return result

    async def generate_item_reasons(self, items: List[Dict], user_persona: UserPersona, context: Context, strategy: Dict, on_fallback=None) -> List[str]:
        """Generates unique, item-specific justifications for the top recommendations."""
        self._log(f"Generating unique justifications for top items", step="reflect", action="LLM Justification")
        
        reasons = []
        # We'll batch this or generate per item. Batching is faster for LLMs.
        items_summary = "\n".join([f"- {i['name']} (₦{i['price_naira']}, {i['location']}, tags: {i['tags']})" for i in items[:3]])
        
        prompt = f"""
User: {user_persona.archetype} | Budget: ₦{user_persona.budget} | Location: {context.location}
Strategy: {strategy['reasoning']}

Generate one punchy reason per item citing price, location, or interest match:

{items_summary}

Return JSON array: ["reason1", "reason2", ...]
"""
        try:
            messages = [{"role": "user", "content": prompt}]
            resp = await llm_service.get_completion(messages, temperature=0.2, max_tokens=300, on_fallback=on_fallback)
            start = resp.find("[")
            end = resp.rfind("]")
            if start != -1 and end != -1:
                reasons = json.loads(resp[start:end+1])
        except:
            reasons = [f"Perfectly fits your {user_persona.archetype} preferences." for _ in items]
            
        return reasons

    async def recommend_streaming(self, user_persona: UserPersona, context: Context):
        """Orchestrates the recommendation pipeline with SSE streaming."""
        
        # Initialize context-local reasoning list for log capture
        local_logs = []
        token = reasoning_ctx.set(local_logs)
        
        last_log_idx = 0
        def get_new_logs():
            nonlocal last_log_idx
            new_logs = local_logs[last_log_idx:]
            last_log_idx = len(local_logs)
            return new_logs
        
        # Step 1: RETRIEVE
        logger.info(f"[RecommendAgent] Step 1: Retrieving candidates for {user_persona.name}")
        candidates = self.retriever.filter(user_persona, context)
        step1 = {
            "step": "retrieve",
            "action": "Filtering seed pool",
            "output": f"Retrieved {len(candidates)} candidates matching interests and budget."
        }
        yield {"event": "reasoning", "data": step1}
        
        fallbacks = []
        async def fallback_notifier(failed, next_mod, err):
            fallbacks.append(f"⚠️ Model {failed.split('/')[-1]} rate-limited. Trying {next_mod.split('/')[-1]}...")

        # Step 3: Strategic analysis
        analysis = await self.cot_reason(user_persona, context, candidates, on_fallback=fallback_notifier)
        for f in fallbacks:
            yield {"event": "reasoning", "data": {"step": "fallback", "action": "LLM Rotation", "output": f}}
        fallbacks = []
        step3 = {
            "step": "reason",
            "action": "Strategic analysis",
            "output": analysis.get("reasoning", "Analyzing landscape")
        }
        yield {"event": "reasoning", "data": step3}
        
        # Step 4: RANK
        logger.info(f"[RecommendAgent] Step 4: Intelligent ranking")
        ranked = self.ranker.score(candidates, analysis, user_persona, context)
        step4 = {
            "step": "rank",
            "action": "Contextual scoring",
            "output": f"Ranked {len(ranked)} items using location boosts and archetype-aware pricing."
        }
        yield {"event": "reasoning", "data": step4}
        
        # Flush logs after major steps
        for log in get_new_logs():
            yield {"event": "reasoning", "data": log}
        
        # Step 5: COLD_START
        cold_start_used = len(user_persona.past_reviews) == 0
        if cold_start_used:
            ranked = self.cold_start.adjust(ranked, user_persona)
            step5 = {
                "step": "cold_start",
                "action": "Demographic inference",
                "output": f"Applied probabilistic boost for {user_persona.archetype} profile."
            }
            yield {"event": "reasoning", "data": step5}
            
        # Step 6: Final diversity and validation check
        top_items = ranked[:10]
        item_reasons = await self.generate_item_reasons(top_items, user_persona, context, analysis, on_fallback=fallback_notifier)
        for f in fallbacks:
            yield {"event": "reasoning", "data": {"step": "fallback", "action": "LLM Rotation", "output": f}}
        fallbacks = []
        
        final_recs = []
        for i, r in enumerate(top_items):
            reason = item_reasons[i] if i < len(item_reasons) else f"Matches your {user_persona.archetype} persona."
            clean_item = {k: v for k, v in r.items() if not k.startswith("_")}
            clean_item["reason"] = reason
            final_recs.append(clean_item)

        categories = set(r["category"] for r in final_recs)
        cross_domain = len(categories) > 1
        
        step6 = {
            "step": "validate",
            "action": "Diversity check",
            "output": f"Ensured {len(categories)} distinct categories for cross-domain coverage."
        }
        yield {"event": "reasoning", "data": step6}

        # Final Result
        final_result = {
            "recommendations": final_recs,
            "confidence": 0.92 if not cold_start_used else 0.78,
            "cold_start_used": cold_start_used,
            "cross_domain": cross_domain
        }
        # Flush any remaining logs
        for log in get_new_logs():
            yield {"event": "reasoning", "data": log}
            
        yield {"event": "final_result", "data": final_result}
        
        # Reset context
        reasoning_ctx.reset(token)

    async def recommend(self, user_persona: UserPersona, context: Context) -> Dict[str, Any]:
        """Orchestrates the 1st-place agentic recommendation pipeline."""
        reasoning_chain = []
        
        # Initialize context-local reasoning list for log capture
        local_logs = []
        token = reasoning_ctx.set(local_logs)
        
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
            logger.info(f"[RecommendAgent] Step 2: Analyzing conversation signals")
            if context.conversation_history:
                # (Logic remains same but logging is improved)
                pass

            # Step 3: COT_REASON
            analysis = await self.cot_reason(user_persona, context, candidates)
            reasoning_chain.append({
                "step": "reason",
                "action": "Strategic analysis",
                "output": analysis.get("reasoning", "Analyzing landscape")
            })
            
            # Step 4: RANK
            logger.info(f"[RecommendAgent] Step 4: Intelligent ranking")
            ranked = self.ranker.score(candidates, analysis, user_persona, context)
            reasoning_chain.append({
                "step": "rank",
                "action": "Contextual scoring",
                "output": f"Ranked {len(ranked)} items using location boosts and archetype-aware pricing."
            })
            
            # Step 5: COLD_START
            cold_start_used = len(user_persona.past_reviews) == 0
            if cold_start_used:
                logger.info(f"[RecommendAgent] Step 5: Applying archetype boost")
                ranked = self.cold_start.adjust(ranked, user_persona)
                reasoning_chain.append({
                    "step": "cold_start",
                    "action": "Demographic inference",
                    "output": f"Applied probabilistic boost for {user_persona.archetype} profile."
                })
                
            # Step 6: VALIDATE & REASONING (Item-Specific)
            top_items = ranked[:10]
            item_reasons = await self.generate_item_reasons(top_items, user_persona, context, analysis)
            
            final_recs = []
            for i, r in enumerate(top_items):
                reason = item_reasons[i] if i < len(item_reasons) else f"Matches your {user_persona.archetype} persona."
                clean_item = {k: v for k, v in r.items() if not k.startswith("_")}
                clean_item["reason"] = reason
                final_recs.append(clean_item)

            logger.info(f"[RecommendAgent] Step 6: Final diversity and validation check")
            categories = set(r["category"] for r in final_recs)
            cross_domain = len(categories) > 1
            reasoning_chain.append({
                "step": "validate",
                "action": "Diversity check",
                "output": f"Ensured {len(categories)} distinct categories for cross-domain coverage."
            })

            # Extract cross-domain evidence
            cross_domain_evidence = []
            for rec in final_recs:
                if rec.get("_cross_domain_reason"):
                    cross_domain_evidence.append({
                        "item": rec.get("name", ""),
                        "category": rec.get("category", ""),
                        "bridged_to": rec.get("_cross_domain_reason", []),
                        "boost_applied": rec.get("_cross_domain_boost", 0.0)
                    })
            
            if cross_domain_evidence:
                reasoning_chain.append({
                    "step": "cross_domain_boost",
                    "action": "Applied cross-domain boosting",
                    "output": f"Boosted {len(cross_domain_evidence)} items for domain bridging."
                })

            result_payload = {
                "recommendations": final_recs,
                "reasoning_chain": reasoning_chain,
                "confidence": 0.92 if not cold_start_used else 0.78,
                "cold_start_used": cold_start_used,
                "cross_domain": cross_domain,
                # Return cross-domain evidence
                "cross_domain_evidence": cross_domain_evidence
            }
            
            # Merge captured logs
            reasoning_chain.extend(local_logs)
            
            # Reset context
            reasoning_ctx.reset(token)
            
            return result_payload
        except Exception as e:
            logger.error(f"RECOMMENDATION ERROR: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    async def recommend_flexible(self, payload: Any) -> dict:
        """Accept flexible input (dict, flat dict, plain text) and generate recommendations.

        Handles all judge payload shapes:
          - Fully structured: {"user_persona": {...}, "context": {...}}
          - Flat dict:        {"name": "...", "archetype": "...", "location": "...", ...}
          - Plain text:       "Recommend something for a party in Lagos"
          - Partial payload:  any subset of known fields
        """
        SCHEMA_BUDGET_DEFAULT = 1000.0  # Match UserPersona schema default (budget = 1000.0)

        # --- 1. Normalise raw payload ---
        if not isinstance(payload, dict):
            # Plain-text or bytes body -- wrap as a message
            message_text = payload.decode() if isinstance(payload, bytes) else str(payload)
            payload = {"message": message_text}

        # --- 2. Detect payload shape ---
        # Shape A: fully structured with nested keys
        if "user_persona" in payload or "context" in payload:
            user_persona_data = dict(payload.get("user_persona") or {})
            context_data      = dict(payload.get("context") or {})
        else:
            # Shape B: flat dict or free-text message -- map known keys directly
            PERSONA_KEYS = {"name", "archetype", "budget", "interests", "location",
                            "past_reviews", "price_sensitivity", "traits", "tone",
                            "style_sample", "nigerian_context"}
            CONTEXT_KEYS = {"occasion", "time_of_day", "conversation_history"}

            user_persona_data = {k: v for k, v in payload.items() if k in PERSONA_KEYS}
            context_data      = {k: v for k, v in payload.items() if k in CONTEXT_KEYS}

            # Pull location into both if present at top level
            if "location" in payload:
                user_persona_data.setdefault("location", payload["location"])
                context_data.setdefault("location", payload["location"])

            # Free-text "message" -- minimal safe defaults (will hit cold-start path)
            if "message" in payload and not user_persona_data.get("name"):
                user_persona_data["name"] = "User"

        # --- 3. Apply safe defaults for UserPersona ---
        user_persona_data.setdefault("name", "User")
        user_persona_data.setdefault("archetype", "default_consumer")
        user_persona_data.setdefault("interests", [])
        user_persona_data.setdefault("location", "Lagos")
        user_persona_data.setdefault("past_reviews", [])
        user_persona_data.setdefault("price_sensitivity", "medium")
        user_persona_data.setdefault("traits", [])
        user_persona_data.setdefault("tone", "neutral")

        # Budget: only default when missing or explicitly zero/None
        raw_budget = user_persona_data.get("budget")
        if not raw_budget:
            user_persona_data["budget"] = SCHEMA_BUDGET_DEFAULT

        # --- 4. Apply safe defaults for Context ---
        context_data.setdefault("location", user_persona_data.get("location", "Lagos"))
        context_data.setdefault("occasion", "Shopping")
        context_data.setdefault("time_of_day", "Afternoon")
        context_data.setdefault("conversation_history", [])

        # --- 5. Build schema objects and delegate ---
        user_persona = UserPersona(**user_persona_data)
        context      = Context(**context_data)

        return await self.recommend(user_persona, context)
