from datetime import datetime, timezone
import uuid
from celery import shared_task
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.db import SyncSessionLocal
from app.models.document import Document
from app.models.chunk import Chunk
from app.services.minio_service import minio_service
from app.services.embedding_service import embedding_service


def _update_heartbeat(session: Session, document: Document, status: str = None) -> None:
    """Helper to update heartbeat_at timestamp and optional status for stuck worker detection."""
    document.heartbeat_at = datetime.now(timezone.utc)
    if status:
        document.processing_status = status
    session.add(document)
    session.commit()
    session.refresh(document)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def ingest_document_task(self, document_id: str):
    """
    Offline Celery Ingestion Pipeline:
    - Idempotent and resumable processing of raw textbook PDFs.
    - Updates heartbeat_at at EVERY major checkpoint (fetch, parse, chunk, embed, store).
    """
    doc_uuid = uuid.UUID(document_id)
    session: Session = SyncSessionLocal()

    try:
        document = session.query(Document).filter(Document.id == doc_uuid).first()
        if not document:
            raise ValueError(f"Document with ID {document_id} not found in database.")

        # Checkpoint 1: Mark status processing and update heartbeat
        _update_heartbeat(session, document, status="processing")

        # Checkpoint 2: Download raw PDF bytes from MinIO object storage
        # TODO: Implement local disk buffer caching if processing large multi-hundred page PDFs
        pdf_bytes = minio_service.download_file(document.minio_path)
        _update_heartbeat(session, document)

        # Checkpoint 3: Parse PDF and split into chapter/page-aware chunks
        # TODO: Integrate robust PDF parser (e.g. PyMuPDF/fitz or pypdf) to extract text, chapter headings, and page numbers
        parsed_chunks_metadata = [
            {
                "content": f"Sample boilerplate chunk 1 for chapter: {document.chapter or 'General'}",
                "page_number": 1,
                "chapter": document.chapter or "Chapter 1",
                "chunk_index": 0,
            },
            {
                "content": f"Sample boilerplate chunk 2 for subject: {document.subject or 'General Science'}",
                "page_number": 2,
                "chapter": document.chapter or "Chapter 1",
                "chunk_index": 1,
            },
        ]
        _update_heartbeat(session, document)

        # Checkpoint 4: Compute BGE-M3 vector embeddings for each chunk via Ollama
        # TODO: Batch embedding requests to Ollama /api/embeddings for faster ingestion
        chunk_objects = []
        for meta in parsed_chunks_metadata:
            # For boilerplate verification, generate a dummy 1024-dim zero/test vector or call service
            # embedding = embedding_service.get_embedding(meta["content"])
            dummy_embedding = [0.01] * 1024
            chunk_obj = Chunk(
                id=uuid.uuid4(),
                document_id=document.id,
                content=meta["content"],
                embedding=dummy_embedding,
                page_number=meta["page_number"],
                chapter=meta["chapter"],
                chunk_index=meta["chunk_index"],
            )
            chunk_objects.append(chunk_obj)
        
        _update_heartbeat(session, document)

        # Checkpoint 5: Write chunks into pgvector database table
        # Delete existing chunks for idempotency if re-ingesting
        session.query(Chunk).filter(Chunk.document_id == document.id).delete()
        session.bulk_save_objects(chunk_objects)
        
        # Mark completed & update final heartbeat
        _update_heartbeat(session, document, status="completed")

        return {"document_id": document_id, "status": "completed", "chunks_count": len(chunk_objects)}

    except Exception as exc:
        session.rollback()
        # Fetch document again to safely update status to failed
        doc_failed = session.query(Document).filter(Document.id == doc_uuid).first()
        if doc_failed:
            _update_heartbeat(session, doc_failed, status="failed")
        raise exc
    finally:
        session.close()
