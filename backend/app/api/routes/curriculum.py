from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_student, require_admin
from app.core.db import get_async_db
from app.models.learning import Chapter, Grade, Student, Subject
from app.services.curriculum_authorization import science_subjects

router = APIRouter()


@router.get("/subjects")
async def subjects(student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    return [{"id": subject.id, "name": subject.name} for subject in await science_subjects(db, student)]


@router.get("/subjects/{subject_id}/chapters")
async def chapters(subject_id: UUID, student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    subject = await db.scalar(select(Subject).where(Subject.id == subject_id, Subject.grade_id == student.grade_id, Subject.name.ilike("Science")))
    if not subject:
        raise HTTPException(status_code=404, detail="Subject is not available for the student's grade.")
    rows = (await db.scalars(select(Chapter).where(Chapter.subject_id == subject.id).order_by(Chapter.chapter_number))).all()
    return [{"id": chapter.id, "name": chapter.name, "chapter_number": chapter.chapter_number} for chapter in rows]


@router.get("/admin/grades")
async def admin_grades(admin: Student = Depends(require_admin), db: AsyncSession = Depends(get_async_db)):
    """Normalized curriculum pick-list for textbook administrators only."""
    rows = (await db.scalars(select(Grade).order_by(Grade.name))).all()
    return [{"id": grade.id, "name": grade.name} for grade in rows]


@router.get("/admin/grades/{grade_id}/subjects")
async def admin_subjects(grade_id: UUID, admin: Student = Depends(require_admin), db: AsyncSession = Depends(get_async_db)):
    rows = (await db.scalars(select(Subject).where(Subject.grade_id == grade_id, Subject.name.ilike("Science")).order_by(Subject.name))).all()
    return [{"id": subject.id, "name": subject.name} for subject in rows]


@router.get("/admin/subjects/{subject_id}/chapters")
async def admin_chapters(subject_id: UUID, admin: Student = Depends(require_admin), db: AsyncSession = Depends(get_async_db)):
    rows = (await db.scalars(select(Chapter).where(Chapter.subject_id == subject_id).order_by(Chapter.chapter_number))).all()
    return [{"id": chapter.id, "name": chapter.name, "chapter_number": chapter.chapter_number} for chapter in rows]
