"""
AnD-task-b: Recommendation Evaluation Runner
Computes RMSE, NDCG@10, per-archetype breakdowns, interaction-bucket analysis,
and cross-domain diversity. All metrics are empirically derived from corpus data.
"""
import sys
import io
# Force UTF-8 stdout so Windows cp1252 consoles don't raise UnicodeEncodeError
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import math
import random
import statistics
from collections import defaultdict
from typing import List, Dict, Tuple

# Access consolidated data from Task B corpus
CORPUS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
if CORPUS_PATH not in sys.path:
    sys.path.insert(0, CORPUS_PATH)

# Set mock env var for Pydantic validation
os.environ["OPENROUTER_API_KEYS"] = '["sk-or-v1-placeholder-for-tests"]'

try:
    from app.corpus.seed_items import SEED_ITEMS
    from app.corpus.ground_truth_ratings import GROUND_TRUTH_RATINGS
    from app.corpus.cold_start_fixtures import COLD_START_FIXTURES
except ImportError as e:
    print(f"WARNING: Could not import corpus data: {e}")
    SEED_ITEMS = []
    GROUND_TRUTH_RATINGS = []
    COLD_START_FIXTURES = []

try:
    from app.models.schemas import UserPersona, Context
    from app.core.retriever import Retriever
    from app.core.ranker import Ranker
    from app.core.cold_start import ColdStart
    PIPELINE_AVAILABLE = True
except ImportError as e:
    print(f"WARNING: Pipeline not available: {e}")
    PIPELINE_AVAILABLE = False

try:
    from rouge_score import rouge_scorer as _rouge_scorer
    ROUGE_AVAILABLE = True
except ImportError:
    ROUGE_AVAILABLE = False

NIGERIAN_MARKERS = ["omo", "abeg", "sha", "na", "dey", "wahala", "jare", "nawa"]


# ---------------------------------------------------------------------------
# Core metric functions
# ---------------------------------------------------------------------------

def compute_rmse(pairs: List[Tuple[float, float]]) -> float:
    """RMSE over (predicted, actual) pairs."""
    if not pairs:
        return 0.0
    return math.sqrt(sum((p - a) ** 2 for p, a in pairs) / len(pairs))


def compute_ndcg(relevances: List[float], k: int = 10) -> float:
    """
    NDCG@k. relevances must be in actual ranked order (not pre-sorted).
    Formula: DCG(actual[:k]) / DCG(ideal[:k]).
    """
    if not relevances:
        return 0.0
    actual = relevances[:k]
    ideal = sorted(relevances, reverse=True)[:k]
    dcg  = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(actual))
    idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def get_interaction_bucket(past_reviews: list) -> str:
    """Categorise user by number of past interactions."""
    n = len(past_reviews) if past_reviews else 0
    if n <= 2:
        return "1-2"
    if n <= 5:
        return "3-5"
    if n <= 10:
        return "6-10"
    return "10+"


def score_relevance(item: dict, persona: dict, context: dict) -> float:
    """Granular relevance scoring (mirrors ablation.py)."""
    rel = 0.0
    if item.get("category") in persona.get("interests", []):
        rel += 1.0
    ctx_loc = (context.get("location") or "").lower()
    item_loc = (item.get("location") or "").lower()
    if ctx_loc and item_loc and (ctx_loc in item_loc or item_loc in ctx_loc):
        rel += 0.5
    price = item.get("price_naira", 0) or 0
    budget = persona.get("budget", 1) or 1
    if price > 0:
        ratio = price / budget
        if ratio <= 1.0:
            rel += 0.5
        elif ratio <= 1.5:
            rel += 0.3
        elif ratio <= 2.0:
            rel += 0.1
    item_rating = item.get("rating", 0) or item.get("avg_rating", 0) or 0
    if item_rating:
        rel += 0.4 * (float(item_rating) / 5.0)
    return min(3.0, max(0.0, rel))


def detect_cross_domain(recommendations: List[Dict]) -> Dict:
    """Count items with cross_domain_tags and compute diversity ratio."""
    cross_count = 0
    categories = set()
    for rec in recommendations[:10]:
        categories.add(rec.get("category", ""))
        if rec.get("cross_domain_tags"):
            cross_count += 1
    return {
        "cross_domain_items": cross_count,
        "cross_domain_ratio": round(cross_count / 10.0, 3),
        "unique_categories": len(categories),
        "diversity_score": round(len(categories) / 10.0, 3),
        "passes": cross_count >= 2,
    }


# ---------------------------------------------------------------------------
# Evaluation runners
# ---------------------------------------------------------------------------

def evaluate_rmse_from_ground_truth(sample_size: int = 500) -> Dict:
    """
    Compute RMSE by running RatingPredictor against GROUND_TRUTH_RATINGS.

    Ground truth schema: {pair_id, user_id, item_id, actual_rating, user_archetype, context}
    There is no 'predicted_rating' field — we generate predictions via RatingPredictor.
    Uses a random sample of up to `sample_size` pairs to keep runtime reasonable.
    """
    if not GROUND_TRUTH_RATINGS:
        return {"error": "GROUND_TRUTH_RATINGS not loaded", "n": 0}

    try:
        from app.ml.rating_predictor import RatingPredictor
        from app.core.config import settings
    except ImportError as e:
        return {"error": f"RatingPredictor unavailable: {e}", "n": 0}

    predictor = RatingPredictor()
    sample = GROUND_TRUTH_RATINGS
    if len(sample) > sample_size:
        rng = random.Random(42)  # deterministic sample
        sample = rng.sample(GROUND_TRUTH_RATINGS, sample_size)

    # Build item lookup for price/description
    item_lookup = {item["item_id"]: item for item in SEED_ITEMS}

    archetype_pairs: Dict[str, List[Tuple]] = defaultdict(list)
    all_pairs: List[Tuple[float, float]] = []

    for entry in sample:
        actual = entry.get("actual_rating")
        if actual is None:
            continue

        # Build a minimal persona from ground truth row
        archetype_raw = entry.get("user_archetype", "default") or "default"
        # Normalise to display form
        arch_display = {
            "haggler": "Haggler",
            "big_woman": "Big Woman",
            "community": "Community Validator",
            "default": "Default",
        }.get(archetype_raw.lower(), archetype_raw.title())

        persona = {
            "name": entry.get("user_id", "user"),
            "archetype": arch_display,
            "budget": 50000,          # neutral default — no budget in GT
            "price_sensitivity": "high" if "haggler" in archetype_raw.lower() else "medium",
            "past_reviews": [],
        }

        item = item_lookup.get(entry.get("item_id", ""), {})
        product = {
            "name": item.get("name", "item"),
            "description": item.get("description", ""),
            "price_naira": item.get("price_naira", 0),
            "category": item.get("category", ""),
        }

        try:
            result = predictor.predict_probabilistic(persona, product)
            predicted = result.get("rating", 3.0)
        except Exception:
            predicted = 3.0

        pair = (float(predicted), float(actual))
        all_pairs.append(pair)
        archetype_pairs[arch_display].append(pair)

    if not all_pairs:
        return {"error": "No valid (predicted, actual) pairs computed", "n": 0}

    overall_rmse = compute_rmse(all_pairs)
    per_archetype = {
        arch: round(compute_rmse(pairs), 4)
        for arch, pairs in archetype_pairs.items()
    }
    return {
        "overall_rmse": round(overall_rmse, 4),
        "n": len(all_pairs),
        "per_archetype": per_archetype,
    }


def evaluate_ndcg_by_bucket(test_cases: List[Dict]) -> Dict:
    """
    Compute NDCG@10 broken down by interaction bucket.
    Requires PIPELINE_AVAILABLE (Retriever + Ranker).
    """
    if not PIPELINE_AVAILABLE:
        return {"error": "Pipeline (Retriever/Ranker) not available"}

    retriever = Retriever()
    ranker = Ranker()
    cold_start = ColdStart()

    bucket_ndcgs: Dict[str, List[float]] = defaultdict(list)
    overall_ndcgs: List[float] = []

    for case in test_cases:
        persona_raw = case["persona"]
        context_raw = case["context"]
        bucket = get_interaction_bucket(persona_raw.get("past_reviews", []))

        try:
            p = UserPersona(**persona_raw)
            c = Context(**context_raw)
            candidates = retriever.filter(p, c)
            analysis = {
                "preferred_categories": p.interests or [],
                "priorities": ["authentic", "value"],
                "reasoning": "Eval run",
            }
            ranked = ranker.score(candidates, analysis, p, c)
            if not persona_raw.get("past_reviews"):
                ranked = cold_start.adjust(ranked, p)

            top_10 = ranked[:10]
            relevances = [score_relevance(item, persona_raw, context_raw) for item in top_10]
            ndcg = compute_ndcg(relevances, k=10)

        except Exception as e:
            ndcg = 0.0

        overall_ndcgs.append(ndcg)
        bucket_ndcgs[bucket].append(ndcg)

    result = {
        "overall_ndcg_at_10": round(statistics.mean(overall_ndcgs), 4) if overall_ndcgs else 0,
        "overall_std": round(statistics.stdev(overall_ndcgs), 4) if len(overall_ndcgs) > 1 else 0,
        "n": len(overall_ndcgs),
        "by_interaction_bucket": {
            bucket: {
                "ndcg": round(statistics.mean(vals), 4),
                "n": len(vals),
            }
            for bucket, vals in bucket_ndcgs.items()
        },
    }
    return result


def evaluate_cross_domain_diversity(test_cases: List[Dict]) -> Dict:
    """Run recommendations and measure cross-domain diversity."""
    if not PIPELINE_AVAILABLE:
        return {"error": "Pipeline not available"}

    retriever = Retriever()
    ranker = Ranker()
    cold_start = ColdStart()

    cross_ratios = []
    diversity_scores = []

    for case in test_cases:
        persona_raw = case["persona"]
        context_raw = case["context"]
        try:
            p = UserPersona(**persona_raw)
            c = Context(**context_raw)
            candidates = retriever.filter(p, c)
            analysis = {
                "preferred_categories": p.interests or [],
                "priorities": ["authentic", "value"],
                "reasoning": "Diversity eval",
            }
            ranked = ranker.score(candidates, analysis, p, c)
            if not persona_raw.get("past_reviews"):
                ranked = cold_start.adjust(ranked, p)

            stats = detect_cross_domain(ranked[:10])
            cross_ratios.append(stats["cross_domain_ratio"])
            diversity_scores.append(stats["diversity_score"])
        except Exception:
            cross_ratios.append(0.0)
            diversity_scores.append(0.0)

    return {
        "avg_cross_domain_ratio": round(statistics.mean(cross_ratios), 4) if cross_ratios else 0,
        "avg_diversity_score": round(statistics.mean(diversity_scores), 4) if diversity_scores else 0,
        "n": len(cross_ratios),
    }


# ---------------------------------------------------------------------------
# Main scorecard
# ---------------------------------------------------------------------------

def run_full_evaluation():
    # Load test cases from ablation for consistent ground truth
    try:
        from ablation import TEST_CASES
    except ImportError:
        TEST_CASES = []

    print("\n" + "=" * 65)
    print(" TASK B: RECOMMENDATION ENGINE EVALUATION SCORECARD")
    print("=" * 65)

    # --- RMSE ---
    print("\n[RMSE against ground truth ratings]")
    rmse_result = evaluate_rmse_from_ground_truth()
    if "error" in rmse_result:
        print(f"  Status : {rmse_result['error']}")
    else:
        rmse_val = rmse_result["overall_rmse"]
        print(f"  Overall RMSE : {rmse_val:.4f}  (n={rmse_result['n']}, target < 0.8)")
        print(f"  Status       : {'PASS' if rmse_val < 0.8 else 'FAIL'}")
        if rmse_result["per_archetype"]:
            print("  Per-archetype RMSE:")
            for arch, val in sorted(rmse_result["per_archetype"].items()):
                print(f"    {arch:<25} : {val:.4f}")

    # --- NDCG@10 by interaction bucket ---
    print("\n[NDCG@10 by interaction bucket]")
    if TEST_CASES:
        ndcg_result = evaluate_ndcg_by_bucket(TEST_CASES)
        if "error" in ndcg_result:
            print(f"  Status : {ndcg_result['error']}")
        else:
            overall = ndcg_result["overall_ndcg_at_10"]
            std     = ndcg_result["overall_std"]
            print(f"  Overall NDCG@10 : {overall:.4f}  std={std:.4f}  (n={ndcg_result['n']})")
            print(f"  Status          : {'PASS' if overall >= 0.5 else 'FAIL'}")
            print("  By interaction bucket:")
            for bucket in ["1-2", "3-5", "6-10", "10+"]:
                b = ndcg_result["by_interaction_bucket"].get(bucket)
                if b:
                    print(f"    Bucket {bucket:<5} : NDCG={b['ndcg']:.4f}  (n={b['n']})")
    else:
        print("  No test cases available — import ablation.TEST_CASES")

    # --- Cross-domain diversity ---
    print("\n[Cross-domain Diversity]")
    if TEST_CASES:
        div_result = evaluate_cross_domain_diversity(TEST_CASES)
        if "error" in div_result:
            print(f"  Status : {div_result['error']}")
        else:
            print(f"  Avg cross-domain ratio : {div_result['avg_cross_domain_ratio']:.4f}  (target >= 0.2)")
            print(f"  Avg category diversity : {div_result['avg_diversity_score']:.4f}")
            print(f"  n                      : {div_result['n']}")

    # --- Nigerian Voice (on cold-start fixtures) ---
    print("\n[Nigerian Voice — Cold Start Fixtures]")
    if COLD_START_FIXTURES:
        marker_counts = []
        for fixture in COLD_START_FIXTURES:
            text = fixture.get("review_text", "") or fixture.get("text", "") or ""
            if text:
                count = sum(1 for m in NIGERIAN_MARKERS if m in text.lower())
                marker_counts.append(count)
        if marker_counts:
            avg = statistics.mean(marker_counts)
            pass_rate = sum(1 for c in marker_counts if c >= 2) / len(marker_counts)
            print(f"  Avg markers/review : {avg:.2f}  (target >= 2.0)")
            print(f"  Reviews >= 2 marks : {pass_rate*100:.1f}%")
        else:
            print("  No review texts in cold start fixtures")
    else:
        print("  COLD_START_FIXTURES not loaded")

    # --- Corpus summary ---
    print("\n" + "=" * 65)
    print(f"CORPUS: {len(SEED_ITEMS)} seed items | "
          f"{len(GROUND_TRUTH_RATINGS)} GT rating pairs | "
          f"{len(COLD_START_FIXTURES)} cold-start fixtures")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    print(f"Loaded {len(SEED_ITEMS)} seed items.")
    print(f"Loaded {len(GROUND_TRUTH_RATINGS)} ground truth ratings.")
    print(f"Loaded {len(COLD_START_FIXTURES)} cold start fixtures.")
    run_full_evaluation()
