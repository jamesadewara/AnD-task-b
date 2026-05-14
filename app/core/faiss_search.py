import json
import os
from typing import List, Dict, Optional

import faiss
import numpy as np
import warnings
from sentence_transformers import SentenceTransformer
from app.core.config import settings

# Suppress Hugging Face FutureWarning about resume_download
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub.file_download")

# CONFIG — points to where your merged files actually are
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # app/core/
# Go up one level: core → app, then into corpus/data
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "corpus", "data")
ITEMS_PATH = os.path.join(DATA_DIR, "merged_items.json")
INDEX_PATH = os.path.join(DATA_DIR, "faiss_flat_index.bin")
ID_MAP_PATH = os.path.join(DATA_DIR, "faiss_id_map.json")

BUILD_INDEX = not os.path.exists(INDEX_PATH)

class FaissItemStore:
    """
    Minimal wrapper: loads items + FAISS index, provides .search()
    """

    def __init__(self):
        # 1. Load items
        with open(ITEMS_PATH, "r", encoding="utf-8") as f:
            raw_items = json.load(f)
        self.items_by_id = {i["item_id"]: i for i in raw_items}
        self.item_list = raw_items  # keep ordered list

        # 2. Load or build FAISS index
        if BUILD_INDEX:
            print("[FAISS] No index found. Building now (one-time)...")
            self._build_index(raw_items)
        else:
            print("[FAISS] Loading existing index...")

        self.index = faiss.read_index(INDEX_PATH)
        with open(ID_MAP_PATH, "r") as f:
            self.id_map = json.load(f)  # {str(idx): item_id}
        self.idx_to_id = {int(k): v for k, v in self.id_map.items()}

        # 3. Load embedding model (384-dim, ~80MB, runs on CPU)
        self.model = SentenceTransformer(
            "all-MiniLM-L6-v2", 
            use_auth_token=settings.HF_TOKEN if settings.HF_TOKEN else None
        )
        print(f"[FAISS] Ready: {self.index.ntotal} items loaded.")

    def _build_index(self, items: List[dict]):
        """One-time index build from item descriptions."""
        model = SentenceTransformer(
            "all-MiniLM-L6-v2", 
            use_auth_token=settings.HF_TOKEN if settings.HF_TOKEN else None
        )
        texts = []
        for item in items:
            text = f"{item['name']}. {item['description']}. Tags: {', '.join(item.get('tags', []))}. "
            text += f"Location: {item['location']}. Price: ₦{item['price_naira']}."
            texts.append(text)

        embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
        embeddings = embeddings.astype("float32")
        faiss.normalize_L2(embeddings)  # cosine similarity via inner product

        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)
        faiss.write_index(index, INDEX_PATH)

        id_map = {i: item["item_id"] for i, item in enumerate(items)}
        with open(ID_MAP_PATH, "w") as f:
            json.dump(id_map, f)

        print(f"[FAISS] Index built: {index.ntotal} items, saved to {INDEX_PATH}")

    def _make_query(self, persona: dict, context: Optional[dict]) -> str:
        """Turn persona+context into a search query string."""
        parts = []
        interests = persona.get("interests", [])
        if interests:
            parts.append(" ".join(interests))

        if context:
            if context.get("occasion"):
                parts.append(context["occasion"])
            if context.get("mood"):
                parts.append(context["mood"])

        # Inject archetype signals so FAISS finds relevant semantic matches
        archetype = (persona.get("archetype") or "default").lower()
        if archetype == "haggler":
            parts.append("cheap budget-friendly value deal affordable")
        elif archetype == "big_woman":
            parts.append("luxury premium high-end exclusive classy")
        elif archetype == "community":
            parts.append("popular trending trusted classic busy")

        if not parts:
            parts = ["restaurant food dining"]  # generic fallback
        return " ".join(parts)

    def search(self, persona: dict, context: Optional[dict] = None, top_k: int = 100) -> List[dict]:
        """
        Returns top-k candidate items as dicts (with _faiss_score attached).
        Drop-in replacement for `for item in SEED_ITEMS:`.
        """
        query_text = self._make_query(persona, context)
        vec = self.model.encode([query_text], convert_to_numpy=True)
        vec = vec.astype("float32")
        faiss.normalize_L2(vec)

        distances, indices = self.index.search(vec, top_k)

        candidates = []
        for idx, score in zip(indices[0], distances[0]):
            if idx == -1:
                continue
            item_id = self.idx_to_id.get(int(idx))
            if not item_id:
                continue
            item = self.items_by_id.get(item_id)
            if item:
                item = dict(item)  # copy so we don't mutate original
                item["_faiss_score"] = float(score)
                candidates.append(item)
        return candidates


# ---------------------------------------------------------------------------
# BACKWARD COMPATIBILITY: if you literally just want a list of items
# ---------------------------------------------------------------------------
class SimpleItemLoader:
    """If you DON'T want FAISS yet, just use this to load JSON instead of hardcoded SEED_ITEMS."""

    def __init__(self, path: str = None):
        if path is None:
            path = ITEMS_PATH
        with open(path, "r", encoding="utf-8") as f:
            self.items = json.load(f)
        self.items_by_id = {i["item_id"]: i for i in self.items}

    def get_all(self) -> List[dict]:
        return self.items

    def get_by_id(self, item_id: str) -> Optional[dict]:
        return self.items_by_id.get(item_id)