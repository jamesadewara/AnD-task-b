import logging
from typing import List, Dict
from app.models.schemas import UserPersona, Context
from app.models.seed_items import SEED_ITEMS

logger = logging.getLogger(__name__)

class Retriever:
    """Simple Python list filtering by interests, category, and budget."""
    def filter(self, user_persona: UserPersona, context: Context) -> List[dict]:
        candidates = []
        
        # Ensure interests are strings
        user_interests = []
        for i in (user_persona.interests or []):
            if isinstance(i, str):
                user_interests.append(i.lower())
            else:
                logger.warning(f"Non-string interest ignored: {i}")
        
        user_budget = user_persona.budget or 10000
        
        for item in SEED_ITEMS:
            match_score = 0
            
            # Safe category check
            category = item.get("category", "")
            if isinstance(category, str) and category.lower() in user_interests:
                match_score += 2
            
            # Safe tag overlap
            try:
                item_tags = item.get("tags", [])
                if isinstance(item_tags, list):
                    # Ensure only primitives are added to the set
                    tag_set = set(str(t).lower() for t in item_tags if isinstance(t, (str, int, float)))
                    interest_set = set(user_interests)
                    tag_overlap = tag_set & interest_set
                    if tag_overlap:
                        match_score += 1
            except Exception as e:
                logger.warning(f"Tag overlap failed for item {item.get('item_id')}: {e}")
            
            # Safe location check
            loc = item.get("location", "")
            ctx_loc = context.location or ""
            if isinstance(loc, str) and isinstance(ctx_loc, str) and ctx_loc.lower() in loc.lower():
                match_score += 1
            
            # Safe budget check
            price = item.get("price_naira", 0)
            if isinstance(price, (int, float)) and price <= user_budget * 1.5 and match_score > 0:
                candidates.append({**item, "_match_score": match_score})
        
        # Fallback (archetype-aware)
        if len(candidates) < 3:
            archetype = str(user_persona.archetype or "").lower()
            if "haggler" in archetype:
                candidates = [item for item in SEED_ITEMS 
                              if isinstance(item.get("price_naira"), (int, float)) 
                              and item["price_naira"] <= user_budget * 0.5]
            elif "big woman" in archetype:
                candidates = [item for item in SEED_ITEMS 
                              if isinstance(item.get("price_naira"), (int, float))
                              and (item["price_naira"] >= user_budget * 0.3 
                                   or any(t in str(item.get("tags", [])) for t in ["luxury", "fine dining"]))]
            else:
                candidates = [item for item in SEED_ITEMS 
                              if isinstance(item.get("price_naira"), (int, float))
                              and item["price_naira"] <= user_budget]
        
        return candidates[:20]
