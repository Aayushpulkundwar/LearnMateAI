from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "LearnMateAI"
    API_V1_STR: str = "/api/v1"

    # Database
    POSTGRES_USER: str = "tutor"
    POSTGRES_PASSWORD: str = "tutorpass"
    POSTGRES_DB: str = "learnmate_db"
    DATABASE_URL: str = "postgresql+asyncpg://tutor:tutorpass@postgres:5432/learnmate_db"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://tutor:tutorpass@postgres:5432/learnmate_db"

    # Redis (Celery)
    REDIS_URL: str = "redis://redis:6379/0"

    # MinIO Object Storage
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_EXTERNAL_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "textbooks"
    MINIO_SECURE: bool = False

    # Ollama Single Local Provider
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    EMBEDDING_MODEL: str = "bge-m3"
    EMBEDDING_DIM: int = 1024
    LLM_MODEL: str = "llama3.1:latest"
    OLLAMA_GENERATION_TIMEOUT_SECONDS: float = 300.0
    QUIZ_GENERATION_TIMEOUT_SECONDS: float = 900.0

    # Page-aware text chunking
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150
    OCR_ENABLED: bool = False
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024

    RETRIEVAL_TOP_K: int = 5
    RETRIEVAL_CANDIDATE_MULTIPLIER: int = 4
    RETRIEVAL_RRF_K: int = 60
    LEXICAL_RELEVANCE_THRESHOLD: float = 0.08
    CONTEXT_MIN_SIMILARITY: float = 0.50
    CONTEXT_MAX_SIMILARITY_DROP: float = 0.06
    RAG_MAX_CONTEXT_CHARS: int = 6000
    LLM_TEMPERATURE: float = 0.2

    # Strict RAG Relevance Threshold
    RELEVANCE_THRESHOLD: float = 0.55

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Authentication. Override JWT_SECRET_KEY in every non-development deployment.
    JWT_SECRET_KEY: str = "development-only-change-me-replace-with-32-byte-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    AUTH_COOKIE_NAME: str = "learnmate_session"
    AUTH_COOKIE_SECURE: bool = False

    PERFORMANCE_STRONG_THRESHOLD: float = 80.0
    PERFORMANCE_DEVELOPING_THRESHOLD: float = 50.0
    PERFORMANCE_MIN_QUESTIONS: int = 10
    PERFORMANCE_MIN_ATTEMPTS: int = 3
    MASTERY_EASY_WEIGHT: float = 1.0
    MASTERY_MEDIUM_WEIGHT: float = 1.5
    MASTERY_HARD_WEIGHT: float = 2.0
    MASTERY_PRIOR_MEAN: float = 0.5
    MASTERY_PRIOR_STRENGTH: float = 6.0
    MASTERY_INSUFFICIENT_EVIDENCE_COUNT: int = 3
    MASTERY_LOW_CONFIDENCE_COUNT: int = 8
    MASTERY_MODERATE_CONFIDENCE_COUNT: int = 20
    MASTERY_STRONG_THRESHOLD: float = 80.0
    MASTERY_DEVELOPING_THRESHOLD: float = 50.0

    @field_validator("CORS_ORIGINS")
    @classmethod
    def reject_wildcard_cors_with_credentials(cls, value: List[str]) -> List[str]:
        if "*" in value:
            raise ValueError("CORS_ORIGINS cannot contain '*' when cookie authentication is enabled.")
        return value

    def model_post_init(self, __context) -> None:
        if self.ENVIRONMENT.lower() in {"production", "staging"}:
            if self.JWT_SECRET_KEY == "development-only-change-me-replace-with-32-byte-secret":
                raise ValueError("JWT_SECRET_KEY must be configured outside development.")
            if not self.AUTH_COOKIE_SECURE:
                raise ValueError("AUTH_COOKIE_SECURE must be true outside development.")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
