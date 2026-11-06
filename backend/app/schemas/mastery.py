from uuid import UUID
from pydantic import BaseModel
class MasteryItem(BaseModel):
    topic_id: UUID; topic_name: str; chapter_id: UUID; chapter_name: str; subject_id: UUID; subject_name: str
    mastery_score: float; evidence_count: int; confidence_level: str; classification: str; last_assessed_at: object | None; provisional: bool
    weighted_evidence: float | None = None; evidence_interval_low: float | None = None; evidence_interval_high: float | None = None; interval_note: str | None = None
class MasteryHistoryItem(BaseModel): previous_score: float; updated_score: float; recorded_at: object; assessment_attempt_id: UUID | None
