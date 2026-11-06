import unittest
from types import SimpleNamespace
from app.services.mastery_service import calculate_mastery, calculate_mastery_estimate, mastery_interval_from_summary

class MasteryTests(unittest.TestCase):
    def test_no_evidence_is_smoothed_and_insufficient(self):
        score,count,confidence,classification=calculate_mastery([])
        self.assertEqual((score,count,confidence,classification),(50.0,0,'Insufficient Evidence','Insufficient Evidence'))
    def test_one_correct_and_one_incorrect_do_not_overstate_mastery(self):
        correct=calculate_mastery([SimpleNamespace(difficulty='hard',is_correct=True)])
        incorrect=calculate_mastery([SimpleNamespace(difficulty='hard',is_correct=False)])
        self.assertLess(correct[0],100); self.assertGreater(correct[0],incorrect[0]); self.assertEqual(correct[2],'Insufficient Evidence')
    def test_mixed_difficulty_and_repeated_evidence(self):
        evidence=[SimpleNamespace(difficulty='easy',is_correct=True),SimpleNamespace(difficulty='medium',is_correct=True),SimpleNamespace(difficulty='hard',is_correct=False)]*4
        score,count,confidence,classification=calculate_mastery(evidence)
        self.assertEqual(count,12); self.assertEqual(confidence,'Moderate Confidence'); self.assertEqual(classification,'Developing')

    def test_evidence_interval_shrinks_with_more_evidence_without_claiming_knowledge_probability(self):
        few = calculate_mastery_estimate([SimpleNamespace(difficulty='easy', is_correct=True)])
        many = calculate_mastery_estimate([SimpleNamespace(difficulty='easy', is_correct=True)] * 20)
        self.assertGreater(few['evidence_interval_high'] - few['evidence_interval_low'], many['evidence_interval_high'] - many['evidence_interval_low'])
        self.assertIn('not a calibrated knowledge probability', few['interval_note'])
        low, high = mastery_interval_from_summary(50, 3)
        self.assertLess(low, high)
