"""Grounded MCQ parsing, validation, deduplication, and persistence helpers."""

import hashlib
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.models.learning import Question, QuestionOption


class CandidateOption(BaseModel):
    option_text: str = Field(min_length=1, max_length=1000)
    misconception_tag: str | None = Field(default=None, max_length=255)


class CandidateQuestion(BaseModel):
    question_text: str = Field(min_length=8, max_length=4000)
    options: list[CandidateOption] = Field(min_length=4, max_length=4)
    correct_option_index: int = Field(ge=0, le=3)
    difficulty: str
    explanation: str = Field(min_length=8, max_length=4000)
    source_chunk_id: UUID
    source_page: int | None = Field(default=None, ge=1)

    @field_validator("difficulty")
    @classmethod
    def valid_difficulty(cls, value: str) -> str:
        value = value.lower()
        if value not in {"easy", "medium", "hard"}:
            raise ValueError("difficulty must be easy, medium, or hard")
        return value

    @field_validator("options")
    @classmethod
    def options_are_distinct(cls, value: list[CandidateOption]) -> list[CandidateOption]:
        normalized = [option.option_text.strip().casefold() for option in value]
        if len(set(normalized)) != 4:
            raise ValueError("options must be distinct")
        return value


def parse_candidates(raw_output: str) -> list[CandidateQuestion]:
    """Accept only a JSON object/list; markdown prose is never interpreted."""
    text = raw_output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    payload = json.loads(text)
    candidates = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(candidates, list):
        raise ValueError("LLM output must contain a questions array")
    return [CandidateQuestion.model_validate(item) for item in candidates]


def normalized_question(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold()).strip()


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalized_question(text).encode("utf-8")).hexdigest()


def is_near_duplicate(question_text: str, existing_texts: Iterable[str], threshold: float = 0.88) -> bool:
    normalized = normalized_question(question_text)
    return any(SequenceMatcher(None, normalized, normalized_question(existing)).ratio() >= threshold for existing in existing_texts)


def grounded_status(candidate: CandidateQuestion, source_content: str, source_page: int | None) -> str:
    if candidate.source_page is not None and candidate.source_page != source_page:
        return "rejected"
    terms = set(re.findall(r"[a-zA-Z]{4,}", candidate.question_text.casefold()))
    source_terms = set(re.findall(r"[a-zA-Z]{4,}", source_content.casefold()))
    overlap = len(terms & source_terms)
    if overlap >= 2:
        source_terms = set(re.findall(r"[a-zA-Z]{3,}", source_content.casefold()))
        correct_terms = set(re.findall(r"[a-zA-Z]{3,}", candidate.options[candidate.correct_option_index].option_text.casefold()))
        distractor_terms = [set(re.findall(r"[a-zA-Z]{3,}", option.option_text.casefold())) for index, option in enumerate(candidate.options) if index != candidate.correct_option_index]
        # A correct answer must be explicitly source-connected before it can be
        # auto-validated. If a distractor is equally source-connected, a human
        # reviewer decides whether the wording is defensible rather than the
        # system claiming exactly-one-answer certainty.
        if not correct_terms or not (correct_terms & source_terms):
            return "review"
        if any(terms and terms <= source_terms for terms in distractor_terms):
            return "review"
        return "validated"
    if overlap == 1:
        return "review"
    return "rejected"


def persist_candidate(
    session: Any,
    candidate: CandidateQuestion,
    *,
    subject_id: UUID,
    chapter_id: UUID,
    topic_id: UUID,
    document_id: UUID,
    source_chunks: dict[UUID, Any],
    existing_texts: Iterable[str],
) -> str:
    """Store only structurally valid, source-bound non-duplicate candidates."""
    source = source_chunks.get(candidate.source_chunk_id)
    if source is None or is_near_duplicate(candidate.question_text, existing_texts):
        return "rejected"
    source_document_id = getattr(source, "document_id", document_id)
    if str(source_document_id) != str(document_id):
        return "rejected"
    status = grounded_status(candidate, source.content, source.page_number)
    if status == "rejected":
        return status
    question = Question(
        subject_id=subject_id,
        chapter_id=chapter_id,
        topic_id=topic_id,
        question_text=candidate.question_text.strip(),
        question_fingerprint=fingerprint(candidate.question_text),
        difficulty=candidate.difficulty,
        source_document_id=document_id,
        source_page=source.page_number,
        source_chunk_id=source.id,
        explanation=candidate.explanation.strip(),
        validation_status=status,
    )
    question.options = [
        QuestionOption(option_text=option.option_text.strip(), is_correct=index == candidate.correct_option_index, misconception_tag=option.misconception_tag)
        for index, option in enumerate(candidate.options)
    ]
    session.add(question)
    return status


def build_generation_prompt(*, topic_name: str, requested_count: int, difficulty_distribution: dict[str, int], chunks: Iterable[Any]) -> str:
    sources = "\n\n".join(
        f"SOURCE chunk_id={chunk.id} page={chunk.page_number}\n{chunk.content}"
        for chunk in chunks
    )
    return f"""Create exactly {requested_count} textbook-grounded MCQs about the topic {topic_name!r}.
Difficulty distribution: {json.dumps(difficulty_distribution)}.
Return JSON only: {{\"questions\":[{{\"question_text\":str,\"options\":[{{\"option_text\":str,\"misconception_tag\":str|null}}],\"correct_option_index\":0,\"difficulty\":\"easy|medium|hard\",\"explanation\":str,\"source_chunk_id\":UUID,\"source_page\":number}}]}}.
Every question must have four distinct options, exactly one correct index, and cite one supplied source. Do not use outside knowledge.

{sources}"""
