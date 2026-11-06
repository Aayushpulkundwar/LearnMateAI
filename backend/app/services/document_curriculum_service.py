"""Validated links between uploaded documents and normalized curriculum."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import Chapter, Grade, Subject


class CurriculumAssociationError(ValueError):
    """Raised when a document link would violate the curriculum hierarchy."""


async def validate_document_curriculum(
    db: AsyncSession,
    *,
    grade_id: UUID | None,
    subject_id: UUID | None,
    chapter_id: UUID | None,
) -> None:
    """Validate a complete grade/subject link and an optional child chapter.

    Database constraints protect integrity as a final boundary.  This service
    produces clear API errors before an upload is written to object storage.
    """
    if (grade_id is None) != (subject_id is None):
        raise CurriculumAssociationError("grade_id and subject_id must be provided together.")
    if chapter_id is not None and subject_id is None:
        raise CurriculumAssociationError("chapter_id requires grade_id and subject_id.")
    if grade_id is None:
        return

    grade = await db.scalar(select(Grade.id).where(Grade.id == grade_id))
    if not grade:
        raise CurriculumAssociationError("grade_id does not identify an existing grade.")
    subject = await db.scalar(select(Subject.id).where(Subject.id == subject_id, Subject.grade_id == grade_id))
    if not subject:
        raise CurriculumAssociationError("subject_id is not available for grade_id.")
    if chapter_id is not None:
        chapter = await db.scalar(select(Chapter.id).where(Chapter.id == chapter_id, Chapter.subject_id == subject_id))
        if not chapter:
            raise CurriculumAssociationError("chapter_id is not available for subject_id.")
