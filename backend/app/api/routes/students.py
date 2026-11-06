from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_student
from app.api.routes.auth import _profile
from app.core.db import get_async_db
from app.models.learning import Grade, Student
from app.schemas.auth import ProfileUpdateRequest, StudentProfile

router = APIRouter()


@router.get("/me", response_model=StudentProfile)
async def get_my_profile(current_student: Student = Depends(get_current_student)):
    return _profile(current_student)


@router.patch("/me", response_model=StudentProfile)
async def update_my_profile(
    payload: ProfileUpdateRequest,
    current_student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_async_db),
):
    if payload.grade_id is not None and payload.grade_id != current_student.grade_id:
        grade = await db.scalar(select(Grade).where(Grade.id == payload.grade_id))
        if not grade:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected grade does not exist.")
        current_student.grade_id = grade.id
        current_student.grade = grade
    if "display_name" in payload.model_fields_set:
        current_student.display_name = payload.display_name.strip() if payload.display_name else None
    await db.commit()
    await db.refresh(current_student, attribute_names=["user", "grade"])
    return _profile(current_student)
