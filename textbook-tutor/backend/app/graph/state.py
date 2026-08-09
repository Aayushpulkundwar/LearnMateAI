from typing import TypedDict, List, Dict, Any, Optional


class RetainedChunk(TypedDict):
    id: str
    document_id: str
    document_title: str
    chapter: Optional[str]
    page_number: Optional[int]
    content: str
    similarity_score: float


class QueryState(TypedDict):
    question: str
    filters: Dict[str, Any]
    retrieved_chunks: List[RetainedChunk]
    is_relevant: bool
    max_relevance_score: float
    answer: str
    citations: List[Dict[str, Any]]
    is_refused: bool
    refusal_reason: Optional[str]
    mode: str  # "query", "summarize", "quiz"
