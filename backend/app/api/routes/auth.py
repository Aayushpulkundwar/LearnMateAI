from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_student
from app.core.config import settings
from app.core.db import get_async_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.learning import AuthSession, Grade, Student, User
from app.schemas.auth import AuthResponse, GradeResponse, LoginRequest, RegisterRequest, StudentProfile

router = APIRouter()


def _profile(student: Student) -> StudentProfile:
    return StudentProfile(
        id=student.id,
        user_id=student.user_id,
        email=student.user.email,
        display_name=student.display_name,
        grade_id=student.grade_id,
        grade_name=student.grade.name,
        is_admin=bool(student.user.is_admin),
    )


def _set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="lax",
        expires=expires_at,
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_async_db)):
    email = str(payload.email).lower()
    existing = await db.scalar(select(User.id).where(func.lower(User.email) == email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
    grade = await db.scalar(select(Grade).where(Grade.id == payload.grade_id))
    if not grade:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected grade does not exist.")

    user = User(email=email, password_hash=hash_password(payload.password))
    student = Student(user=user, grade_id=grade.id, display_name=payload.display_name.strip() if payload.display_name else None)
    db.add(student)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
    await db.refresh(student, attribute_names=["user", "grade"])
    session_id = uuid4()
    token, expires_at = create_access_token(user_id=user.id, session_id=session_id)
    db.add(AuthSession(id=session_id, user_id=user.id, expires_at=expires_at))
    await db.commit()
    _set_session_cookie(response, token, expires_at)
    return AuthResponse(student=_profile(student))


@router.get("/grades", response_model=list[GradeResponse])
async def list_grades(db: AsyncSession = Depends(get_async_db)):
    # Length first keeps Class 7-9 ahead of Class 10-12 without changing IDs.
    return (await db.scalars(select(Grade).order_by(func.length(Grade.name), Grade.name))).all()


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_async_db)):
    user = await db.scalar(
        select(User)
        .options(selectinload(User.student).selectinload(Student.grade))
        .where(func.lower(User.email) == str(payload.email).lower())
    )
    if not user or not verify_password(payload.password, user.password_hash) or not user.student:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    session_id = uuid4()
    token, expires_at = create_access_token(user_id=user.id, session_id=session_id)
    db.add(AuthSession(id=session_id, user_id=user.id, expires_at=expires_at))
    await db.commit()
    _set_session_cookie(response, token, expires_at)
    return AuthResponse(student=_profile(user.student))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, current_student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    # Current token/session identity was already verified by get_current_student.
    # Revoking all currently valid sessions for this user provides reliable logout
    # even when a prior cookie was copied to a different client.
    now = datetime.now(timezone.utc)
    sessions = (await db.scalars(select(AuthSession).where(AuthSession.user_id == current_student.user_id, AuthSession.revoked_at.is_(None)))).all()
    for session in sessions:
        session.revoked_at = now
    await db.commit()
    response.delete_cookie(settings.AUTH_COOKIE_NAME, path="/")


