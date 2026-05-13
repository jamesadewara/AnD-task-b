from typing import List, Dict
from app.models.schemas import UserPersona, Context
from app.core.config import settings

class Ranker:
    def score(self, candidates: List[Dict], analysis: Dict, 
              user_persona: UserPersona, context: Context) -> List[Dict]:
        scored = []
        preferred = [p.lower() for p in analysis.get("preferred_categories", [])]
        priorities = [p.lower() for p in analysis.get("priorities", [])]
        user_interests = [i.lower() for i in (user_persona.interests or [])]
        budget = user_persona.budget or 10000
        archetype = str(user_persona.archetype or "").lower()
        
        for item in candidates:
            score = item["rating"] * 2.0 # Base score: 0-10
            
            # 1. CATEGORY & INTEREST ALIGNMENT
            if item["category"].lower() in preferred:
                score += 8.0 # Stronger category boost
            
            # Direct interest match in tags or name
            item_tags = [t.lower() for t in item["tags"]]
            if any(i in item_tags or i in item["name"].lower() for i in user_interests):
                score += 4.0

            # 2. TAG MATCH WITH LLM PRIORITIES
            for tag in item_tags:
                if any(p in tag for p in priorities):
                    score += 3.0
            
            # 3. ARCHETYPE-SPECIFIC PRICE LOGIC
            ratio = item["price_naira"] / budget if budget > 0 else 1
            if "haggler" in archetype:
                # Hagglers love cheap, hate anything near or over budget
                if ratio <= 0.3: score += 10.0
                elif ratio <= 0.6: score += 5.0
                elif ratio <= 1.0: score += 1.0
                else: score -= 15.0 # Severe penalty for over-budget
            elif any(t in archetype for t in ["big woman", "big man", "prestige"]):
                # Prestige users favor luxury over price, but within a reasonable band
                if any(t in item_tags for t in ["luxury", "exclusive", "premium", "bespoke"]):
                    score += 12.0
                if ratio > 1.2: score -= 2.0 # Slight penalty only
            else:
                # Default price logic
                if ratio <= 0.6: score += 4.0
                elif ratio <= 1.0: score += 2.0
                elif ratio <= 1.5: score -= 5.0
            
            # 4. LOCATION RELEVANCE (CULTURALLY INTELLIGENT)
            ctx_loc = (context.location or "").lower()
            item_loc = item["location"].lower()
            if ctx_loc == item_loc:
                score += 15.0 # HUGE boost for local city match
            elif ctx_loc in item_loc or item_loc in ctx_loc:
                score += 8.0 # Strong boost for partial match (e.g. Lagos vs Ikeja)
            elif item_loc == "nigeria":
                score += 3.0 # Nationwide availability
            
            # 5. OCCASION & TIME-OF-DAY INTELLIGENCE
            occasion = (context.occasion or "").lower()
            tod = (context.time_of_day or "").lower()
            
            # Check situational tags (morning, evening, etc.)
            if tod in item_tags:
                score += 6.0
            
            # Occasion keyword mapping
            occasion_map = settings.OCCASION_KEYWORDS
            for occ, keywords in occasion_map.items():
                if occ in occasion:
                    if any(k.lower() in item_tags for k in keywords):
                        score += 8.0
                    break
            
            scored.append({**item, "score": round(max(0, score), 2)})
        
        # Sort by final score
        return sorted(scored, key=lambda x: x["score"], reverse=True)
