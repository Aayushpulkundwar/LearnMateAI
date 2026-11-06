"""Server-side curriculum scope resolution for authenticated students."""
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.learning import Chapter, Student, Subject

SCIENCE = "science"


@dataclass(frozen=True)
class AuthorizedScope:
    grade_id: UUID
    subject_id: UUID
    chapter_id: UUID | None
    document_id: UUID | None


def forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def science_subjects(db: AsyncSession, student: Student) -> list[Subject]:
    return (await db.scalars(
        select(Subject).where(Subject.grade_id == student.grade_id, Subject.name.ilike("Science")).order_by(Subject.name)
    )).all()


async def resolve_authorized_scope(
    db: AsyncSession, student: Student, *, document_id: UUID | None = None,
    subject_id: UUID | None = None, chapter_id: UUID | None = None,
    legacy_grade: str | None = None, legacy_subject: str | None = None,
    legacy_chapter: str | None = None,
) -> AuthorizedScope:
    """Resolve client hints to a grade-bound Science scope; never trust them."""
    if legacy_grade and legacy_grade.strip().casefold() not in {
        student.grade.name.casefold(), student.grade.name.replace("Class ", "").casefold(),
    }:
        raise forbidden("Requested grade is not available to this student.")
    if legacy_subject and legacy_subject.strip().casefold() != SCIENCE:
        raise forbidden("Requested subject is not available to this student.")

    subjects = await science_subjects(db, student)
    if not subjects:
        raise HTTPException(status_code=404, detail="Science curriculum is not available for the student's grade.")
    if subject_id:
        subject = next((item for item in subjects if item.id == subject_id), None)
        if not subject:
            raise forbidden("Requested subject is not available to this student.")
    elif len(subjects) == 1:
        subject = subjects[0]
    else:
        raise HTTPException(status_code=409, detail="Select a Science subject before requesting curriculum content.")

    chapter = None
    if chapter_id:
        chapter = await db.scalar(select(Chapter).where(Chapter.id == chapter_id, Chapter.subject_id == subject.id))
        if not chapter:
            raise forbidden("Requested chapter is not available to this student.")
    elif legacy_chapter:
        chapter = await db.scalar(select(Chapter).where(Chapter.subject_id == subject.id, Chapter.name.ilike(legacy_chapter.strip())))
        if not chapter:
            raise forbidden("Requested chapter is not available to this student.")

    document = None
    if document_id:
        document = await db.scalar(select(Document).where(Document.id == document_id))
        if not document or document.grade_id is None or document.subject_id is None:
            raise forbidden("Document is not available to students.")
        if document.grade_id != student.grade_id or document.subject_id != subject.id:
            raise forbidden("Document is not available to this student.")
        if chapter and document.chapter_id and document.chapter_id != chapter.id:
            raise forbidden("Document does not belong to the requested chapter.")
        if document.chapter_id and chapter is None:
            chapter = await db.scalar(select(Chapter).where(Chapter.id == document.chapter_id, Chapter.subject_id == subject.id))

    return AuthorizedScope(student.grade_id, subject.id, chapter.id if chapter else None, document.id if document else None)
