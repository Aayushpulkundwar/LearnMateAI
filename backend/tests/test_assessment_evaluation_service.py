import unittest
from types import SimpleNamespace
from uuid import uuid4
from app.services.assessment_evaluation_service import evaluate_attempt_questions

def item(correct=True, difficulty="easy"):
    option_id, other = uuid4(), uuid4()
    question = SimpleNamespace(chapter_id=uuid4(), topic_id=uuid4(), difficulty=difficulty, options=[SimpleNamespace(id=option_id,is_correct=correct), SimpleNamespace(id=other,is_correct=not correct)])
    return SimpleNamespace(id=uuid4(), question=question), option_id, other

class EvaluationTests(unittest.TestCase):
    def test_fully_correct_and_zero_answered(self):
        first, right, _ = item(); second, right_two, _ = item()
        correct = evaluate_attempt_questions([first, second], [SimpleNamespace(attempt_question_id=first.id, selected_option_id=right), SimpleNamespace(attempt_question_id=second.id, selected_option_id=right_two)])
        empty = evaluate_attempt_questions([first, second], [])
        self.assertEqual((correct['correct'], correct['accuracy']), (2, 100.0))
        self.assertEqual((empty['unanswered'], empty['accuracy']), (2, 0.0))
    def test_partial_and_unanswered_scoring(self):
        first, right, _ = item(); second, _, wrong = item(); third, _, _ = item()
        result = evaluate_attempt_questions([first,second,third],[SimpleNamespace(attempt_question_id=first.id,selected_option_id=right),SimpleNamespace(attempt_question_id=second.id,selected_option_id=wrong)])
        self.assertEqual((result['correct'],result['incorrect'],result['unanswered'],result['accuracy']),(1,1,1,33.33))
    def test_invalid_option_rejected(self):
        question, _, _ = item()
        with self.assertRaises(ValueError): evaluate_attempt_questions([question],[SimpleNamespace(attempt_question_id=question.id,selected_option_id=uuid4())])
