from typing import List, Dict, Any

class ReActAgent:
    def filter_and_rank(self, candidates: List[Dict[str, Any]], context: dict, user: dict) -> List[Dict[str, Any]]:
        valid_candidates = []
        for item in candidates:
            if context.get("mood") == "tired" and item.get("duration_minutes", 0) > 150:
                continue
            if context.get("time_of_day") == "night" and item.get("category") == "movies" and item.get("duration_minutes", 0) > 180:
                continue
            valid_candidates.append(item)

        for item in valid_candidates:
            score = item.get("base_score", 0.5)
            if user.get("nigerian_context", True) and item.get("metadata", {}).get("nigerian_context"):
                score += 0.15
            if item.get("category") in user.get("interests", []):
                score += 0.2
            if context.get("mood") == "hungry" and item.get("category") == "food":
                score += 0.15
            if context.get("mood") == "energetic" and item.get("category") in ["music", "events"]:
                score += 0.1
            score += item.get("metadata", {}).get("popularity", 0) * 0.05
            item["final_score"] = min(1.0, max(0.0, score))

        valid_candidates.sort(key=lambda x: x["final_score"], reverse=True)
        return valid_candidates[:10]
