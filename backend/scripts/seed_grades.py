"""Idempotently seed the supported student registration grades.

Run from the backend directory inside the API container, or with a database
configuration that can reach the configured PostgreSQL instance:
``python -m scripts.seed_grades``.
"""
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert

from app.core.db import SyncSessionLocal
from app.models.learning import Grade

GRADE_NAMES = ("Class 7", "Class 8", "Class 9", "Class 10", "Class 11", "Class 12")


def seed_grades(session) -> list[str]:
    """Insert only missing names, preserving all existing IDs and relationships.

    The unique name constraint also prevents duplicates if two seeds run at once.
    The caller owns the transaction.
    """
    statement = (
        insert(Grade)
        .values([{"id": uuid4(), "name": name} for name in GRADE_NAMES])
        .on_conflict_do_nothing(index_elements=[Grade.name])
        .returning(Grade.name)
    )
    return list(session.scalars(statement))


def main() -> None:
    with SyncSessionLocal() as session:
        inserted = seed_grades(session)
        session.commit()
    print(f"Inserted {len(inserted)} grade(s): {', '.join(inserted) or 'none'}")


if __name__ == "__main__":
    main()
