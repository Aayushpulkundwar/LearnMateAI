import unittest
from types import SimpleNamespace

from app.evaluation.assessment_quality import diagnostic_reliability_summary, question_bank_quality, reassessment_performance


class AssessmentQualityTests(unittest.TestCase):
    def test_question_quality_reports_invalid_answer_keys_and_coverage(self):
        valid = SimpleNamespace(id='good', chapter_id='c1', topic_id='t1', difficulty='easy', validation_status='validated', options=[SimpleNamespace(is_correct=True)] + [SimpleNamespace(is_correct=False)] * 3)
        invalid = SimpleNamespace(id='bad', chapter_id='c1', topic_id='t2', difficulty='hard', validation_status='review', options=[SimpleNamespace(is_correct=True)] * 2)
        report = question_bank_quality([valid, invalid])
        self.assertEqual(report['valid_question_count'], 1)
        self.assertEqual(report['invalid_question_ids'], ['bad'])
        self.assertEqual(report['coverage']['topic']['t1'], 1)

    def test_reliability_and_reassessment_are_descriptive_only(self):
        reliability = diagnostic_reliability_summary([40, 60, 80])
        performance = reassessment_performance([40, 70], [60, 65])
        self.assertEqual(reliability['attempts'], 3)
        self.assertIn('Descriptive only', reliability['reliability_note'])
        self.assertEqual((performance['paired_topics'], performance['improved_topics']), (2, 1))
        self.assertIn('not causal', performance['note'])
