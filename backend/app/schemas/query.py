from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class Citation(BaseModel):
    chunk_id: Optional[UUID] = None
    document_id: UUID
    document_title: str
    chapter: Optional[str] = None
    page_number: Optional[int] = None
    chunk_index: Optional[int] = None
    source_index: Optional[int] = None
    similarity_score: Optional[float] = None
    snippet: str


class QueryRequest(BaseModel):
    question: str = Field(..., description="Student question grounded in textbook content")
    document_id: Optional[UUID] = Field(None, description="Optional document filter")
    subject: Optional[str] = Field(None, description="Optional subject filter (e.g. Science, Mathematics)")
    grade: Optional[str] = Field(None, description="Optional grade filter (e.g. Grade 10)")
    chapter: Optional[str] = Field(None, description="Optional chapter title filter")
    grade_id: Optional[UUID] = Field(None, description="Optional normalized grade filter")
    subject_id: Optional[UUID] = Field(None, description="Optional normalized subject filter")
    chapter_id: Optional[UUID] = Field(None, description="Optional normalized chapter filter")
    study_topic_id: Optional[UUID] = Field(None, description="Optional student-selected topic for a focused tutoring session")
    explanation_depth: Literal['brief', 'standard', 'detailed'] = Field('standard', description="Student-selected explanation depth; never inferred from mastery")


class QueryResponse(BaseModel):
    question: str
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    is_refused: bool = Field(False, description="True if answer refused due to missing/irrelevant context")
    refusal_reason: Optional[str] = None


# Secondary Feature 1: Chapter Summarization
class SummarizeRequest(BaseModel):
    document_id: UUID = Field(..., description="Target textbook document ID")
    chapter: Optional[str] = Field(None, description="Target chapter title")


class SummarizeResponse(BaseModel):
    document_id: UUID
    chapter: Optional[str] = None
    summary: str
    key_takeaways: List[str] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)


# Secondary Feature 2: Quiz Generation
class QuizRequest(BaseModel):
    document_id: Optional[UUID] = Field(None, description="Optional authorized textbook filter")
    subject_id: Optional[UUID] = None
    chapter_id: Optional[UUID] = None
    chapter: Optional[str] = Field(None, description="Target chapter title")
    num_questions: int = Field(10, ge=1, le=10, description="Number of concept-based MCQs to generate")
    difficulty: Literal['easy', 'medium', 'hard'] = 'medium'
    topic_id: Optional[UUID] = Field(None, description="Optional authorized concept for focused practice")
