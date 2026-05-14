#!/usr/bin/env python3
"""
AnD Task B Ablation Study
==========================
Evaluates recommendation quality with/without key components.

Ablations:
  - Full System (baseline)
  - w/o Location Boost
  - w/o Cold Start handling
  - w/o Occasion Matching

Metrics:
  - NDCG@10 (normalized discounted cumulative gain)
  - Hit Rate@3 (top-3 contains expected category)
  - Category Diversity (distinct categories in top-10)

Usage:
  python ablation.py --output_dir ./results
"""

import argparse
import json
import os
import sys
import math
import statistics
from typing import List, Dict

# Add parent paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.schemas import UserPersona, Context
from app.core.retriever import Retriever
from app.core.ranker import Ranker
from app.core.cold_start import ColdStart


# --- TEST CASES (50) ---
TEST_CASES = [
    # Cold-start Haggler in Lagos (10)
    {"case_id": "b_001", "persona": {"name": "Haggler_Lagos_1", "archetype": "Haggler", "budget": 5000, "interests": ["street_food"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Evening", "occasion": "Quick Dinner"}, "expected_categories": ["street_food"]},
    {"case_id": "b_002", "persona": {"name": "Haggler_Lagos_2", "archetype": "Haggler", "budget": 10000, "interests": ["nollywood"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Night", "occasion": "Movie Night"}, "expected_categories": ["nollywood"]},
    {"case_id": "b_003", "persona": {"name": "Haggler_Lagos_3", "archetype": "Haggler", "budget": 3000, "interests": ["electronics"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Morning", "occasion": "Essential Shopping"}, "expected_categories": ["electronics"]},
    {"case_id": "b_004", "persona": {"name": "Haggler_Lagos_4", "archetype": "Haggler", "budget": 7000, "interests": ["fashion"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Afternoon", "occasion": "Market Visit"}, "expected_categories": ["fashion"]},
    {"case_id": "b_005", "persona": {"name": "Haggler_Lagos_5", "archetype": "Haggler", "budget": 4500, "interests": ["wellness"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Morning", "occasion": "Self Care"}, "expected_categories": ["wellness"]},
    {"case_id": "b_006", "persona": {"name": "Haggler_Lagos_6", "archetype": "Haggler", "budget": 6000, "interests": ["street_food"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Evening", "occasion": "Party"}, "expected_categories": ["street_food"]},
    {"case_id": "b_007", "persona": {"name": "Haggler_Lagos_7", "archetype": "Haggler", "budget": 8000, "interests": ["electronics"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Afternoon", "occasion": "Gift Search"}, "expected_categories": ["electronics"]},
    {"case_id": "b_008", "persona": {"name": "Haggler_Lagos_8", "archetype": "Haggler", "budget": 5500, "interests": ["nollywood"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Night", "occasion": "Family Time"}, "expected_categories": ["nollywood"]},
    {"case_id": "b_009", "persona": {"name": "Haggler_Lagos_9", "archetype": "Haggler", "budget": 4000, "interests": ["street_food"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Evening", "occasion": "Street Crawl"}, "expected_categories": ["street_food"]},
    {"case_id": "b_010", "persona": {"name": "Haggler_Lagos_10", "archetype": "Haggler", "budget": 9000, "interests": ["fashion"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Morning", "occasion": "Church"}, "expected_categories": ["fashion"]},

    # Cold-start Big Woman in Abuja (10)
    {"case_id": "b_011", "persona": {"name": "BigWoman_Abuja_1", "archetype": "Big Woman", "budget": 150000, "interests": ["fashion"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Afternoon", "occasion": "Wedding"}, "expected_categories": ["fashion"]},
    {"case_id": "b_012", "persona": {"name": "BigWoman_Abuja_2", "archetype": "Big Woman", "budget": 200000, "interests": ["wellness"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Morning", "occasion": "Relaxation"}, "expected_categories": ["wellness"]},
    {"case_id": "b_013", "persona": {"name": "BigWoman_Abuja_3", "archetype": "Big Woman", "budget": 100000, "interests": ["dining"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Evening", "occasion": "Business Dinner"}, "expected_categories": ["dining"]},
    {"case_id": "b_014", "persona": {"name": "BigWoman_Abuja_4", "archetype": "Big Woman", "budget": 180000, "interests": ["electronics"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Afternoon", "occasion": "Luxury Shopping"}, "expected_categories": ["electronics"]},
    {"case_id": "b_015", "persona": {"name": "BigWoman_Abuja_5", "archetype": "Big Woman", "budget": 120000, "interests": ["community_events"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Evening", "occasion": "Networking"}, "expected_categories": ["community_events"]},
    {"case_id": "b_016", "persona": {"name": "BigWoman_Abuja_6", "archetype": "Big Woman", "budget": 160000, "interests": ["fashion"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Morning", "occasion": "Bespoke Fitting"}, "expected_categories": ["fashion"]},
    {"case_id": "b_017", "persona": {"name": "BigWoman_Abuja_7", "archetype": "Big Woman", "budget": 140000, "interests": ["wellness"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Afternoon", "occasion": "Skin Care"}, "expected_categories": ["wellness"]},
    {"case_id": "b_018", "persona": {"name": "BigWoman_Abuja_8", "archetype": "Big Woman", "budget": 190000, "interests": ["dining"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Evening", "occasion": "Celebration"}, "expected_categories": ["dining"]},
    {"case_id": "b_019", "persona": {"name": "BigWoman_Abuja_9", "archetype": "Big Woman", "budget": 110000, "interests": ["electronics"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Morning", "occasion": "Office Setup"}, "expected_categories": ["electronics"]},
    {"case_id": "b_020", "persona": {"name": "BigWoman_Abuja_10", "archetype": "Big Woman", "budget": 170000, "interests": ["community_events"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Evening", "occasion": "Gala"}, "expected_categories": ["community_events"]},

    # Community Validator in PH with history (10)
    {"case_id": "b_021", "persona": {"name": "Validator_PH_1", "archetype": "Community Validator", "budget": 25000, "interests": ["street_food"], "past_reviews": [{"item_id": "sf_004", "rating": 5, "text": "Loved the Boli!"}]}, "context": {"location": "Port Harcourt", "time_of_day": "Evening", "occasion": "Date Night"}, "expected_categories": ["street_food"]},
    {"case_id": "b_022", "persona": {"name": "Validator_PH_2", "archetype": "Community Validator", "budget": 30000, "interests": ["electronics"], "past_reviews": [{"item_id": "el_001", "rating": 4, "text": "Solid pods"}]}, "context": {"location": "Port Harcourt", "time_of_day": "Afternoon", "occasion": "Tech Upgrade"}, "expected_categories": ["electronics"]},
    {"case_id": "b_023", "persona": {"name": "Validator_PH_3", "archetype": "Community Validator", "budget": 20000, "interests": ["nollywood"], "past_reviews": [{"item_id": "nw_004", "rating": 5, "text": "Great movie"}]}, "context": {"location": "Port Harcourt", "time_of_day": "Night", "occasion": "Movie Night"}, "expected_categories": ["nollywood"]},
    {"case_id": "b_024", "persona": {"name": "Validator_PH_4", "archetype": "Community Validator", "budget": 28000, "interests": ["fashion"], "past_reviews": [{"item_id": "fs_003", "rating": 4, "text": "Comfortable"}]}, "context": {"location": "Port Harcourt", "time_of_day": "Morning", "occasion": "Social Gathering"}, "expected_categories": ["fashion"]},
    {"case_id": "b_025", "persona": {"name": "Validator_PH_5", "archetype": "Community Validator", "budget": 22000, "interests": ["community_events"], "past_reviews": [{"item_id": "ce_005", "rating": 5, "text": "Amazing concert"}]}, "context": {"location": "Port Harcourt", "time_of_day": "Evening", "occasion": "Live Music"}, "expected_categories": ["community_events"]},
    {"case_id": "b_026", "persona": {"name": "Validator_PH_6", "archetype": "Community Validator", "budget": 26000, "interests": ["street_food"], "past_reviews": []}, "context": {"location": "Port Harcourt", "time_of_day": "Afternoon", "occasion": "Local Taste"}, "expected_categories": ["street_food"]},
    {"case_id": "b_027", "persona": {"name": "Validator_PH_7", "archetype": "Community Validator", "budget": 24000, "interests": ["electronics"], "past_reviews": []}, "context": {"location": "Port Harcourt", "time_of_day": "Morning", "occasion": "Gadget Search"}, "expected_categories": ["electronics"]},
    {"case_id": "b_028", "persona": {"name": "Validator_PH_8", "archetype": "Community Validator", "budget": 21000, "interests": ["nollywood"], "past_reviews": []}, "context": {"location": "Port Harcourt", "time_of_day": "Night", "occasion": "Relaxation"}, "expected_categories": ["nollywood"]},
    {"case_id": "b_029", "persona": {"name": "Validator_PH_9", "archetype": "Community Validator", "budget": 29000, "interests": ["fashion"], "past_reviews": []}, "context": {"location": "Port Harcourt", "time_of_day": "Afternoon", "occasion": "Traditional Outfit"}, "expected_categories": ["fashion"]},
    {"case_id": "b_030", "persona": {"name": "Validator_PH_10", "archetype": "Community Validator", "budget": 23000, "interests": ["community_events"], "past_reviews": []}, "context": {"location": "Port Harcourt", "time_of_day": "Evening", "occasion": "Networking"}, "expected_categories": ["community_events"]},

    # Cross-domain (10)
    {"case_id": "b_031", "persona": {"name": "Cross_1", "archetype": "Default", "budget": 50000, "interests": ["electronics", "street_food"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Afternoon", "occasion": "Lunch and Shop"}, "expected_categories": ["electronics", "street_food"]},
    {"case_id": "b_032", "persona": {"name": "Cross_2", "archetype": "Default", "budget": 75000, "interests": ["fashion", "dining"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Evening", "occasion": "Date Night"}, "expected_categories": ["fashion", "dining"]},
    {"case_id": "b_033", "persona": {"name": "Cross_3", "archetype": "Default", "budget": 30000, "interests": ["nollywood", "wellness"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Morning", "occasion": "Self Care Day"}, "expected_categories": ["nollywood", "wellness"]},
    {"case_id": "b_034", "persona": {"name": "Cross_4", "archetype": "Default", "budget": 45000, "interests": ["community_events", "electronics"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Afternoon", "occasion": "Tech Summit"}, "expected_categories": ["community_events", "electronics"]},
    {"case_id": "b_035", "persona": {"name": "Cross_5", "archetype": "Default", "budget": 60000, "interests": ["street_food", "fashion"], "past_reviews": []}, "context": {"location": "Kano", "time_of_day": "Evening", "occasion": "Culture Trip"}, "expected_categories": ["street_food", "fashion"]},
    {"case_id": "b_036", "persona": {"name": "Cross_6", "archetype": "Default", "budget": 35000, "interests": ["dining", "nollywood"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Night", "occasion": "Movie & Dinner"}, "expected_categories": ["dining", "nollywood"]},
    {"case_id": "b_037", "persona": {"name": "Cross_7", "archetype": "Default", "budget": 80000, "interests": ["wellness", "community_events"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Morning", "occasion": "Wellness Expo"}, "expected_categories": ["wellness", "community_events"]},
    {"case_id": "b_038", "persona": {"name": "Cross_8", "archetype": "Default", "budget": 25000, "interests": ["electronics", "fashion"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Afternoon", "occasion": "Mall Crawl"}, "expected_categories": ["electronics", "fashion"]},
    {"case_id": "b_039", "persona": {"name": "Cross_9", "archetype": "Default", "budget": 55000, "interests": ["street_food", "dining"], "past_reviews": []}, "context": {"location": "PH", "time_of_day": "Evening", "occasion": "Foodie Tour"}, "expected_categories": ["street_food", "dining"]},
    {"case_id": "b_040", "persona": {"name": "Cross_10", "archetype": "Default", "budget": 90000, "interests": ["nollywood", "community_events"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Afternoon", "occasion": "Film Festival"}, "expected_categories": ["nollywood", "community_events"]},

    # Multi-turn (10)
    {"case_id": "b_041", "persona": {"name": "Multi_1", "archetype": "Haggler", "budget": 5000, "interests": ["street_food"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Evening", "occasion": "Quick Dinner"}, "expected_categories": ["street_food"]},
    {"case_id": "b_042", "persona": {"name": "Multi_2", "archetype": "Big Woman", "budget": 150000, "interests": ["fashion"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Afternoon", "occasion": "Wedding"}, "expected_categories": ["fashion"]},
    {"case_id": "b_043", "persona": {"name": "Multi_3", "archetype": "Default", "budget": 20000, "interests": ["electronics"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Morning", "occasion": "Tech Search"}, "expected_categories": ["electronics"]},
    {"case_id": "b_044", "persona": {"name": "Multi_4", "archetype": "Default", "budget": 10000, "interests": ["street_food"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Night", "occasion": "Late Snack"}, "expected_categories": ["street_food"]},
    {"case_id": "b_045", "persona": {"name": "Multi_5", "archetype": "Default", "budget": 30000, "interests": ["nollywood"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Night", "occasion": "Movie Night"}, "expected_categories": ["nollywood"]},
    {"case_id": "b_046", "persona": {"name": "Multi_6", "archetype": "Default", "budget": 50000, "interests": ["dining"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Evening", "occasion": "Dinner"}, "expected_categories": ["dining"]},
    {"case_id": "b_047", "persona": {"name": "Multi_7", "archetype": "Default", "budget": 25000, "interests": ["fashion"], "past_reviews": []}, "context": {"location": "Abuja", "time_of_day": "Afternoon", "occasion": "Shopping"}, "expected_categories": ["fashion"]},
    {"case_id": "b_048", "persona": {"name": "Multi_8", "archetype": "Default", "budget": 40000, "interests": ["wellness"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Morning", "occasion": "Spa"}, "expected_categories": ["wellness"]},
    {"case_id": "b_049", "persona": {"name": "Multi_9", "archetype": "Default", "budget": 15000, "interests": ["community_events"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Afternoon", "occasion": "Outing"}, "expected_categories": ["community_events"]},
    {"case_id": "b_050", "persona": {"name": "Multi_10", "archetype": "Default", "budget": 35000, "interests": ["electronics"], "past_reviews": []}, "context": {"location": "Lagos", "time_of_day": "Morning", "occasion": "Gifts"}, "expected_categories": ["electronics"]},
]


def compute_ndcg(relevances: List[float], k: int = 10) -> float:
    """
    Compute NDCG@k.
    relevances: scores in the ORDER returned by the ranker (NOT pre-sorted).
    NDCG = DCG(actual order) / DCG(ideal order).
    Bug-fixed: previously both rel and ideal were sorted, giving NDCG=1.0 always.
    """
    if not relevances:
        return 0.0
    actual = relevances[:k]          # preserve ranker order
    ideal = sorted(relevances, reverse=True)[:k]
    dcg  = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(actual))
    idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def score_relevance(item: dict, persona: dict, context: dict) -> float:
    """
    Granular relevance scoring for NDCG computation.
    Uses continuous price ratio and item rating so scores vary across ablations.
    Max score: ~3.0 (unnormalised before clamp to 1.0 for NDCG).
    """
    rel = 0.0

    # --- Category interest match (binary, most important signal) ---
    if item.get("category") in persona.get("interests", []):
        rel += 1.0

    # --- Location match ---
    ctx_loc = (context.get("location") or "").lower()
    item_loc = (item.get("location") or "").lower()
    if ctx_loc and item_loc and (ctx_loc in item_loc or item_loc in ctx_loc):
        rel += 0.5

    # --- Continuous price affordability (0-0.5 range, decays as price exceeds budget) ---
    price = item.get("price_naira", 0) or 0
    budget = persona.get("budget", 1) or 1
    if price > 0:
        ratio = price / budget
        if ratio <= 1.0:
            rel += 0.5          # fully affordable
        elif ratio <= 1.5:
            rel += 0.3          # slightly over budget
        elif ratio <= 2.0:
            rel += 0.1          # significantly over
        # > 2x budget: no affordability score

    # --- Item rating quality (0-0.4 range) ---
    item_rating = item.get("rating", 0) or item.get("avg_rating", 0) or 0
    if item_rating:
        rel += 0.4 * (float(item_rating) / 5.0)

    # --- Occasion tag match ---
    occasion = (context.get("occasion") or "").lower()
    occasion_map = {
        "movie night": ["movie night", "nollywood", "family"],
        "quick dinner": ["quick", "fast", "street_food"],
        "business dinner": ["fine dining", "exclusive", "luxury"],
        "date night": ["romance", "intimate", "exclusive"],
        "party": ["spicy", "celebration", "high-energy"],
        "breakfast": ["breakfast", "morning", "light"],
        "wedding": ["bespoke", "traditional", "luxury", "fashion"],
        "self care": ["organic", "wellness", "skin", "spa"],
    }
    for occ, keywords in occasion_map.items():
        if occ in occasion:
            if any(kw in (item.get("tags") or []) for kw in keywords):
                rel += 0.3
            break

    # Clamp to [0, 3.0] — leave un-normalised so NDCG has real variance
    return min(3.0, max(0.0, rel))


def apply_ablation(study_name: str, persona: dict, context: dict) -> tuple:
    """Apply ablation modifications."""
    p = persona.copy()
    c = context.copy()

    if study_name == "w/o Location Boost":
        c["location"] = ""
    elif study_name == "w/o Cold Start":
        if not p.get("past_reviews"):
            p["past_reviews"] = [{"item_id": "mock", "rating": 4, "text": "Good"}]
    elif study_name == "w/o Occasion Matching":
        c["occasion"] = ""

    return p, c


def run_ablation(study_name: str, cases: List[dict]) -> dict:
    """Run one ablation study on all cases."""
    retriever = Retriever()
    ranker = Ranker()
    cold_start = ColdStart()

    ndcgs = []
    hit_rates = []
    diversities = []

    print(f"  Running {study_name}...")
    for case in cases:
        persona, context = apply_ablation(study_name, case["persona"], case["context"])
        p = UserPersona(**persona)
        c = Context(**context)

        try:
            candidates = retriever.filter(p, c)
            analysis = {
                "preferred_categories": p.interests or [],
                "priorities": ["authentic", "value"],
                "reasoning": "Ablation study",
            }
            ranked = ranker.score(candidates, analysis, p, c)

            if study_name != "w/o Cold Start" and not persona.get("past_reviews"):
                ranked = cold_start.adjust(ranked, p)

            top_10 = ranked[:10]

            # NDCG
            relevances = [score_relevance(item, persona, context) for item in top_10]
            ndcg = compute_ndcg(relevances, k=10)
            ndcgs.append(ndcg)

            # Hit Rate@3
            top_3_cats = [item.get("category") for item in top_10[:3]]
            hits = any(cat in case["expected_categories"] for cat in top_3_cats)
            hit_rates.append(1.0 if hits else 0.0)

            # Diversity
            cats = set(item.get("category") for item in top_10)
            diversities.append(len(cats))

        except Exception as e:
            print(f"    WARN: {case['case_id']} failed: {e}")
            ndcgs.append(0.0)
            hit_rates.append(0.0)
            diversities.append(0)

    return {
        "ndcg_at_10": round(statistics.mean(ndcgs), 3) if ndcgs else 0,
        "std_ndcg": round(statistics.stdev(ndcgs), 3) if len(ndcgs) > 1 else 0,
        "hit_rate_at_3": round(statistics.mean(hit_rates), 3) if hit_rates else 0,
        "avg_diversity": round(statistics.mean(diversities), 2) if diversities else 0,
        "samples": len(cases),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_dir", default="./results")
    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    studies = ["Full System", "w/o Location Boost", "w/o Cold Start", "w/o Occasion Matching"]
    results = {}

    print("\n" + "="*50)
    print("TASK B ABLATION STUDY (50 cases)")
    print("="*50)

    for study in studies:
        results[study] = run_ablation(study, TEST_CASES)

    # Save
    output_path = os.path.join(args.output_dir, "ablation_task_b.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    # Print table
    print("\n" + "-"*70)
    print(f"{'Study':<30} | {'NDCG@10':>8} | {'Std':>5} | {'Hit@3':>6} | {'Div':>4}")
    print("-"*70)
    for study, vals in results.items():
        print(f"{study:<30} | {vals['ndcg_at_10']:>8.3f} | {vals['std_ndcg']:>5.3f} | {vals['hit_rate_at_3']:>6.3f} | {vals['avg_diversity']:>4.1f}")
    print("-"*70)
    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()