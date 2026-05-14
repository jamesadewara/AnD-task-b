import logging
from typing import List, Dict
from app.corpus.data.seed_items import SEED_ITEMS
from app.models.schemas import UserPersona, Context

logger = logging.getLogger(__name__)

class Retriever:
    """Intelligent candidate retrieval from the SEED_ITEMS pool."""
    def filter(self, user_persona: UserPersona, context: Context) -> List[dict]:
        candidates = []
        
        user_interests = [str(i).lower() for i in (user_persona.interests or [])]
        user_budget = user_persona.budget or 0
        
        for item in SEED_ITEMS:
            match_score = 0
            
            # 1. Category/Interest Match
            category = str(item.get("category", "")).lower()
            if category in user_interests:
                match_score += 5
            
            # 2. Tag Overlap
            item_tags = [str(t).lower() for t in item.get("tags", [])]
            if any(interest in item_tags for interest in user_interests):
                match_score += 3
            
            # 3. Location Relevance (City Match)
            ctx_loc = (context.location or "").lower()
            item_loc = str(item.get("location", "")).lower()
            if ctx_loc and (ctx_loc in item_loc or item_loc in ctx_loc):
                match_score += 2
            
            # 4. Budget Constraint (Soft filter)
            price = item.get("price_naira", 0)
            
            # Archetype-aware retrieval: Hagglers are strict, Prestige users are loose
            archetype = str(user_persona.archetype or "").lower()
            budget_limit = user_budget * 1.2 if "haggler" in archetype else user_budget * 2.5
            
            if price <= budget_limit:
                # If we have a match_score or it's a generally high-quality item, include it
                if match_score > 0 or item.get("rating", 0) >= 4.5:
                    candidates.append({**item, "_match_score": match_score})
        
        # FINAL FALLBACK: If pool is dry, provide top-rated items within budget
        if not candidates:
            logger.warning(f"No candidates found for {user_persona.name}. Falling back to top-rated items.")
            candidates = sorted(
                [i for i in SEED_ITEMS if i["price_naira"] <= user_budget * 1.5],
                key=lambda x: x["rating"],
                reverse=True
            )[:10]
        
        return candidates
