import asyncio
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from app.services.document_curriculum_service import (
    CurriculumAssociationError,
    validate_document_curriculum,
)


class DocumentCurriculumValidationTests(unittest.TestCase):
    def test_legacy_document_without_normalized_links_remains_allowed(self):
        db = AsyncMock()
        asyncio.run(validate_document_curriculum(db, grade_id=None, subject_id=None, chapter_id=None))
        db.scalar.assert_not_awaited()

    def test_subject_requires_grade(self):
        with self.assertRaisesRegex(CurriculumAssociationError, "provided together"):
            asyncio.run(validate_document_curriculum(AsyncMock(), grade_id=None, subject_id=uuid4(), chapter_id=None))

    def test_chapter_requires_subject_and_grade(self):
        with self.assertRaisesRegex(CurriculumAssociationError, "requires grade_id"):
            asyncio.run(validate_document_curriculum(AsyncMock(), grade_id=None, subject_id=None, chapter_id=uuid4()))

    def test_valid_hierarchy_is_accepted(self):
        db = AsyncMock()
        db.scalar = AsyncMock(side_effect=[uuid4(), uuid4(), uuid4()])
        asyncio.run(validate_document_curriculum(db, grade_id=uuid4(), subject_id=uuid4(), chapter_id=uuid4()))
        self.assertEqual(db.scalar.await_count, 3)

    def test_subject_from_another_grade_is_rejected(self):
        db = AsyncMock()
        db.scalar = AsyncMock(side_effect=[uuid4(), None])
        with self.assertRaisesRegex(CurriculumAssociationError, "not available for grade_id"):
            asyncio.run(validate_document_curriculum(db, grade_id=uuid4(), subject_id=uuid4(), chapter_id=None))
