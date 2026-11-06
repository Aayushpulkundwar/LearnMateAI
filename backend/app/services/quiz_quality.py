"""Concept assessment contracts and cheap checks, before semantic review.

These checks reject demonstrable defects; they do not pretend that lexical
overlap proves an answer key, grammaticality, or pedagogical calibration.
"""
import re
import unicodedata
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.question_bank_service import is_near_duplicate

GENERATOR_VERSION = 'concept-v1'
Difficulty = Literal['easy', 'medium', 'hard']
QuestionType = Literal['conceptual', 'application', 'scenario', 'analytical']
BLOOM = {
    'easy': {'remember', 'understand'},
    'medium': {'understand', 'apply', 'analyze'},
    'hard': {'apply', 'analyze', 'evaluate'},
}
PLANS = {
    'easy': ['conceptual'] * 6 + ['application'] * 2 + ['scenario'] * 2,
    'medium': ['conceptual'] * 2 + ['application'] * 4 + ['scenario'] * 2 + ['analytical'] * 2,
    'hard': ['application'] * 2 + ['scenario'] * 3 + ['analytical'] * 5,
}


def normalized(value):
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', value).casefold()))


def question_plan(difficulty, count):
    # Prefix sampling would remove analysis from shorter medium quizzes.
    plan = PLANS[difficulty]
    return Counter(plan[min(9, int((i + .5) * 10 / count))] for i in range(count))


class ConceptQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    question: str = Field(min_length=20, max_length=900)
    options: dict[Literal['A', 'B', 'C', 'D'], str]
    correct_answer: Literal['A', 'B', 'C', 'D']
    explanation: str = Field(min_length=35, max_length=900)
    difficulty: Difficulty
    question_type: QuestionType
    bloom_level: Literal['remember', 'understand', 'apply', 'analyze', 'evaluate']
    concept: str = Field(min_length=4, max_length=120)
    learning_objective: str = Field(min_length=12, max_length=250)
    # Compact numeric references map to authorized chunks on the server.
    sources: list[int] = Field(min_length=1, max_length=3)
    evidence: str = Field(min_length=30, max_length=600)
    misconceptions: dict[Literal['A', 'B', 'C', 'D'], str]

    @field_validator('options')
    @classmethod
    def four_distinct_options(cls, value):
        if set(value) != set('ABCD') or any(not text.strip() or len(text) > 450 for text in value.values()):
            raise ValueError('Provide four nonempty options A-D, at most 450 characters each.')
        if len({normalized(text) for text in value.values()}) != 4:
            raise ValueError('Options must differ in meaning, not capitalization or punctuation.')
        return value


class QuestionBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    questions: list[ConceptQuestion] = Field(max_length=10)


class Verdict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: int
    valid: bool
    supported_answers: list[Literal['A', 'B', 'C', 'D']] = Field(max_length=4)
    reason: str = Field(max_length=300)


class ReviewBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    verdicts: list[Verdict] = Field(max_length=10)


def corrupted(text):
    return bool(re.search(r'\ufffd|[\x00-\x08\x0b\x0c\x0e-\x1f]|(?:[A-Za-z]\s+){8,}[A-Za-z]', text))


def rejection_reason(question, sources, accepted, difficulty, remaining, *, focused=False):
    if question.difficulty != difficulty or question.bloom_level not in BLOOM[difficulty]:
        return 'Difficulty/Bloom level does not match the requested cognitive complexity.'
    if remaining[question.question_type] <= 0:
        return 'This question type is already filled; generate a missing type.'
    if len(set(question.sources)) != len(question.sources) or any(i not in sources for i in question.sources):
        return 'Cite only supplied source numbers, without duplicates.'
    chapters = {sources[i][3].id for i in question.sources}
    if len(chapters) != 1:
        return 'A tracked concept question must belong to one chapter.'
    text = ' '.join([question.question, *question.options.values(), question.explanation])
    if corrupted(text) or re.search(r'_{2,}|\.{3,}|\b(?:fill in|complete the (?:textbook|statement|sentence)|page\s*\d+|fig(?:ure)?\.?\s*\d+)\b', text, re.I):
        return 'Use complete standalone conceptual questions, without blanks, page/figure references, or corrupted extraction.'
    if not question.question.endswith('?'):
        return 'Write a complete, grammatical question ending in a question mark.'
    if re.search(r'\b(?:all|none|both) of (?:the )?(?:above|these)|\b(?:except|not true|incorrect statement)\b', text, re.I):
        return 'Avoid multiple-answer or negative constructions.'
    if any(re.search(r'\b(?:all|none)\b', value, re.I) and len(value.split()) <= 3 for value in question.options.values()):
        return 'Do not use all/none alternatives.'
    # An exact quote is necessary evidence, never sufficient proof of correctness.
    if not any(' '.join(question.evidence.casefold().split()) in ' '.join(sources[i][2].casefold().split()) for i in question.sources):
        return 'Evidence must be a verbatim contiguous passage from a cited source.'
    if set(question.misconceptions) != set('ABCD') - {question.correct_answer} or any(len(v.strip()) < 8 for v in question.misconceptions.values()):
        return 'Explain the realistic misconception behind each of the three distractors only.'
    if is_near_duplicate(question.question, [q.question for q in accepted], threshold=.80):
        return 'This question substantially duplicates a previous question.'
    if not focused and any(normalized(q.concept) == normalized(question.concept) or is_near_duplicate(question.concept, [q.concept], threshold=.86) for q in accepted):
        return 'This concept is already assessed; choose a distinct learning objective.'
    if focused and any(is_near_duplicate(question.learning_objective, [q.learning_objective], threshold=.85) for q in accepted):
        return 'Use a different learning objective within the focused concept.'
    # Whitespace around a formula/subscript often signals damaged PDF extraction.
    if re.search(r'\b[A-Z][a-z]?\s+\d+\b|(?:->|→|=)\s*(?:[?.,;]|$)', text):
        return 'Avoid damaged chemical equations; use readable intact formulas or words.'
    return None
