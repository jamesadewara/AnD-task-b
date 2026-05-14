import logging
from typing import List, Dict
from app.models.schemas import UserPersona, Context
from app.core.config import settings
from app.core.faiss_search import FaissItemStore

logger = logging.getLogger(__name__)

# Initialize once at module load (not per request)
_item_store = FaissItemStore()


class Retriever:
    """FAISS-accelerated candidate retrieval + original archetype-aware scoring."""

    def filter(self, user_persona: UserPersona, context: Context) -> List[dict]:
        # ---- STEP 1: FAISS vector search (replaces brute-force loop) ----
        # Convert Pydantic models to dicts for faiss_search
        persona_dict = user_persona.model_dump() if hasattr(user_persona, "model_dump") else dict(user_persona)
        context_dict = context.model_dump() if hasattr(context, "model_dump") else dict(context)

        candidates = _item_store.search(persona_dict, context_dict, top_k=100)

        # ---- STEP 2: Your existing scoring logic (unchanged) ----
        user_interests = [str(i).lower() for i in (user_persona.interests or [])]
        user_budget = user_persona.budget or settings.DEFAULT_USER_BUDGET
        archetype = str(user_persona.archetype or "").lower()

        # Archetype-aware budget limit (your exact logic)
        budget_limit = user_budget * 1.2 if "haggler" in archetype else user_budget * 2.5

        filtered = []
        for item in candidates:
            match_score = 0

            # 1. Category/Interest Match (+5)
            category = str(item.get("category", "")).lower()
            if category in user_interests:
                match_score += 5

            # 2. Tag Overlap (+3)
            item_tags = [str(t).lower() for t in item.get("tags", [])]
            if any(interest in item_tags for interest in user_interests):
                match_score += 3

            # 3. Location Relevance (+2)
            ctx_loc = (context.location or "").lower()
            item_loc = str(item.get("location", "")).lower()
            if ctx_loc and (ctx_loc in item_loc or item_loc in ctx_loc):
                match_score += 2

            # 4. Budget Constraint (Soft filter)
            price = item.get("price_naira", 0)
            if price <= budget_limit:
                # Include if there's any match signal OR it's high-quality
                if match_score > 0 or item.get("rating", 0) >= 4.5:
                    # NEW: Add FAISS semantic score bonus
                    faiss_score = item.get("_faiss_score", 0)
                    match_score += min(faiss_score * 5.0, 10.0)

                    filtered.append({**item, "_match_score": match_score})

        # ---- STEP 3: Fallback (your exact logic) ----
        if not filtered:
            logger.warning(f"No candidates found for {user_persona.name}. Falling back to top-rated items.")
            # Load all items from store for fallback
            all_items = _item_store.items_by_id.values()
            filtered = sorted(
                [i for i in all_items if i["price_naira"] <= user_budget * 1.5],
                key=lambda x: x["rating"],
                reverse=True
            )[:10]

        return filtered