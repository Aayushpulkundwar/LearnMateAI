from uuid import UUID
from pydantic import BaseModel

class PerformanceMetric(BaseModel):
    id: str; correct: int; total_questions: int; attempt_count: int; accuracy: float; classification: str; evidence_sufficient: bool; provisional: bool
class SubjectOverview(PerformanceMetric): subject_id: str
class AnalyticsOverview(BaseModel): subjects: list[SubjectOverview]; total_attempts: int
class SubjectAnalytics(BaseModel): subject_id: UUID; overall: PerformanceMetric | None; strongest_chapters: list[PerformanceMetric]; weakest_chapters: list[PerformanceMetric]; frequently_incorrect_topics: list[PerformanceMetric]
class AssessmentHistory(BaseModel): attempt_id: UUID; subject_id: UUID; submitted_at: object; accuracy: float; total_questions: int
class TrendsResponse(BaseModel): points: list[AssessmentHistory]
