"""Idempotently seed the minimum verified Science curriculum.

Run inside the API container from ``/app``:
``python -m scripts.seed_science_curriculum``

The six registration grades must already exist (use ``seed_grades`` first in a
new environment).  Only Class 10 Chapter 1 is seeded because it is supported
by the currently ingested NCERT document; this script intentionally does not
invent chapters for the other grade-level Science subjects.
"""

from collections.abc import Iterable

from sqlalchemy import func, or_, select

from app.core.db import SyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.learning import Chapter, Grade, Subject


SCIENCE_GRADES = ("Class 7", "Class 8", "Class 9", "Class 10", "Class 11", "Class 12")
CLASS_10_CHAPTER_1 = "Chemical Reactions and Equations"


def normalized(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def get_single_by_normalized_name(rows: Iterable[object], expected_name: str, kind: str):
    matches = [row for row in rows if normalized(row.name) == normalized(expected_name)]
    if len(matches) > 1:
        raise RuntimeError(f"Multiple {kind} records match {expected_name!r}; resolve duplicates before seeding.")
    return matches[0] if matches else None


def verified_chapter_document(session, subject: Subject, chapter: Chapter) -> Document | None:
    """Return one safely mappable document only when metadata and chunks agree."""
    candidates = session.scalars(
        select(Document).where(
            or_(Document.grade_id.is_(None), Document.grade_id == subject.grade_id),
            or_(Document.subject_id.is_(None), Document.subject_id == subject.id),
            Document.chapter_id.is_(None),
            func.lower(func.trim(Document.grade)).in_(("10", "class 10", "grade 10")),
            func.lower(func.trim(Document.subject)) == normalized(subject.name),
            func.lower(func.trim(Document.chapter)) == normalized(chapter.name),
        )
    ).all()
    verified: list[Document] = []
    for document in candidates:
        labels = session.scalars(
            select(Chunk.chapter).where(Chunk.document_id == document.id).distinct()
        ).all()
        nonempty_labels = {normalized(label) for label in labels if label}
        title_evidence = session.scalar(
            select(Chunk.id).where(
                Chunk.document_id == document.id,
                Chunk.content.ilike(f"%{chapter.name}%"),
            ).limit(1)
        )
        if nonempty_labels == {normalized(chapter.name)} and title_evidence:
            verified.append(document)
    if len(verified) > 1:
        raise RuntimeError(
            f"Multiple documents are chapter-specific matches for {chapter.name!r}; map them through an administrator review."
        )
    return verified[0] if verified else None


def main() -> None:
    created_subjects: list[str] = []
    created_chapters: list[str] = []
    mapped_documents: list[str] = []

    with SyncSessionLocal() as session:
        grades = session.scalars(select(Grade).where(Grade.name.in_(SCIENCE_GRADES))).all()
        grades_by_name = {grade.name: grade for grade in grades}
        missing = [name for name in SCIENCE_GRADES if name not in grades_by_name]
        if missing:
            raise RuntimeError(f"Required grades are missing: {', '.join(missing)}. Run scripts.seed_grades first.")

        science_subjects: dict[str, Subject] = {}
        for grade_name in SCIENCE_GRADES:
            grade = grades_by_name[grade_name]
            subject = get_single_by_normalized_name(
                session.scalars(select(Subject).where(Subject.grade_id == grade.id)).all(), "Science", "Science subject"
            )
            if subject is None:
                subject = Subject(name="Science", grade_id=grade.id)
                session.add(subject)
                session.flush()
                created_subjects.append(grade_name)
            science_subjects[grade_name] = subject

        class_10_science = science_subjects["Class 10"]
        chapters = session.scalars(select(Chapter).where(Chapter.subject_id == class_10_science.id)).all()
        chapter = get_single_by_normalized_name(chapters, CLASS_10_CHAPTER_1, "chapter")
        chapter_number_match = [item for item in chapters if item.chapter_number == 1]
        if chapter is None and chapter_number_match:
            raise RuntimeError("Class 10 Science chapter number 1 already has a different title; refusing to guess.")
        if chapter is None:
            chapter = Chapter(subject_id=class_10_science.id, chapter_number=1, name=CLASS_10_CHAPTER_1)
            session.add(chapter)
            session.flush()
            created_chapters.append("Class 10 Science — Chapter 1")

        document = verified_chapter_document(session, class_10_science, chapter)
        if document:
            document.grade_id = class_10_science.grade_id
            document.subject_id = class_10_science.id
            document.chapter_id = chapter.id
            document.curriculum_mapping_note = (
                "Mapped by verified legacy metadata and homogeneous chunk labels; "
                "content identifies Class 10 Science Chapter 1."
            )
            mapped_documents.append(str(document.id))

        session.commit()

    print(
        "Science curriculum seed complete: "
        f"subjects_created={len(created_subjects)} ({', '.join(created_subjects) or 'none'}); "
        f"chapters_created={len(created_chapters)} ({', '.join(created_chapters) or 'none'}); "
        f"documents_mapped={len(mapped_documents)} ({', '.join(mapped_documents) or 'none'})."
    )


if __name__ == "__main__":
    main()
