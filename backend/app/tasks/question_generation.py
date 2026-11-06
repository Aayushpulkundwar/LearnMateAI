import asyncio
from datetime import datetime, timezone
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.db import SyncSessionLocal
from app.models.chunk import Chunk
from app.models.learning import Chapter, Question, QuestionGenerationJob, Subject, Topic
from app.services.llm_service import llm_service
from app.services.embedding_service import embedding_service
from app.services.question_bank_service import build_generation_prompt, parse_candidates, persist_candidate


@celery_app.task(bind=True, max_retries=2, default_retry_delay=15)
def generate_question_bank_task(self, job_id: str):
    session = SyncSessionLocal()
    try:
        job = session.query(QuestionGenerationJob).filter(QuestionGenerationJob.id == UUID(job_id)).first()
        if not job:
            raise ValueError("Question generation job not found.")
        if job.status == "completed":
            return {"job_id": job_id, "status": "completed", "idempotent": True}
        job.status = "processing"
        session.commit()
        topic = session.query(Topic).filter(Topic.id == job.topic_id).first()
        topic_embedding = embedding_service.embed_text(topic.name)
        chunks = (
            session.query(Chunk)
            .filter(Chunk.document_id == job.document_id, Chunk.embedding.is_not(None))
            .order_by(Chunk.embedding.cosine_distance(topic_embedding))
            .limit(max(job.requested_count * 3, 8))
            .all()
        )
        if not topic or not chunks:
            raise ValueError("No source chunks are available for the requested document/topic.")
        prompt = build_generation_prompt(topic_name=topic.name, requested_count=job.requested_count, difficulty_distribution=job.difficulty_distribution, chunks=chunks)
        raw = asyncio.run(llm_service.generate(prompt, "You generate rigorous textbook MCQs. Output valid JSON only."))
        candidates = parse_candidates(raw)
        source_chunks = {chunk.id: chunk for chunk in chunks}
        existing = [row[0] for row in session.query(Question.question_text).filter(Question.topic_id == job.topic_id).all()]
        generated = rejected = 0
        for candidate in candidates:
            outcome = persist_candidate(session, candidate, subject_id=job.subject_id, chapter_id=job.chapter_id, topic_id=job.topic_id, document_id=job.document_id, source_chunks=source_chunks, existing_texts=existing)
            if outcome in {"validated", "review"}:
                generated += 1
                existing.append(candidate.question_text)
            else:
                rejected += 1
        job.status, job.generated_count, job.rejected_count, job.completed_at = "completed", generated, rejected, datetime.now(timezone.utc)
        session.commit()
        return {"job_id": job_id, "status": job.status, "generated": generated, "rejected": rejected}
    except Exception as exc:
        session.rollback()
        job = session.query(QuestionGenerationJob).filter(QuestionGenerationJob.id == UUID(job_id)).first()
        if job:
            job.status, job.error_message, job.completed_at = "failed", str(exc)[:2000], datetime.now(timezone.utc)
            session.commit()
        raise
    finally:
        session.close()
