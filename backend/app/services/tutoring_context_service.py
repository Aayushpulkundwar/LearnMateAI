"""Server-derived, non-authoritative preferences for focused tutor sessions."""
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.learning import Chapter, Student, Subject, Topic, TopicMastery

async def resolve_tutoring_context(db: AsyncSession, student: Student, topic_id: UUID, explanation_depth: str | None):
    """Return only this student's topic context; curriculum metadata supplies retrieval filters."""
    row = await db.execute(
        select(Topic, Chapter, Subject, TopicMastery)
        .join(Chapter, Topic.chapter_id == Chapter.id)
        .join(Subject, Chapter.subject_id == Subject.id)
        .outerjoin(TopicMastery, (TopicMastery.topic_id == Topic.id) & (TopicMastery.student_id == student.id))
        .where(Topic.id == topic_id, Subject.grade_id == student.grade_id)
    )
    result = row.one_or_none()
    if not result:
        return None
    topic, chapter, subject, mastery = result
    evidence_count = mastery.evidence_count if mastery else 0
    sufficient = evidence_count >= settings.MASTERY_INSUFFICIENT_EVIDENCE_COUNT
    if not sufficient:
        status = "Insufficient Evidence"
    elif float(mastery.mastery_score) >= settings.MASTERY_STRONG_THRESHOLD:
        status = "Strong"
    elif float(mastery.mastery_score) >= settings.MASTERY_DEVELOPING_THRESHOLD:
        status = "Developing"
    else:
        status = "Needs Improvement"
    return {
        "subject": subject.name, "subject_id": subject.id, "chapter": chapter.name, "chapter_id": chapter.id, "topic": topic.name,
        "mastery_status": status, "evidence_sufficient": sufficient,
        "explanation_depth": explanation_depth or "standard",
    }
