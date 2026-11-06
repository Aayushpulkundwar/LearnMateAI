"""Opt-in checks against the local development stack (not a shared database).

RUN_REGISTRATION_INTEGRATION=1 python -m unittest tests.test_registration_grades -v
Test accounts are removed in tearDown; existing accounts and grades are untouched.
"""
import os
import unittest
from uuid import uuid4

import httpx
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.db import SyncSessionLocal, sync_engine
from app.models.learning import Grade, Student, User
from scripts.seed_grades import GRADE_NAMES, seed_grades


@unittest.skipUnless(os.getenv("RUN_REGISTRATION_INTEGRATION") == "1", "Requires local development stack")
class RegistrationGradeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.emails = []
        self.client = httpx.Client(base_url=os.getenv("REGISTRATION_TEST_BASE_URL", "http://127.0.0.1:8000/api/v1"), trust_env=False)

    def tearDown(self):
        self.client.close()
        with SyncSessionLocal() as session:
            session.execute(delete(User).where(User.email.in_(self.emails)))
            session.commit()

    def test_seed_fills_missing_grades_and_preserves_ids_on_repeat(self):
        # A connection-local temporary table isolates the missing-data scenario.
        with sync_engine.connect() as connection, connection.begin():
            connection.execute(text("CREATE TEMP TABLE grades (LIKE public.grades INCLUDING ALL) ON COMMIT DROP"))
            with Session(bind=connection) as session:
                original_id = uuid4()
                session.add(Grade(id=original_id, name="Class 10"))
                session.flush()
                self.assertEqual(set(seed_grades(session)), set(GRADE_NAMES) - {"Class 10"})
                first = dict(session.execute(select(Grade.name, Grade.id)).all())
                self.assertEqual(seed_grades(session), [])
                second = dict(session.execute(select(Grade.name, Grade.id)).all())
                self.assertEqual(first, second)
                self.assertEqual(second["Class 10"], original_id)
                self.assertEqual(len(second), 6)

    def test_register_profile_login_and_logout_for_every_grade(self):
        response = self.client.get("/auth/grades")
        self.assertEqual(response.status_code, 200)
        grades = response.json()
        self.assertEqual([grade["name"] for grade in grades], list(GRADE_NAMES))
        self.assertEqual(len({grade["id"] for grade in grades}), 6)
        for grade in grades:
            with self.subTest(grade=grade["name"]):
                self.client.cookies.clear()
                email = f"grade-check-{uuid4().hex}@example.com"
                self.emails.append(email)
                payload = {"email": email, "password": "Grade verification password 2026", "grade_id": grade["id"], "display_name": "Grade verification"}
                registered = self.client.post("/auth/register", json=payload)
                self.assertEqual(registered.status_code, 201, registered.text)
                profile = registered.json()["student"]
                self.assertEqual(profile["grade_id"], grade["id"])
                self.assertEqual(profile["grade_name"], grade["name"])
                with SyncSessionLocal() as session:
                    saved_grade = session.scalar(select(Student.grade_id).join(User).where(User.email == email))
                    self.assertEqual(str(saved_grade), grade["id"])
                self.assertEqual(self.client.get("/students/me").json()["grade_name"], grade["name"])
                self.assertEqual(self.client.post("/auth/register", json=payload).status_code, 409)
                self.assertEqual(self.client.post("/auth/logout").status_code, 204)
                self.assertEqual(self.client.get("/students/me").status_code, 401)
                self.assertEqual(self.client.post("/auth/login", json={"email": email, "password": "wrong"}).status_code, 401)
                logged_in = self.client.post("/auth/login", json={"email": email, "password": payload["password"]})
                self.assertEqual(logged_in.status_code, 200)
                self.assertEqual(logged_in.json()["student"]["grade_id"], grade["id"])
                self.assertEqual(self.client.post("/auth/logout").status_code, 204)
        invalid = self.client.post("/auth/register", json={"email": f"invalid-{uuid4().hex}@example.com", "password": "Grade verification password 2026", "grade_id": str(uuid4())})
        self.assertEqual(invalid.status_code, 422)
