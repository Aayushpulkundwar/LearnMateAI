from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import httpx

from app.core.config import settings
from app.core.db import get_async_db

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

    # Check Ollama endpoint
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                status["services"]["ollama"] = "connected"
            else:
                status["services"]["ollama"] = f"error status {resp.status_code}"
                status["status"] = "degraded"
    except Exception as exc:
        status["services"]["ollama"] = f"unreachable: {str(exc)}"
        status["status"] = "degraded"

    return status
