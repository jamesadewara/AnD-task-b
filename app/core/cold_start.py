from typing import List, Dict
from app.models.schemas import UserPersona

class ColdStart:
    """Demographic inference using persona signals — works for ANY archetype."""
    
    def adjust(self, ranked: List[Dict], user_persona: UserPersona) -> List[Dict]:
        budget = user_persona.budget or 10000
        sensitivity = (user_persona.price_sensitivity or "medium").lower()
        interests = [i.lower() for i in user_persona.interests]
        traits = [t.lower() for t in user_persona.traits]
        tone = (user_persona.tone or "neutral").lower()
        location = (user_persona.location or "").lower()
        
        adjusted = []
        
        for item in ranked:
            boost = 0.0
            
            # --- 1. PRICE ALIGNMENT (universal) ---
            price = item.get("price_naira", 0)
            ratio = price / budget if budget > 0 else 1.0
            
            if sensitivity == "high":
                if ratio <= 0.3: boost += 4
                elif ratio <= 0.6: boost += 2
                elif ratio <= 1.0: boost += 1
                elif ratio > 1.5: boost -= 4
                elif ratio > 1.0: boost -= 2
            elif sensitivity == "low":
                if ratio >= 1.0: boost += 2  # Low sensitivity = comfortable with premium
                if ratio < 0.2: boost -= 1   # But might see "too cheap" as low quality
            else:  # medium
                if ratio <= 1.0: boost += 1
                elif ratio > 1.5: boost -= 2
            
            # --- 2. INTEREST AFFINITY (universal) ---
            category = item.get("category", "").lower()
            if category in interests:
                boost += 5
            
            tags = [t.lower() for t in item.get("tags", [])]
            tag_overlap = set(tags) & set(interests)
            boost += len(tag_overlap) * 2
            
            # --- 3. TRAIT SIGNALS (universal) ---
            if "quality_over_price" in traits:
                if item.get("rating", 0) >= 4.5:
                    boost += 3
                if "luxury" in tags or "premium" in tags or "handmade" in tags:
                    boost += 2
            
            if "price_sensitive" in traits or "value_seeker" in traits:
                if "value" in tags or "cheap" in tags or "budget" in tags:
                    boost += 3
                if ratio <= 0.5:
                    boost += 2
            
            if "status_conscious" in traits:
                if "exclusive" in tags or "prestige" in tags or "bespoke" in tags:
                    boost += 3
                if item.get("price_naira", 0) >= budget * 0.8:
                    boost += 2  # Expensive = status signal
            
            if "social" in traits or "outgoing" in traits:
                if "family" in tags or "social" in tags or "shareable" in tags:
                    boost += 2
            
            # --- 4. TONE SIGNAL (universal) ---
            if tone == "formal":
                if "fine dining" in tags or "luxury" in tags or "exclusive" in tags:
                    boost += 2
                if "street" in category:  # Formal tone unlikely for street food
                    boost -= 1
            elif tone == "casual" or tone == "energetic":
                if "street" in category or "local" in tags or "quick" in tags:
                    boost += 2
                if "fine dining" in tags:
                    boost -= 1  # Casual user unlikely for white-tablecloth
            
            # --- 5. LOCATION RELEVANCE (universal) ---
            item_location = item.get("location", "").lower()
            if location and location in item_location:
                boost += 2
            elif location and "nigeria" in item_location:
                boost += 0.5  # Nationwide availability is mildly positive
            
            # Apply boost
            current_score = item.get("score", item.get("rating", 3.0) * 2)
            new_score = round(current_score + boost, 2)
            adjusted.append({**item, "score": new_score})
        
        return sorted(adjusted, key=lambda x: x["score"], reverse=True)