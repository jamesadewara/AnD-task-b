from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from loguru import logger
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.core.logging import setup_logging

# Initialize logging as soon as possible
setup_logging()

# Import Routers
from app.api.v1.endpoints.recommendations import router as recommendations_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 [Lifespan] Starting up {settings.APP_NAME}")
    try:
        logger.info("🧠 [ML] Starting stateless recommendation service...")
        yield
    except Exception as e:
        logger.error(f"❌ [Lifespan] CRITICAL ERROR during startup: {e}")
        raise
    finally:
        logger.info(f"🛑 [Lifespan] Shutting down {settings.APP_NAME}...")
        logger.info("🏁 [Lifespan] Cleanup complete.")

 
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI(
    title=f"{settings.APP_NAME} - Task B",
    description="DSN X BCT LLM Agent Challenge - Task B: Contextual Recommendation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── Routes ─────────────────────────────────────────────────────────────────────


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    # Serves ReDoc using unpkg CDN instead of jsdelivr.net
    # jsdelivr is blocked by Edge/Safari tracking prevention
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
  <head>
    <title>{settings.APP_NAME} - API Docs</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body {{ margin: 0; padding: 0; }}</style>
  </head>
  <body>
    <redoc spec-url="/openapi.json"></redoc>
    <script src="https://unpkg.com/redoc@latest/bundles/redoc.standalone.js"></script>
  </body>
</html>
""")

@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "ok", 
        "service": "task-b-recommendation",
    }

@app.get("/api/v1/health/stream")
async def health_stream():
    from fastapi.responses import StreamingResponse
    import json
    import asyncio
    
    async def heartbeat():
        try:
            while True:
                yield f"data: {json.dumps({'status': 'ok', 'service': 'task-b'})}\n\n"
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            logger.info("Health stream for Task B closed.")
            
    return StreamingResponse(heartbeat(), media_type="text/event-stream")

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Task B service is running", "version": "1.0.0"}

# Register API Routers
app.include_router(recommendations_router, prefix="/api/v1/recommendations", tags=["Recommendations"])
