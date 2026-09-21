from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.services.pdf_extraction import ExtractedPDFPage
from app.services.text_chunking import TextChunk
from app.tasks.ingestion import _build_chunk_objects, ingest_document_task


class IngestionEmbeddingTests(unittest.TestCase):
    def test_every_chunk_keeps_metadata_and_receives_its_embedding(self):
        document = SimpleNamespace(id=uuid4(), chapter="Photosynthesis")
        text_chunks = [
            TextChunk(page_number=2, content="First extracted content.", chunk_index=0),
            TextChunk(page_number=3, content="Second extracted content.", chunk_index=1),
        ]
        embeddings = [[0.1, 0.2], [0.3, 0.4]]

        chunks = _build_chunk_objects(document, text_chunks, embeddings)

        self.assertEqual([chunk.document_id for chunk in chunks], [document.id, document.id])
        self.assertEqual([chunk.page_number for chunk in chunks], [2, 3])
        self.assertEqual([chunk.chunk_index for chunk in chunks], [0, 1])
        self.assertEqual([chunk.content for chunk in chunks], ["First extracted content.", "Second extracted content."])
        self.assertEqual([chunk.embedding for chunk in chunks], embeddings)

    def test_embedding_count_mismatch_prevents_chunk_creation(self):
        document = SimpleNamespace(id=uuid4(), chapter=None)
        text_chunks = [TextChunk(page_number=1, content="Chunk content.", chunk_index=0)]

        with self.assertRaisesRegex(ValueError, "does not match"):
            _build_chunk_objects(document, text_chunks, [])

    def test_embedding_failure_marks_document_failed_before_chunk_write(self):
        document = SimpleNamespace(
            id=uuid4(),
            minio_path="textbooks/test.pdf",
            chapter="Test chapter",
            processing_status="pending",
            heartbeat_at=None,
        )

        class Query:
            def filter(self, *_args):
                return self

            def first(self):
                return document

        class Session:
            bulk_save_called = False

            def query(self, *_args):
                return Query()

            def add(self, *_args):
                pass

            def commit(self):
                pass

            def refresh(self, *_args):
                pass

            def rollback(self):
                pass

            def bulk_save_objects(self, *_args):
                self.bulk_save_called = True

            def close(self):
                pass

        session = Session()
        text_chunks = [TextChunk(page_number=1, content="Final chunk text.", chunk_index=0)]
        with (
            patch("app.tasks.ingestion.SyncSessionLocal", return_value=session),
            patch("app.tasks.ingestion.minio_service.download_file", return_value=b"pdf bytes"),
            patch("app.tasks.ingestion.extract_pdf_pages", return_value=[ExtractedPDFPage(1, "Final chunk text.")]),
            patch("app.tasks.ingestion.chunk_extracted_pages", return_value=text_chunks),
            patch("app.tasks.ingestion.embedding_service.embed_texts", side_effect=RuntimeError("Ollama unavailable")),
        ):
            with self.assertRaisesRegex(RuntimeError, "Ollama unavailable"):
                ingest_document_task.run(str(document.id))

        self.assertEqual(document.processing_status, "failed")
        self.assertFalse(session.bulk_save_called)
