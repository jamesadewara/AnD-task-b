# ============================================================
# COLD-START FIXTURES FOR TASK B (Recommendations Project)
# ============================================================

COLD_START_FIXTURES = [
    {
        "fixture_id": "cs_t01",
        "scenario": "zero_history",
        "user_profile": {
            "user_id": "cs_dayo",
            "age_range": "25-34",
            "location": "Lagos",
            "archetype": "haggler",
            "stated_preferences": ["cheap food", "fast tech", "bus park snacks"],
            "budget_naira": 4000,
            "occupation": "bus conductor",
            "purchase_history": []
        },
        "expected_recommendation_contains": ["street_food", "budget", "value"],
        "expected_recommendation_excludes": ["luxury", "fine dining"],
        "evaluation_notes": "Should recommend Ewa Agoyin or Roasted Corn. Budget is very tight."
    },
    {
        "fixture_id": "cs_t02",
        "scenario": "zero_history",
        "user_profile": {
            "user_id": "cs_hauwa",
            "age_range": "35-44",
            "location": "Sokoto",
            "archetype": "big_woman",
            "stated_preferences": ["traditional luxury", "gold jewelry", "fine fabrics"],
            "budget_naira": 300000,
            "occupation": "contractor",
            "purchase_history": []
        },
        "expected_recommendation_contains": ["fashion", "luxury", "prestige"],
        "expected_recommendation_excludes": ["street_food", "cheap"],
        "evaluation_notes": "Should recommend Coral Beads or Designer Agbada."
    },
    {
        "fixture_id": "cs_t03",
        "scenario": "zero_history",
        "user_profile": {
            "user_id": "cs_obi",
            "age_range": "18-24",
            "location": "Port Harcourt",
            "archetype": "community",
            "stated_preferences": ["afrobeats", "nightlife", "gadgets"],
            "budget_naira": 50000,
            "occupation": "student",
            "purchase_history": []
        },
        "expected_recommendation_contains": ["community_events", "music", "trending"],
        "expected_recommendation_excludes": ["traditional", "boring"],
        "evaluation_notes": "Should recommend Burna Boy Live or Gidi Culture Fest."
    },
    {
        "fixture_id": "cs_t04",
        "scenario": "minimal_history",
        "user_profile": {
            "user_id": "cs_amaka",
            "age_range": "25-34",
            "location": "Abuja",
            "archetype": "default",
            "stated_preferences": ["healthy meals", "skincare", "peaceful spots"],
            "budget_naira": 20000,
            "occupation": "nurse",
            "purchase_history": [
                {"item_id": "wl_001", "rating": 5.0} # Shea Butter
            ]
        },
        "expected_recommendation_contains": ["wellness", "dining", "natural"],
        "expected_recommendation_excludes": ["nightlife", "loud"],
        "evaluation_notes": "Should leverage Shea Butter interest to recommend Aromatherapy Massage or Zobo."
    },
    {
        "fixture_id": "cs_t05",
        "scenario": "minimal_history",
        "user_profile": {
            "user_id": "cs_emeka",
            "age_range": "45-54",
            "location": "Owerri",
            "archetype": "haggler",
            "stated_preferences": ["local soup", "sturdy tech", "traditional clothes"],
            "budget_naira": 15000,
            "occupation": "electrician",
            "purchase_history": [
                {"item_id": "el_011", "rating": 4.8} # Rechargeable Fan
            ]
        },
        "expected_recommendation_contains": ["electronics", "street_food", "essential"],
        "expected_recommendation_excludes": ["luxury", "international"],
        "evaluation_notes": "Should recommend Isiewu or Zinox Power Bank based on utility history."
    },
    {
        "fixture_id": "cs_t06",
        "scenario": "minimal_history",
        "user_profile": {
            "user_id": "cs_funke",
            "age_range": "25-34",
            "location": "Ilorin",
            "archetype": "community",
            "stated_preferences": ["trending movies", "family gatherings", "fashion accessories"],
            "budget_naira": 10000,
            "occupation": "seamstress",
            "purchase_history": [
                {"item_id": "nw_010", "rating": 5.0} # Tribe Called Judah
            ]
        },
        "expected_recommendation_contains": ["nollywood", "fashion", "family"],
        "expected_recommendation_excludes": ["high-tech", "luxury dining"],
        "evaluation_notes": "Should recommend Battle on Buka Street or Handmade Fila."
    },
    {
        "fixture_id": "cs_t07",
        "scenario": "cross_domain",
        "user_profile": {
            "user_id": "cs_tunde",
            "age_range": "35-44",
            "location": "Akure",
            "archetype": "default",
            "stated_preferences": ["farming", "rural development", "satellite tv"],
            "budget_naira": 80000,
            "occupation": "agriprenuer",
            "purchase_history": [
                {"item_id": "el_012", "rating": 5.0} # Starlink
            ]
        },
        "expected_recommendation_contains": ["tech", "electronics", "work"],
        "expected_recommendation_excludes": ["nightlife", "fast fashion"],
        "evaluation_notes": "Should bridge satellite interest to MTN 5G Router or Power Bank."
    },
    {
        "fixture_id": "cs_t08",
        "scenario": "cross_domain",
        "user_profile": {
            "user_id": "cs_zara",
            "age_range": "18-24",
            "location": "Zaria",
            "archetype": "community",
            "stated_preferences": ["islamic art", "traditional music", "henna wellness"],
            "budget_naira": 12000,
            "occupation": "student",
            "purchase_history": [
                {"item_id": "ce_009", "rating": 4.9} # Nupe Festival
            ]
        },
        "expected_recommendation_contains": ["culture", "wellness", "heritage"],
        "expected_recommendation_excludes": ["nightlife", "alcohol-related"],
        "evaluation_notes": "Should bridge festival interest to Masa or Kilishi."
    }
]
