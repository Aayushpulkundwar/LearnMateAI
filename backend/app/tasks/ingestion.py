from datetime import datetime, timezone
import logging
import uuid
from celery import shared_task
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.db import SyncSessionLocal
from app.models.document import Document
from app.models.chunk import Chunk
from app.core.config import settings
from app.services.minio_service import minio_service
from app.services.pdf_extraction import extract_pdf_pages
from app.services.text_chunking import chunk_extracted_pages
from app.services.embedding_service import embedding_service


logger = logging.getLogger(__name__)


def _update_heartbeat(session: Session, document: Document, status: str = None) -> None:
    """Helper to update heartbeat_at timestamp and optional status for stuck worker detection."""
    document.heartbeat_at = datetime.now(timezone.utc)
    if status:
        document.processing_status = status
    session.add(document)
    session.commit()
    session.refresh(document)


def _build_chunk_objects(document: Document, text_chunks, embeddings) -> list[Chunk]:
    """Pair final text chunks with validated embeddings before any DB write."""
    if len(text_chunks) != len(embeddings):
        raise ValueError(
            f"Embedding count {len(embeddings)} does not match chunk count {len(text_chunks)}."
        )
    return [
        Chunk(
            id=uuid.uuid4(),
            document_id=document.id,
            content=text_chunk.content,
            embedding=embedding,
            page_number=text_chunk.page_number,
            chapter=document.chapter,
            chunk_index=text_chunk.chunk_index,
        )
        for text_chunk, embedding in zip(text_chunks, embeddings)
    ]


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def ingest_document_task(self, document_id: str):
    """
    Offline Celery Ingestion Pipeline:
    - Idempotent and resumable processing of raw textbook PDFs.
    - Updates heartbeat_at at EVERY major checkpoint (fetch, parse, chunk, embed, store).
    """
    doc_uuid = uuid.UUID(document_id)
    session: Session = SyncSessionLocal()
    stage = "initialization"

    try:
        document = session.query(Document).filter(Document.id == doc_uuid).first()
        if not document:
            raise ValueError(f"Document with ID {document_id} not found in database.")

        # Checkpoint 1: Mark status processing and update heartbeat
        stage = "processing"
        _update_heartbeat(session, document, status="processing")

        # Checkpoint 2: Download raw PDF bytes from MinIO object storage
        # TODO: Implement local disk buffer caching if processing large multi-hundred page PDFs
        stage = "download"
        pdf_bytes = minio_service.download_file(document.minio_path)
        _update_heartbeat(session, document)

        # Checkpoint 3: Extract clean text per physical PDF page.
        stage = "extraction"
        extracted_pages = extract_pdf_pages(pdf_bytes)
        _update_heartbeat(session, document)

        # Checkpoint 4: Chunk every page independently. Chunk indexes are
        # document-monotonic, while page_number remains source provenance.
        stage = "chunking"
        text_chunks = chunk_extracted_pages(
            extracted_pages,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )

        # Checkpoint 5: Generate exactly one validated BGE-M3 vector for each
        # non-empty final chunk. No DB writes occur before all vectors validate.
        stage = "embedding"
        logger.info("Generating embeddings: document_id=%s chunks=%s", document_id, len(text_chunks))
        embeddings = embedding_service.embed_texts([chunk.content for chunk in text_chunks]) if text_chunks else []
        chunk_objects = _build_chunk_objects(document, text_chunks, embeddings)
        
        _update_heartbeat(session, document)

        # Checkpoint 6: Write fully prepared chunks into pgvector database table.
        # Delete existing chunks for idempotency if re-ingesting
        stage = "persistence"
        session.query(Chunk).filter(Chunk.document_id == document.id).delete()
        session.bulk_save_objects(chunk_objects)
        
        # Mark completed & update final heartbeat
        _update_heartbeat(session, document, status="completed")

        return {"document_id": document_id, "status": "completed", "chunks_count": len(chunk_objects)}

    except Exception as exc:
        logger.exception("Document ingestion failed: document_id=%s stage=%s", document_id, stage)
        session.rollback()
        # Fetch document again to safely update status to failed
        doc_failed = session.query(Document).filter(Document.id == doc_uuid).first()
        if doc_failed:
            _update_heartbeat(session, doc_failed, status="failed")
        raise exc
    finally:
        session.close()
