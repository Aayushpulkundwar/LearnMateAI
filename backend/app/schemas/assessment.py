from uuid import UUID
from pydantic import BaseModel, Field

class DiagnosticStartRequest(BaseModel):
    subject_id: UUID
    question_count: int = Field(default=30, ge=20, le=30)

class PublicOption(BaseModel): id: UUID; option_text: str
class AttemptQuestionView(BaseModel):
    id: UUID; question_text: str; display_order: int; options: list[PublicOption]
    difficulty: str | None = None
    question_type: str | None = None
    concept: str | None = None
class AttemptView(BaseModel): id: UUID; status: str; score: float | None = None; coverage_warning: str | None = None; questions: list[AttemptQuestionView]
class AnswerSubmission(BaseModel): attempt_question_id: UUID; selected_option_id: UUID
class SubmitRequest(BaseModel): answers: list[AnswerSubmission]
class AttemptHistoryItem(BaseModel): id: UUID; subject_id: UUID; started_at: object; submitted_at: object | None; status: str; score: float | None
class ResultGroup(BaseModel): id: str; correct: int; total: int; accuracy: float
class AssessmentResult(BaseModel):
    attempt_id: UUID; subject_id: UUID; total_questions: int; correct: int; incorrect: int; unanswered: int; accuracy: float
    chapter_results: list[ResultGroup]; topic_results: list[ResultGroup]; difficulty_results: list[ResultGroup]
class ReviewOption(BaseModel): id: UUID; option_text: str; is_correct: bool
class ReviewQuestion(BaseModel):
    id: UUID; question_text: str; selected_option_id: UUID | None; options: list[ReviewOption]; explanation: str | None; source_document_id: UUID | None; source_page: int | None; source_chunk_id: UUID | None
    source_title: str | None = None
    chapter_name: str | None = None
    difficulty: str | None = None
    question_type: str | None = None
    bloom_level: str | None = None
    concept: str | None = None
    topic_id: UUID | None = None
    source_chunk_ids: list[UUID] = Field(default_factory=list)
    evidence: str | None = None
class AssessmentReview(BaseModel): result: AssessmentResult; questions: list[ReviewQuestion]
