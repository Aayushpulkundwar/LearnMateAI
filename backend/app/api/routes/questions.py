from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin
from app.core.db import get_async_db
from app.models.document import Document
from app.models.learning import Chapter, Question, QuestionGenerationJob, Student, Subject, Topic
from app.schemas.question_bank import GenerationStatusResponse, QuestionBankSummary, QuestionGenerationRequest
from app.tasks.question_generation import generate_question_bank_task
from uuid import UUID

router = APIRouter()


@router.post("/generate", response_model=GenerationStatusResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_questions(payload: QuestionGenerationRequest, admin: Student = Depends(require_admin), db: AsyncSession = Depends(get_async_db)):
    topic = await db.scalar(select(Topic).join(Chapter).where(Topic.id == payload.topic_id, Topic.chapter_id == payload.chapter_id, Chapter.subject_id == payload.subject_id))
    document = await db.scalar(select(Document).where(Document.id == payload.document_id, Document.processing_status == "completed"))
    if not topic or not document:
        raise HTTPException(status_code=422, detail="Subject, chapter, topic, or completed source document is invalid.")
    # Legacy documents intentionally remain usable.  Once a document has been
    # mapped, however, generation cannot attach it to another curriculum node.
    if document.subject_id is not None and document.subject_id != payload.subject_id:
        raise HTTPException(status_code=422, detail="Document is mapped to a different subject.")
    if document.chapter_id is not None and document.chapter_id != payload.chapter_id:
        raise HTTPException(status_code=422, detail="Document is mapped to a different chapter.")
    job = QuestionGenerationJob(subject_id=payload.subject_id, chapter_id=payload.chapter_id, topic_id=payload.topic_id, document_id=payload.document_id, requested_count=payload.batch_size, difficulty_distribution=payload.difficulty_distribution, created_by_user_id=admin.user_id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    generate_question_bank_task.delay(str(job.id))
    return GenerationStatusResponse(task_id=job.id, status=job.status, generated_count=0, rejected_count=0)


@router.get("/generation-status/{task_id}", response_model=GenerationStatusResponse)
async def generation_status(task_id: UUID, admin: Student = Depends(require_admin), db: AsyncSession = Depends(get_async_db)):
    job = await db.scalar(select(QuestionGenerationJob).where(QuestionGenerationJob.id == task_id))
    if not job:
        raise HTTPException(status_code=404, detail="Generation task not found.")
    return GenerationStatusResponse(task_id=job.id, status=job.status, generated_count=job.generated_count, rejected_count=job.rejected_count, error_message=job.error_message)


@router.get("/bank-summary", response_model=QuestionBankSummary)
async def bank_summary(admin: Student = Depends(require_admin), db: AsyncSession = Depends(get_async_db)):
    total = await db.scalar(select(func.count(Question.id))) or 0
    validated = await db.scalar(select(func.count(Question.id)).where(Question.validation_status == "validated")) or 0
    review = await db.scalar(select(func.count(Question.id)).where(Question.validation_status == "review")) or 0
    active_jobs = await db.scalar(select(func.count(QuestionGenerationJob.id)).where(QuestionGenerationJob.status.in_(["pending", "processing"]))) or 0
    return QuestionBankSummary(total_questions=total, validated_questions=validated, review_questions=review, jobs_pending_or_processing=active_jobs)
