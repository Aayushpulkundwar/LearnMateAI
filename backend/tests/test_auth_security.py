import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest import TestCase

import jwt
from fastapi import HTTPException
from fastapi import Response
from starlette.requests import Request

from app.api.dependencies import get_current_student, require_admin, require_owned_student
from app.api.routes.auth import _profile
from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.api.routes.auth import login, logout, register
from app.models.learning import Grade, Student, User
from app.schemas.auth import LoginRequest, RegisterRequest


def _request_with_cookie(value: str | None) -> Request:
    headers = [] if value is None else [(b"cookie", f"{settings.AUTH_COOKIE_NAME}={value}".encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


class AuthenticationSecurityTests(TestCase):
    def test_registration_duplicate_login_and_logout_behaviors(self):
        grade = Grade(id=uuid.uuid4(), name="Grade 10")

        class RegisterDb:
            def __init__(self): self.calls, self.added = 0, []
            async def scalar(self, _statement):
                self.calls += 1
                return None if self.calls == 1 else grade
            def add(self, item): self.added.append(item)
            async def commit(self):
                for item in self.added:
                    if getattr(item, "id", None) is None: item.id = uuid.uuid4()
                    if isinstance(item, Student):
                        item.user.id = uuid.uuid4()
                        item.user_id = item.user.id
            async def refresh(self, student, attribute_names=None):
                student.grade = grade

        registration = asyncio.run(register(
            RegisterRequest(email="student@example.com", password="secure student password", grade_id=grade.id),
            Response(),
            RegisterDb(),
        ))
        self.assertEqual(registration.student.email, "student@example.com")

        class DuplicateDb:
            async def scalar(self, _statement): return uuid.uuid4()

        with self.assertRaises(HTTPException) as duplicate:
            asyncio.run(register(
                RegisterRequest(email="student@example.com", password="secure student password", grade_id=grade.id),
                Response(),
                DuplicateDb(),
            ))
        self.assertEqual(duplicate.exception.status_code, 409)

        user = User(id=uuid.uuid4(), email="student@example.com", password_hash=hash_password("secure student password"))
        student = Student(id=uuid.uuid4(), user_id=user.id, grade_id=grade.id, user=user, grade=grade)
        user.student = student

        class LoginDb:
            async def scalar(self, _statement): return user
            def add(self, _item): pass
            async def commit(self): pass

        response = Response()
        logged_in = asyncio.run(login(LoginRequest(email=user.email, password="secure student password"), response, LoginDb()))
        self.assertEqual(logged_in.student.id, student.id)
        self.assertIn("httponly", response.headers["set-cookie"].lower())

        with self.assertRaises(HTTPException) as invalid:
            asyncio.run(login(LoginRequest(email=user.email, password="wrong"), Response(), LoginDb()))
        self.assertEqual(invalid.exception.status_code, 401)

        class LogoutDb:
            async def scalars(self, _statement):
                class Result:
                    def all(self): return [type("Session", (), {"revoked_at": None})()]
                return Result()
            async def commit(self): pass

        logout_response = Response()
        asyncio.run(logout(logout_response, student, LogoutDb()))
        self.assertIn(settings.AUTH_COOKIE_NAME, logout_response.headers["set-cookie"])

    def test_password_hash_verifies_only_correct_password(self):
        password_hash = hash_password("secure student password")
        self.assertTrue(verify_password("secure student password", password_hash))
        self.assertFalse(verify_password("incorrect password", password_hash))

    def test_access_token_expires(self):
        token = jwt.encode(
            {"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        with self.assertRaises(jwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_missing_or_expired_session_is_unauthorized(self):
        with self.assertRaises(HTTPException) as missing:
            asyncio.run(get_current_student(_request_with_cookie(None), object()))
        self.assertEqual(missing.exception.status_code, 401)

        expired = jwt.encode(
            {"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        with self.assertRaises(HTTPException) as expired_result:
            asyncio.run(get_current_student(_request_with_cookie(expired), object()))
        self.assertEqual(expired_result.exception.status_code, 401)

    def test_cross_student_access_is_forbidden(self):
        class Student:
            id = uuid.uuid4()

        with self.assertRaises(HTTPException) as result:
            require_owned_student(Student(), uuid.uuid4())
        self.assertEqual(result.exception.status_code, 403)

    def test_admin_flag_is_exposed_only_from_authenticated_profile_and_checked_server_side(self):
        grade = Grade(id=uuid.uuid4(), name="Class 10")
        admin = Student(id=uuid.uuid4(), user_id=uuid.uuid4(), grade_id=grade.id, grade=grade, user=User(email="admin@example.com", is_admin=True))
        student = Student(id=uuid.uuid4(), user_id=uuid.uuid4(), grade_id=grade.id, grade=grade, user=User(email="student@example.com", is_admin=False))
        self.assertTrue(_profile(admin).is_admin)
        self.assertFalse(_profile(student).is_admin)
        self.assertIs(asyncio.run(require_admin(admin)), admin)
        with self.assertRaises(HTTPException) as result:
            asyncio.run(require_admin(student))
        self.assertEqual(result.exception.status_code, 403)

    def test_token_contains_subject_and_session_id(self):
        user_id, session_id = uuid.uuid4(), uuid.uuid4()
        token, expires_at = create_access_token(user_id=user_id, session_id=session_id)
        payload = decode_access_token(token)
        self.assertEqual(payload["sub"], str(user_id))
        self.assertEqual(payload["sid"], str(session_id))
        self.assertGreater(expires_at, datetime.now(timezone.utc))
