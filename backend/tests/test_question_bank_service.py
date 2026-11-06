import json
import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.services.question_bank_service import CandidateQuestion, is_near_duplicate, parse_candidates, persist_candidate


def payload(chunk_id, correct=0):
    return {"questions": [{"question_text": "What does photosynthesis produce?", "options": [{"option_text": "Glucose"}, {"option_text": "Iron"}, {"option_text": "Salt"}, {"option_text": "Plastic"}], "correct_option_index": correct, "difficulty": "easy", "explanation": "The source states that photosynthesis produces glucose.", "source_chunk_id": str(chunk_id), "source_page": 2}]}


class QuestionBankServiceTests(unittest.TestCase):
    def test_valid_grounded_question_is_stored_with_one_correct_option(self):
        chunk_id = uuid4()
        candidate = parse_candidates(json.dumps(payload(chunk_id)))[0]
        session = SimpleNamespace(added=[])
        session.add = session.added.append
        result = persist_candidate(session, candidate, subject_id=uuid4(), chapter_id=uuid4(), topic_id=uuid4(), document_id=uuid4(), source_chunks={chunk_id: SimpleNamespace(id=chunk_id, page_number=2, content="Photosynthesis can produce glucose in plants.")}, existing_texts=[])
        self.assertEqual(result, "validated")
        self.assertEqual(len(session.added[0].options), 4)
        self.assertEqual(sum(option.is_correct for option in session.added[0].options), 1)

    def test_invalid_llm_output_and_multiple_or_missing_correct_answers_are_rejected(self):
        with self.assertRaises(Exception):
            parse_candidates("not json")
        data = payload(uuid4())
        data["questions"][0]["correct_option_index"] = 4
        with self.assertRaises(Exception):
            parse_candidates(json.dumps(data))

    def test_duplicate_and_missing_source_are_rejected(self):
        chunk_id = uuid4()
        candidate = parse_candidates(json.dumps(payload(chunk_id)))[0]
        session = SimpleNamespace(add=lambda _: None)
        self.assertEqual(persist_candidate(session, candidate, subject_id=uuid4(), chapter_id=uuid4(), topic_id=uuid4(), document_id=uuid4(), source_chunks={}, existing_texts=[]), "rejected")
        self.assertTrue(is_near_duplicate("What does photosynthesis produce?", ["What does photosynthesis produce?"]))

    def test_unsupported_question_is_rejected(self):
        chunk_id = uuid4()
        candidate = CandidateQuestion.model_validate({**payload(chunk_id)["questions"][0], "question_text": "How does quantum entanglement work?"})
        session = SimpleNamespace(add=lambda _: None)
        self.assertEqual(persist_candidate(session, candidate, subject_id=uuid4(), chapter_id=uuid4(), topic_id=uuid4(), document_id=uuid4(), source_chunks={chunk_id: SimpleNamespace(id=chunk_id, page_number=2, content="Photosynthesis produces glucose in plants.")}, existing_texts=[]), "rejected")

    def test_source_document_mismatch_is_rejected_and_ambiguous_options_require_review(self):
        chunk_id, document_id = uuid4(), uuid4()
        candidate = parse_candidates(json.dumps(payload(chunk_id)))[0]
        mismatch = SimpleNamespace(id=chunk_id, document_id=uuid4(), page_number=2, content="Photosynthesis produces glucose in plants.")
        self.assertEqual(persist_candidate(SimpleNamespace(add=lambda _: None), candidate, subject_id=uuid4(), chapter_id=uuid4(), topic_id=uuid4(), document_id=document_id, source_chunks={chunk_id: mismatch}, existing_texts=[]), "rejected")
        data = payload(chunk_id); data["questions"][0]["options"][1]["option_text"] = "Plants"
        ambiguous = parse_candidates(json.dumps(data))[0]
        source = SimpleNamespace(id=chunk_id, document_id=document_id, page_number=2, content="Photosynthesis produces glucose in plants.")
        self.assertEqual(persist_candidate(SimpleNamespace(add=lambda _: None), ambiguous, subject_id=uuid4(), chapter_id=uuid4(), topic_id=uuid4(), document_id=document_id, source_chunks={chunk_id: source}, existing_texts=[]), "review")
