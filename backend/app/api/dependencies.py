"""Reusable authenticated-context dependencies.

Feature routes must derive the student from this dependency, never a client
supplied student_id.  It is also the ownership boundary for future assessment,
analytics, mastery, recommendation, and history endpoints.
"""

from datetime import datetime, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.db import get_async_db
from app.core.security import decode_access_token
from app.models.learning import AuthSession, Student


UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication is required.",
)


async def get_current_student(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> Student:
    token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not token:
        raise UNAUTHORIZED
    try:
        payload = decode_access_token(token)
        user_id = UUID(str(payload["sub"]))
        session_id = UUID(str(payload["sid"]))
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise UNAUTHORIZED

    now = datetime.now(timezone.utc)
    session = await db.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    if not session:
        raise UNAUTHORIZED

    student = await db.scalar(
        select(Student)
        .options(selectinload(Student.user), selectinload(Student.grade))
        .where(Student.user_id == user_id)
    )
    if not student:
        raise UNAUTHORIZED
    return student


def require_owned_student(current_student: Student, requested_student_id: UUID) -> None:
    """Use only where legacy routes still carry a student identifier."""
    if current_student.id != requested_student_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student data access is forbidden.")


async def require_admin(current_student: Student = Depends(get_current_student)) -> Student:
    if not current_student.user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access is required.")
    return current_student
