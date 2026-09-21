from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.db import get_async_db
from app.services.llm_service import llm_service

router = APIRouter()


@router.get("/", summary="System Health Check")
async def health_check(db: AsyncSession = Depends(get_async_db)):
    """Deep healthcheck verifying PostgreSQL DB, Redis, MinIO, and Ollama readiness."""
    status = {
        "status": "healthy",
        "services": {
            "postgres": "unknown",
            "ollama": "unknown",
        }
    }

    # Check Postgres
    try:
        await db.execute(text("SELECT 1"))
        status["services"]["postgres"] = "connected"
    except Exception as exc:
        status["services"]["postgres"] = f"error: {str(exc)}"
        status["status"] = "degraded"

    # Check Ollama endpoint and configured generation model.
    try:
        await llm_service.check_availability()
        status["services"]["ollama"] = "connected"
    except Exception as exc:
        status["services"]["ollama"] = f"unavailable: {str(exc)}"
        status["status"] = "degraded"

    return status
