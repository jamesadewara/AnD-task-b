import json
import os

_FILE_PATH = os.path.join(os.path.dirname(__file__), "data", "merged_cold_start_fixtures.json")

with open(_FILE_PATH, "r", encoding="utf-8") as f:
    COLD_START_FIXTURES = json.load(f)
