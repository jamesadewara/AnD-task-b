import json
import os

_FILE_PATH = os.path.join(os.path.dirname(__file__), "data", "merged_ground_truth.json")

with open(_FILE_PATH, "r", encoding="utf-8") as f:
    GROUND_TRUTH_RATINGS = json.load(f)
