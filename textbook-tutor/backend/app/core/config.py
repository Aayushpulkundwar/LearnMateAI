from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Textbook Tutor"
    API_V1_STR: str = "/api/v1"

    # Database
    POSTGRES_USER: str = "tutor"
    POSTGRES_PASSWORD: str = "tutorpass"
    POSTGRES_DB: str = "textbook_db"
    DATABASE_URL: str = "postgresql+asyncpg://tutor:tutorpass@postgres:5432/textbook_db"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://tutor:tutorpass@postgres:5432/textbook_db"

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
    LLM_MODEL: str = "llama3.1"

    # Strict RAG Relevance Threshold
    RELEVANCE_THRESHOLD: float = 0.6

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
