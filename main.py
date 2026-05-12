import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import setup_logging
from app.api.v1.endpoints.recommendations import router as recommendations_router

# Initialize logging
setup_logging()

app = FastAPI(
    title=f"{settings.APP_NAME} - Task B",
    description="DSN X BCT LLM Agent Challenge - Task B: Recommendation Engine",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "task-b-recommendation"}

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Task B Recommendation Service is running", "port": 8001}

# Register API Router
app.include_router(recommendations_router, prefix="/api/v1/recommendations", tags=["Recommendations"])

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
