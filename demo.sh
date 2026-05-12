#!/bin/bash
set -e

echo "🚀 Starting AnD-task-b Deployment..."

# Check .env
if [ ! -f .env ]; then
    echo "Creating .env with defaults..."
    echo "APP_NAME=AnD-recommendation-engine" > .env
    echo "DEBUG=True" >> .env
    echo "LITELLM_MODEL_PRIMARY=openrouter/google/gemma-2-9b-it:free" >> .env
    echo "OPENROUTER_API_KEY=YOUR_KEY_HERE" >> .env
fi

# Build and Start
docker-compose build
docker-compose up -d

echo "⏳ Waiting for stabilization..."
sleep 8

# Verification
echo "🔍 Health Check:"
curl -s http://localhost:8001/health | grep "ok" && echo "✅ Task B Online"

echo "🧪 Running Test Case 1 (Haggler Cold-Start):"
curl -s -X POST http://localhost:8001/api/v1/recommendations/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_persona": {
      "name": "Chinedu",
      "archetype": "The Haggler",
      "interests": ["street_food"],
      "budget": 5000,
      "past_reviews": []
    },
    "context": {
      "location": "Lagos",
      "occasion": "quick dinner",
      "conversation_history": []
    }
  }' | python3 -m json.tool | grep -C 5 "reasoning_chain"

echo -e "\n✅ Setup complete! Full test guide in JUDGE_GUIDE.md"
