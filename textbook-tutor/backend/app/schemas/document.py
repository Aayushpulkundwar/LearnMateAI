from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class DocumentBase(BaseModel):
    title: str
    subject: Optional[str] = None
    grade: Optional[str] = None
    chapter: Optional[str] = None


class DocumentCreate(DocumentBase):
    pass


class DocumentResponse(DocumentBase):
    id: UUID
    processing_status: str
    heartbeat_at: Optional[datetime] = None
    minio_path: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentStatusResponse(BaseModel):
    id: UUID
    processing_status: str
    heartbeat_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
