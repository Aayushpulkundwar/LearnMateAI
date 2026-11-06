"""Idempotently register the verified Class 10 Science chapter taxonomy."""

import json

from sqlalchemy import select

from app.core.db import SyncSessionLocal
from app.models.learning import Chapter, Grade, Subject


CHAPTERS = {
    1: "Chemical Reactions and Equations", 2: "Acids, Bases and Salts",
    3: "Metals and Non-metals", 4: "Carbon and its Compounds",
    5: "Life Processes", 6: "Control and Coordination",
    7: "How do Organisms Reproduce?", 8: "Heredity and Evolution",
    9: "Light - Reflection and Refraction", 10: "The Human Eye and the Colourful World",
    11: "Electricity", 12: "Magnetic Effects of Electric Current", 13: "Our Environment",
}


def main() -> None:
    with SyncSessionLocal() as session:
        grade = session.scalar(select(Grade).where(Grade.name == "Class 10"))
        if grade is None:
            raise RuntimeError("Class 10 grade is missing; seed verified grades before continuing.")
        subjects = session.scalars(select(Subject).where(Subject.grade_id == grade.id, Subject.name.ilike("Science"))).all()
        if len(subjects) > 1:
            raise RuntimeError("Multiple Class 10 Science subjects exist; resolve before ingestion.")
        subject = subjects[0] if subjects else Subject(name="Science", grade_id=grade.id)
        if not subjects:
            session.add(subject); session.flush()
        existing = {row.chapter_number: row for row in session.scalars(select(Chapter).where(Chapter.subject_id == subject.id)).all()}
        for number, name in CHAPTERS.items():
            row = existing.get(number)
            if row and row.name != name:
                raise RuntimeError(f"Chapter {number} has {row.name!r}, not verified title {name!r}.")
            if row is None:
                session.add(Chapter(subject_id=subject.id, chapter_number=number, name=name))
        session.commit()
        rows = session.scalars(select(Chapter).where(Chapter.subject_id == subject.id).order_by(Chapter.chapter_number)).all()
        print(json.dumps({"grade_id": str(grade.id), "subject_id": str(subject.id), "chapters": {str(row.chapter_number): {"id": str(row.id), "name": row.name} for row in rows}}, sort_keys=True))


if __name__ == "__main__":
    main()
