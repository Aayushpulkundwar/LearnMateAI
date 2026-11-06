from fastapi import APIRouter
from app.api.routes.documents import router as documents_router
from app.api.routes.query import router as query_router
from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.students import router as students_router
from app.api.routes.questions import router as questions_router
from app.api.routes.assessments import router as assessments_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.mastery import router as mastery_router
from app.api.routes.learning import router as learning_router
from app.api.routes.curriculum import router as curriculum_router

api_router = APIRouter()

api_router.include_router(health_router, prefix="/health", tags=["Health"])
api_router.include_router(documents_router, prefix="/documents", tags=["Textbook Ingestion & Documents"])
api_router.include_router(query_router, prefix="/query", tags=["Textbook RAG & Learning Features"])
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication & Student Profiles"])
api_router.include_router(students_router, prefix="/students", tags=["Student Profiles"])
api_router.include_router(questions_router, prefix="/questions", tags=["Administrative Question Bank"])
api_router.include_router(assessments_router, prefix="/assessments", tags=["Student Diagnostic Assessments"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Student Performance Analytics"])
api_router.include_router(mastery_router, prefix="/mastery", tags=["Concept Mastery"])
api_router.include_router(learning_router, prefix="/learning", tags=["Adaptive Learning"])
api_router.include_router(curriculum_router, prefix="/curriculum", tags=["Authorized Curriculum"])
