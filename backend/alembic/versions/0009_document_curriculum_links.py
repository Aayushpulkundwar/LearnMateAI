"""Link documents to normalized curriculum without rewriting RAG data.

Revision ID: 0009_document_curriculum_links
Revises: 0008_add_student_gender
"""

import re

from alembic import op
import sqlalchemy as sa


revision = "0009_document_curriculum_links"
down_revision = "0008_add_student_gender"
branch_labels = None
depends_on = None


def _name(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _grade(value: str | None) -> str:
    """Canonicalize only conventional Class/Grade labels, never fuzzy-match."""
    normalized = _name(value)
    match = re.fullmatch(r"(?:class|grade)\s*(\d{1,2})", normalized) or re.fullmatch(r"(\d{1,2})", normalized)
    return match.group(1) if match else normalized


def upgrade() -> None:
    # The three simple FKs are explicit API/model relationships.  Composite
    # constraints below prevent a subject from belonging to a different grade
    # or a chapter from belonging to a different subject.
    op.add_column("documents", sa.Column("grade_id", sa.UUID(), nullable=True))
    op.add_column("documents", sa.Column("subject_id", sa.UUID(), nullable=True))
    op.add_column("documents", sa.Column("chapter_id", sa.UUID(), nullable=True))
    op.add_column("documents", sa.Column("curriculum_mapping_note", sa.Text(), nullable=True))

    op.create_unique_constraint("uq_subjects_id_grade", "subjects", ["id", "grade_id"])
    op.create_unique_constraint("uq_chapters_id_subject", "chapters", ["id", "subject_id"])
    op.create_foreign_key("fk_documents_grade", "documents", "grades", ["grade_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_documents_subject", "documents", "subjects", ["subject_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_documents_chapter", "documents", "chapters", ["chapter_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_documents_subject_grade", "documents", "subjects", ["grade_id", "subject_id"], ["grade_id", "id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_documents_chapter_subject", "documents", "chapters", ["subject_id", "chapter_id"], ["subject_id", "id"], ondelete="RESTRICT")
    op.create_check_constraint("ck_documents_grade_subject_pair", "documents", "(grade_id IS NULL) = (subject_id IS NULL)")
    op.create_check_constraint("ck_documents_chapter_requires_subject", "documents", "chapter_id IS NULL OR subject_id IS NOT NULL")
    op.create_index("ix_documents_grade_id", "documents", ["grade_id"])
    op.create_index("ix_documents_subject_id", "documents", ["subject_id"])
    op.create_index("ix_documents_chapter_id", "documents", ["chapter_id"])
    op.create_index("ix_documents_curriculum_lookup", "documents", ["grade_id", "subject_id", "chapter_id", "processing_status"])

    # This backfill only uses deterministic exact normalized matches within the
    # existing hierarchy.  It neither creates curriculum rows nor touches
    # chunks, vectors, question links, or object storage.
    bind = op.get_bind()
    grades = bind.execute(sa.text("SELECT id, name FROM grades")).mappings().all()
    subjects = bind.execute(sa.text("SELECT id, grade_id, name FROM subjects")).mappings().all()
    chapters = bind.execute(sa.text("SELECT id, subject_id, name FROM chapters")).mappings().all()
    documents = bind.execute(sa.text("SELECT id, grade, subject, chapter FROM documents")).mappings().all()

    for document in documents:
        grade_matches = [row for row in grades if _grade(row["name"]) == _grade(document["grade"])] if document["grade"] else []
        if len(grade_matches) != 1:
            reason = "No unique normalized grade match." if grade_matches else "No normalized grade match."
            bind.execute(sa.text("UPDATE documents SET curriculum_mapping_note = :reason WHERE id = :id"), {"id": document["id"], "reason": reason})
            continue
        grade = grade_matches[0]
        subject_matches = [row for row in subjects if row["grade_id"] == grade["id"] and _name(row["name"]) == _name(document["subject"])] if document["subject"] else []
        if len(subject_matches) != 1:
            reason = "No unique normalized subject match for the matched grade." if subject_matches else "No normalized subject match for the matched grade."
            bind.execute(sa.text("UPDATE documents SET curriculum_mapping_note = :reason WHERE id = :id"), {"id": document["id"], "reason": reason})
            continue
        subject = subject_matches[0]
        chapter_id = None
        if document["chapter"]:
            chapter_matches = [row for row in chapters if row["subject_id"] == subject["id"] and _name(row["name"]) == _name(document["chapter"])]
            if len(chapter_matches) == 1:
                chapter_id = chapter_matches[0]["id"]
                reason = "Mapped from unambiguous legacy grade, subject, and chapter metadata."
            elif chapter_matches:
                reason = "Mapped grade and subject; chapter requires manual mapping because multiple normalized chapters match."
            else:
                reason = "Mapped grade and subject; chapter requires manual mapping because no normalized chapter matches."
        else:
            reason = "Mapped grade and subject; legacy chapter metadata is absent."
        bind.execute(
            sa.text("UPDATE documents SET grade_id = :grade_id, subject_id = :subject_id, chapter_id = :chapter_id, curriculum_mapping_note = :reason WHERE id = :id"),
            {"id": document["id"], "grade_id": grade["id"], "subject_id": subject["id"], "chapter_id": chapter_id, "reason": reason},
        )


def downgrade() -> None:
    op.drop_index("ix_documents_curriculum_lookup", table_name="documents")
    op.drop_index("ix_documents_chapter_id", table_name="documents")
    op.drop_index("ix_documents_subject_id", table_name="documents")
    op.drop_index("ix_documents_grade_id", table_name="documents")
    op.drop_constraint("ck_documents_chapter_requires_subject", "documents", type_="check")
    op.drop_constraint("ck_documents_grade_subject_pair", "documents", type_="check")
    op.drop_constraint("fk_documents_chapter_subject", "documents", type_="foreignkey")
    op.drop_constraint("fk_documents_subject_grade", "documents", type_="foreignkey")
    op.drop_constraint("fk_documents_chapter", "documents", type_="foreignkey")
    op.drop_constraint("fk_documents_subject", "documents", type_="foreignkey")
    op.drop_constraint("fk_documents_grade", "documents", type_="foreignkey")
    op.drop_constraint("uq_chapters_id_subject", "chapters", type_="unique")
    op.drop_constraint("uq_subjects_id_grade", "subjects", type_="unique")
    op.drop_column("documents", "curriculum_mapping_note")
    op.drop_column("documents", "chapter_id")
    op.drop_column("documents", "subject_id")
    op.drop_column("documents", "grade_id")
