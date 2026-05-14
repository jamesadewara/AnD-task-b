import re
from typing import List, Dict
from loguru import logger

from app.core.llm import llm_service

class CoTReasoning:
    def __init__(self):
        pass

    async def generate_reasoning_chain(self, persona: dict, context: dict, category: str) -> List[Dict[str, str]]:
        name = persona.get("name", "Anonymous User")
        interests = ", ".join(persona.get("interests", [])[:10])
        traits = ", ".join(persona.get("traits", [])[:10])
        tone = persona.get("tone", "neutral")
        nigerian_context = persona.get("nigerian_context", True)

        prompt = f"""
        User: {name}
        Interests: {interests}
        Traits: {traits}
        Tone: {tone}
        Nigerian: {nigerian_context}
        Mood: {context.get('mood')} | Time: {context.get('time_of_day')} | Location: {context.get('location')}
        Request: {context.get('raw_message', 'No specific request')}
        
        Write 2-3 sentences analyzing what this user would like.
        """

        messages = [{"role": "user", "content": prompt}]
        logger.info(f"[CoTReasoning] Generating reasoning strategy for {name}...")
        response_text = await llm_service.get_completion(messages=messages, temperature=0.4, max_tokens=150)
        
        # Build reasoning chain in Python
        reasoning_chain = []
        
        reasoning_chain.append({
            "step": "retrieve",
            "action": "Fetched user persona and context",
            "output": f"Persona: {name}, Interests: {len(persona.get('interests', []))}. Context: {context.get('mood')} mood."
        })
        
        reasoning_chain.append({
            "step": "cot_reason",
            "action": "Analyzed profile and context for strategy",
            "output": response_text.strip().replace('"', '')
        })

        return reasoning_chain
