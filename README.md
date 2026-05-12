# AnD Task B: Personalization & Recommendation Engine

Stateless, agentic recommendation engine for the DSN X BCT LLM Agent Challenge. It leverages real-time reasoning to deliver culturally-grounded recommendations for Nigerian users.

## 🚀 Features
- **Stateless API**: No database used. Operates entirely on input context.
- **Agentic Workflow**: Implements a 6-step Retrieve-Reason-Rank-Validate pipeline.
- **Visible Reasoning**: Every response includes a mandatory `reasoning_chain` (CoT) for transparency.
- **Multi-Model Failover**: Automatic rotation between GLM-4.5, Nemotron-3, and Gemma-4 for maximum reliability.
- **Nigerian Context**: Deep cultural grounding for archetypes, locations, and occasions.

## 🚦 Setup

### 1. Environment Setup
Clone the example environment and add your OpenRouter API key:
```bash
cp .env.example .env
```
Then edit `.env`:
```env
OPENROUTER_API_KEY=your_key_here
```

### 2. Run with Docker
```bash
docker build -t and-task-b .
docker run -p 8001:8001 --env-file .env and-task-b
```
*(Note: Use `docker-compose up --build` if you prefer the orchestration layer)*

## ⚖️ Compliance & Disclosure
- **LLM**: Strictly uses the official OpenRouter SDK with free model failovers.
- **Data**: 0 external datasets used. 100% logic and seed-based reasoning.
- **Zero Search**: No vector databases or FAISS; pure agentic reasoning over context.