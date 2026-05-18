# Judge Testing Guide — AnD Task B

## Quick Start
```bash
cd AnD-task-b
sudo docker compose up -d --build
```

## Health Check
```bash
curl http://127.0.0.1:8001/api/v1/health
```

---

## Test 1: Cold-Start Haggler (Price Sensitivity)
**Validates:** Inference from archetype/budget when history is empty.
**Expected:** Items under ₦5,000 (Haggler preference) with "value" tags ranked high. `cold_start_used: true`.

```bash
curl -X POST http://localhost:8001/api/v1/recommendations/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_persona": {
      "name": "Chinedu",
      "location": "Lagos",
      "archetype": "The Haggler",
      "interests": ["street_food"],
      "budget": 5000,
      "past_reviews": []
    },
    "context": {
      "location": "Lagos",
      "time_of_day": "evening",
      "occasion": "quick dinner",
      "conversation_history": []
    }
  }'
```

---

## Test 2: Cross-Domain Movie Night
**Validates:** Mixed category recommendations and `cross_domain: true`.
**Expected:** Mix of Nollywood movies and Street Food items.

```bash
curl -X POST http://localhost:8001/api/v1/recommendations/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_persona": {
      "name": "Kelechi",
      "location": "Port Harcourt",
      "archetype": "The Community Validator",
      "interests": ["nollywood", "street_food"],
      "budget": 10000,
      "past_reviews": [{"product_name": "Wedding Party", "rating": 5}]
    },
    "context": {
      "location": "Port Harcourt",
      "time_of_day": "night",
      "occasion": "movie night with friends",
      "conversation_history": []
    }
  }'
```

---

## Test 3: Multiturn Rejection Handling
**Validates:** Agentic filtering based on conversation history.
**Expected:** " RSVP Lagos" should be REMOVED because user says it is "too expensive".

```bash
curl -X POST http://localhost:8001/api/v1/recommendations/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_persona": {
      "name": "Amina",
      "location": "Abuja",
      "archetype": "The Big Woman",
      "interests": ["dining"],
      "budget": 100000,
      "past_reviews": []
    },
    "context": {
      "location": "Abuja",
      "occasion": "business dinner",
      "conversation_history": [
        {"role": "user", "message": "I want something nice"},
        {"role": "agent", "message": "How about RSVP Lagos?"},
        {"role": "user", "message": "No, that one is too expensive and far. Something in Abuja."}
      ]
    }
  }'
```

---

## Test 4: Hard Budget Extraction
**Validates:** Regex-based constraint extraction from chat.
**Expected:** ONLY items ₦20,000 or less should appear.

```bash
curl -X POST http://localhost:8001/api/v1/recommendations/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_persona": {
      "name": "Ibrahim",
      "interests": ["electronics"],
      "budget": 150000,
      "past_reviews": []
    },
    "context": {
      "conversation_history": [
        {"role": "user", "message": "I need a new phone but not more than ₦120000 please"}
      ]
    }
  }'
```
