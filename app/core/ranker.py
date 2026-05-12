from typing import List, Dict
from app.models.schemas import UserPersona, Context
from app.core.config import settings

class Ranker:
    def score(self, candidates: List[Dict], analysis: Dict, 
              user_persona: UserPersona, context: Context) -> List[Dict]:
        scored = []
        preferred = [p.lower() for p in analysis.get("preferred_categories", [])]
        priorities = [p.lower() for p in analysis.get("priorities", [])]
        budget = user_persona.budget or 10000
        
        for item in candidates:
            score = item["rating"] * 2 # Base score: 0-10
            
            # Category match
            if item["category"].lower() in preferred:
                score += 5
            
            # Tag match with priorities from CoT
            for tag in item["tags"]:
                if any(p in tag.lower() for p in priorities):
                    score += 2
            
            # Price alignment logic
            ratio = item["price_naira"] / budget if budget > 0 else 1
            if ratio <= 0.3:
                score += 4 # Extremely affordable
            elif ratio <= 0.6:
                score += 2 # Very affordable
            elif ratio <= 1.0:
                score += 1 # Within budget
            elif ratio <= 1.5:
                score -= 1 # Slightly over
            else:
                score -= 3 # Way over budget
            
            # Location boost
            if context.location and context.location.lower() in item["location"].lower():
                score += 2
            
            # Occasion boost (using OCCASION_KEYWORDS from config)
            occasion = (context.occasion or "").lower()
            occasion_map = settings.OCCASION_KEYWORDS
            
            for occ, keywords in occasion_map.items():
                if occ in occasion:
                    item_tags = [t.lower() for t in item["tags"]]
                    if any(k.lower() in item_tags for k in keywords):
                        score += 3
                    break
            
            # Time of day awareness
            tod = (context.time_of_day or "").lower()
            if tod == "morning" and "breakfast" in [t.lower() for t in item["tags"]]:
                score += 2
            
            scored.append({**item, "score": round(max(0, score), 2)})
        
        # Sort by final score
        return sorted(scored, key=lambda x: x["score"], reverse=True)
