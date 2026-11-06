import asyncio
import unittest
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

from app.models.document import Document
from app.models.learning import Subject
from app.services.curriculum_authorization import resolve_authorized_scope


class _Rows:
    def __init__(self, values): self.values = values
    def all(self): return self.values


class CurriculumAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.grade_7, self.grade_10 = uuid4(), uuid4()
        self.science_7 = Subject(id=uuid4(), grade_id=self.grade_7, name="Science")
        self.student = SimpleNamespace(grade_id=self.grade_7, grade=SimpleNamespace(name="Class 7"))

    def _db(self, scalar_values=()):
        class Db:
            async def scalars(_, statement): return _Rows([self.science_7])
            async def scalar(_, statement): return next(_.values, None)
            values = iter(scalar_values)
        return Db()

    def test_class_7_receives_only_its_science_scope(self):
        scope = asyncio.run(resolve_authorized_scope(self._db(), self.student))
        self.assertEqual(scope.grade_id, self.grade_7)
        self.assertEqual(scope.subject_id, self.science_7.id)

    def test_cross_grade_subject_is_forbidden(self):
        with self.assertRaises(HTTPException) as result:
            asyncio.run(resolve_authorized_scope(self._db(), self.student, subject_id=uuid4()))
        self.assertEqual(result.exception.status_code, 403)

    def test_cross_grade_legacy_filter_is_forbidden(self):
        with self.assertRaises(HTTPException) as result:
            asyncio.run(resolve_authorized_scope(self._db(), self.student, legacy_grade="10"))
        self.assertEqual(result.exception.status_code, 403)

    def test_unmapped_document_is_forbidden(self):
        document = Document(id=uuid4(), title="Legacy", minio_path="textbooks/legacy.pdf", grade_id=None, subject_id=None)
        with self.assertRaises(HTTPException) as result:
            asyncio.run(resolve_authorized_scope(self._db([document]), self.student, document_id=document.id))
        self.assertEqual(result.exception.status_code, 403)
