from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class QuestionGenerationRequest(BaseModel):
    subject_id: UUID
    chapter_id: UUID
    topic_id: UUID
    document_id: UUID
    batch_size: int = Field(default=5, ge=1, le=20)
    difficulty_distribution: dict[str, int] = Field(default_factory=lambda: {"easy": 2, "medium": 2, "hard": 1})

    @model_validator(mode="after")
    def validate_distribution(self):
        if set(self.difficulty_distribution) - {"easy", "medium", "hard"} or any(value < 0 for value in self.difficulty_distribution.values()) or sum(self.difficulty_distribution.values()) != self.batch_size:
            raise ValueError("difficulty_distribution must use easy/medium/hard and total batch_size")
        return self


class GenerationStatusResponse(BaseModel):
    task_id: UUID
    status: str
    generated_count: int
    rejected_count: int
    error_message: str | None = None


class QuestionBankSummary(BaseModel):
    total_questions: int
    validated_questions: int
    review_questions: int
    jobs_pending_or_processing: int
