import json
import os

_EXTERNAL = os.path.join(os.path.dirname(__file__), "data", "merged_items.json")
with open(_EXTERNAL, "r", encoding="utf-8") as f:
    SEED_ITEMS = json.load(f)