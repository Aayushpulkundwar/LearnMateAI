from fastapi import APIRouter
from app.api.routes.documents import router as documents_router
from app.api.routes.query import router as query_router
from app.api.routes.health import router as health_router

api_router = APIRouter()

api_router.include_router(health_router, prefix="/health", tags=["Health"])
api_router.include_router(documents_router, prefix="/documents", tags=["Textbook Ingestion & Documents"])
api_router.include_router(query_router, prefix="/query", tags=["Textbook RAG & Learning Features"])
