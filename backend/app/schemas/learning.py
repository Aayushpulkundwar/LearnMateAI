from uuid import UUID
from pydantic import BaseModel, Field
class RecommendationView(BaseModel):
    id: UUID; topic_id: UUID; topic_name: str; chapter_name: str; subject_name: str; priority: str; recommendation_type: str; reason: str; action: str; status: str
class RecommendationUpdate(BaseModel): status: str = Field(pattern="^(dismissed|completed|active)$")
class ReassessmentStartRequest(BaseModel):
    topic_ids: list[UUID] = []; chapter_ids: list[UUID] = []; question_count: int = Field(default=10, ge=5, le=20)
class ProgressItem(BaseModel):
    topic_id: UUID; topic_name: str; current_mastery: float; previous_mastery: float | None; change: float | None; direction: str
