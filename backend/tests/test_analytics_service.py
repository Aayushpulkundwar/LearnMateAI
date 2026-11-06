import unittest
from types import SimpleNamespace
from uuid import uuid4
from app.services.analytics_service import summarize

class AnalyticsTests(unittest.TestCase):
    def test_empty_and_small_samples_are_provisional(self):
        self.assertEqual(summarize([], "chapter_id"), [])
        row=SimpleNamespace(chapter_id=uuid4(),attempt_id=uuid4(),is_correct=True)
        result=summarize([row],"chapter_id")[0]
        self.assertEqual(result["accuracy"],100.0); self.assertTrue(result["provisional"])
    def test_improvement_and_decline_data_remains_actual(self):
        chapter=uuid4(); first=uuid4(); second=uuid4()
        rows=[SimpleNamespace(chapter_id=chapter,attempt_id=first,is_correct=False) for _ in range(3)]+[SimpleNamespace(chapter_id=chapter,attempt_id=second,is_correct=True) for _ in range(7)]
        result=summarize(rows,"chapter_id")[0]
        self.assertEqual((result["correct"],result["total_questions"],result["accuracy"]),(7,10,70.0))
