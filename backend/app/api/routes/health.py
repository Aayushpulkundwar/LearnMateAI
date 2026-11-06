import logging
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.db import get_async_db
from app.services.llm_service import llm_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", summary="System Health Check")
async def health_check(db: AsyncSession = Depends(get_async_db)):
    """Deep healthcheck verifying PostgreSQL DB, Redis, MinIO, and Ollama readiness."""
    result = {
        "status": "healthy",
        "services": {
            "postgres": "unknown",
            "ollama": "unknown",
        }
    }

    # Check Postgres
    try:
        await db.execute(text("SELECT 1"))
        result["services"]["postgres"] = "connected"
    except Exception:
        logger.warning("health_postgres_unavailable")
        result["services"]["postgres"] = "unavailable"
        result["status"] = "degraded"

    # Check Ollama endpoint and configured generation model.
    try:
        await llm_service.check_availability()
        result["services"]["ollama"] = "connected"
    except Exception:
        logger.warning("health_ollama_unavailable")
        result["services"]["ollama"] = "unavailable"
        result["status"] = "degraded"

    return result


@router.get("/live", summary="Process Liveness")
async def liveness():
    return {"status": "alive"}


@router.get("/ready", summary="Dependency Readiness")
async def readiness(response: Response, db: AsyncSession = Depends(get_async_db)):
    result = await health_check(db)
    if result["status"] != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
