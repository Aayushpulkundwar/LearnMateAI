from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_db
from app.models.document import Document
from app.schemas.document import DocumentResponse, DocumentStatusResponse
from app.services.minio_service import minio_service
from app.tasks.ingestion import ingest_document_task

router = APIRouter()


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    title: str = Form(...),
    subject: Optional[str] = Form(None),
    grade: Optional[str] = Form(None),
    chapter: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Upload textbook PDF:
    1. Stores raw PDF in MinIO object storage.
    2. Inserts Document record in DB with processing_status = 'pending'.
    3. Dispatches async Celery task (ingest_document_task) for offline chunking & vector embedding.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF textbook files are supported.")

    doc_id = uuid4()
    object_name = f"{doc_id}_{file.filename}"

    try:
        # Read file contents & upload to MinIO
        contents = await file.read()
        minio_path = minio_service.upload_file(
            object_name=object_name,
            file_data=file.file,
            length=len(contents),
            content_type=file.content_type or "application/pdf"
        )

        document = Document(
            id=doc_id,
            title=title,
            subject=subject,
            grade=grade,
            chapter=chapter,
            processing_status="pending",
            minio_path=minio_path
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)

        # Dispatch background Celery task
        ingest_document_task.delay(str(doc_id))

        return document

    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Document upload failed: {str(exc)}")


@router.get("/", response_model=List[DocumentResponse])
async def list_documents(
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
):
    """List all ingested textbooks with optional subject and grade filters."""
    query = select(Document)
    if subject:
        query = query.where(Document.subject == subject)
    if grade:
        query = query.where(Document.grade == grade)

    result = await db.execute(query.order_by(Document.created_at.desc()))
    documents = result.scalars().all()
    return documents


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Get textbook document details and processing status."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Status check endpoint for tracking Celery worker progress & heartbeat."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document
