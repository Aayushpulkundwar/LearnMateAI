import logging
from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_db
from app.core.config import settings
from app.api.dependencies import get_current_student, require_admin
from app.models.document import Document
from app.models.learning import Student, Subject
from app.schemas.document import DocumentResponse, DocumentStatusResponse
from app.services.minio_service import minio_service
from app.services.document_curriculum_service import CurriculumAssociationError, validate_document_curriculum
from app.services.curriculum_authorization import resolve_authorized_scope
from app.tasks.ingestion import ingest_document_task

logger = logging.getLogger(__name__)

router = APIRouter()


async def _read_and_rewind_upload(file: UploadFile) -> tuple[int, object]:
    """Bound and verify a PDF upload before it reaches object storage."""
    contents = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(contents) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="PDF exceeds the upload size limit.")
    if not contents.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Uploaded file is not a valid PDF.")
    await file.seek(0)
    return len(contents), file.file


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    title: str = Form(...),
    subject: Optional[str] = Form(None),
    grade: Optional[str] = Form(None),
    chapter: Optional[str] = Form(None),
    grade_id: Optional[UUID] = Form(None),
    subject_id: Optional[UUID] = Form(None),
    chapter_id: Optional[UUID] = Form(None),
    file: UploadFile = File(...),
    admin: Student = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Upload textbook PDF:
    1. Stores raw PDF in MinIO object storage.
    2. Inserts Document record in DB with processing_status = 'pending'.
    3. Dispatches async Celery task (ingest_document_task) for offline chunking & vector embedding.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF textbook files are supported.")
    try:
        await validate_document_curriculum(
            db, grade_id=grade_id, subject_id=subject_id, chapter_id=chapter_id,
        )
    except CurriculumAssociationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    doc_id = uuid4()
    # Do not preserve an untrusted client filename in the object key.
    object_name = f"{doc_id}.pdf"
    minio_path = None

    try:
        # Reading for length inspection advances UploadFile to EOF; rewind it
        # before passing the same stream to MinIO.
        content_length, upload_stream = await _read_and_rewind_upload(file)
        minio_path = minio_service.upload_file(
            object_name=object_name,
            file_data=upload_stream,
            length=content_length,
            content_type=file.content_type or "application/pdf"
        )

        document = Document(
            id=doc_id,
            title=title,
            subject=subject,
            grade=grade,
            chapter=chapter,
            grade_id=grade_id,
            subject_id=subject_id,
            chapter_id=chapter_id,
            processing_status="pending",
            minio_path=minio_path
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)

        # Dispatch background Celery task
        ingest_document_task.delay(str(doc_id))

        return document

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        if minio_path:
            try:
                minio_service.remove_file(minio_path)
            except Exception:
                logger.warning("upload_cleanup_failed document_id=%s", doc_id, exc_info=True)
        logger.exception("document_upload_failed document_id=%s", doc_id)
        raise HTTPException(status_code=500, detail="Document upload failed. Please try again later.")


@router.get("/", response_model=List[DocumentResponse])
async def list_documents(
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    subject_id: Optional[UUID] = None,
    chapter_id: Optional[UUID] = None,
    student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db),
):
    """List all ingested textbooks with optional subject and grade filters."""
    query = select(Document)
    if not student.user.is_admin:
        # Client filters can narrow a list but never broaden a student's grade-bound scope.
        if subject_id is not None or chapter_id is not None:
            await resolve_authorized_scope(db, student, subject_id=subject_id, chapter_id=chapter_id)
        science = select(Subject.id).where(Subject.grade_id == student.grade_id, Subject.name.ilike("Science"))
        query = query.where(Document.grade_id == student.grade_id, Document.subject_id.in_(science))
        if subject_id is not None:
            query = query.where(Document.subject_id == subject_id)
        if chapter_id is not None:
            query = query.where(Document.chapter_id == chapter_id)

    result = await db.execute(query.order_by(Document.created_at.desc()))
    documents = result.scalars().all()
    return documents


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db),
):
    """Get textbook document details and processing status."""
    query = select(Document).where(Document.id == document_id)
    if not student.user.is_admin:
        science = select(Subject.id).where(Subject.grade_id == student.grade_id, Subject.name.ilike("Science"))
        query = query.where(Document.grade_id == student.grade_id, Document.subject_id.in_(science))
    result = await db.execute(query)
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: UUID,
    student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db),
):
    """Status check endpoint for tracking Celery worker progress & heartbeat."""
    query = select(Document).where(Document.id == document_id)
    if not student.user.is_admin:
        science = select(Subject.id).where(Subject.grade_id == student.grade_id, Subject.name.ilike("Science"))
        query = query.where(Document.grade_id == student.grade_id, Document.subject_id.in_(science))
    result = await db.execute(query)
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document
