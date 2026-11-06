import unittest
from types import SimpleNamespace
from uuid import uuid4
from app.services.diagnostic_assessment_service import select_diagnostic_questions

class DiagnosticSamplingTests(unittest.TestCase):
    def test_balances_chapters_and_shuffles(self):
        chapters = [uuid4() for _ in range(3)]
        questions = [SimpleNamespace(id=uuid4(), chapter_id=chapter, difficulty=("easy", "medium", "hard")[index % 3]) for chapter in chapters for index in range(12)]
        selected, warning = select_diagnostic_questions(questions, 30)
        counts = {chapter: sum(q.chapter_id == chapter for q in selected) for chapter in chapters}
        self.assertEqual(len(selected), 30); self.assertIsNone(warning); self.assertEqual(set(counts.values()), {10})
    def test_shortage_is_explicit(self):
        one, two = uuid4(), uuid4()
        questions = [SimpleNamespace(id=uuid4(), chapter_id=one, difficulty="easy") for _ in range(3)] + [SimpleNamespace(id=uuid4(), chapter_id=two, difficulty="medium") for _ in range(25)]
        selected, warning = select_diagnostic_questions(questions, 20)
        self.assertIsNotNone(warning); self.assertLessEqual(len(selected), 20)
