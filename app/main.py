import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import async_session
from app.routers import chat, documents, exercise, exercise_log, feedback, plans, schedule, users

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Fitness AI Service",
    description="AI-тренер и диетолог с RAG на базе книг по ЗОЖ",
    version="0.4.0",
    docs_url=None if settings.api_secret_key else "/docs",
    redoc_url=None if settings.api_secret_key else "/redoc",
    openapi_url=None if settings.api_secret_key else "/openapi.json",
)


@app.on_event("startup")
async def _preload_models():
    """Load embedding model in background so startup is fast but model is warm."""
    import asyncio

    async def _load():
        await asyncio.sleep(2)  # Let uvicorn finish startup first
        logging.getLogger(__name__).info("Loading embedding model...")
        from app.rag.embeddings import get_model
        get_model()
        logging.getLogger(__name__).info("Embedding model ready.")

    asyncio.create_task(_load())


# API key authentication middleware
@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    # Skip auth for health check
    if request.url.path == "/health":
        return await call_next(request)
    # Skip if no key configured (dev mode)
    if not settings.api_secret_key:
        return await call_next(request)
    api_key = request.headers.get("X-API-Key", "")
    if api_key != settings.api_secret_key:
        return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
    return await call_next(request)

logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(users.router)
app.include_router(chat.router)
app.include_router(plans.router)
app.include_router(schedule.router)
app.include_router(documents.router)
app.include_router(exercise.router)
app.include_router(exercise_log.router)
app.include_router(feedback.router)


@app.get("/health")
async def health():
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return {"status": "degraded", "db": "unavailable"}
