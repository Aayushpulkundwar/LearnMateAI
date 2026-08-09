from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class Citation(BaseModel):
    document_id: UUID
    document_title: str
    chapter: Optional[str] = None
    page_number: Optional[int] = None
    snippet: str


class QueryRequest(BaseModel):
    question: str = Field(..., description="Student question grounded in textbook content")
    document_id: Optional[UUID] = Field(None, description="Optional document filter")
    subject: Optional[str] = Field(None, description="Optional subject filter (e.g. Science, Mathematics)")
    grade: Optional[str] = Field(None, description="Optional grade filter (e.g. Grade 10)")
    chapter: Optional[str] = Field(None, description="Optional chapter title filter")


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
class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    correct_option_index: int
    explanation: str
    citation: Optional[Citation] = None


class QuizRequest(BaseModel):
    document_id: UUID = Field(..., description="Target textbook document ID")
    chapter: Optional[str] = Field(None, description="Target chapter title")
    num_questions: int = Field(5, ge=1, le=20, description="Number of quiz questions to generate")


class QuizResponse(BaseModel):
    document_id: UUID
    chapter: Optional[str] = None
    questions: List[QuizQuestion] = Field(default_factory=list)
