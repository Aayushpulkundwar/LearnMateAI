import secrets
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_student
from app.core.db import get_async_db
from app.models.learning import Assessment, AssessmentAttempt, AssessmentEvaluation, AttemptQuestion, Question, Student, StudentAnswer, Subject
from app.schemas.assessment import AssessmentResult, AssessmentReview, AttemptHistoryItem, AttemptView, DiagnosticStartRequest, PublicOption, SubmitRequest
from app.services.diagnostic_assessment_service import select_diagnostic_questions
from app.services.assessment_evaluation_service import evaluate_attempt_questions
from app.services.mastery_service import recalculate_topic_mastery
from app.services.recommendation_service import refresh_recommendations

router = APIRouter()

@router.get("/subjects")
async def available_subjects(student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    subjects = (await db.scalars(select(Subject).where(Subject.grade_id == student.grade_id, Subject.name.ilike("Science")).order_by(Subject.name))).all()
    return [{"id": subject.id, "name": subject.name} for subject in subjects]

def view(attempt):
    questions = []
    for aq in sorted(attempt.attempt_questions, key=lambda item: item.display_order):
        option_by_id = {str(option.id): option for option in aq.question.options}
        metadata = getattr(aq.question, 'assessment_metadata', None) or {}
        questions.append({"id": aq.id, "question_text": aq.question.question_text, "display_order": aq.display_order,
            "difficulty": aq.question.difficulty, "question_type": metadata.get('question_type'), "concept": metadata.get('concept'),
            "options": [PublicOption(id=option_by_id[str(option_id)].id, option_text=option_by_id[str(option_id)].option_text) for option_id in aq.option_order_snapshot]})
    return AttemptView(id=attempt.id, status=attempt.status, score=float(attempt.score) if attempt.score is not None else None, coverage_warning=attempt.assessment.coverage_warning, questions=questions)

async def owned_attempt(attempt_id, student_id, db, lock=False):
    statement = select(AssessmentAttempt).options(selectinload(AssessmentAttempt.assessment), selectinload(AssessmentAttempt.attempt_questions).selectinload(AttemptQuestion.question).selectinload(Question.options), selectinload(AssessmentAttempt.attempt_questions).selectinload(AttemptQuestion.student_answer)).where(AssessmentAttempt.id == attempt_id, AssessmentAttempt.student_id == student_id)
    if lock: statement = statement.with_for_update()
    attempt = await db.scalar(statement)
    if not attempt: raise HTTPException(status_code=404, detail="Assessment attempt not found.")
    return attempt

@router.post("/diagnostic/start", response_model=AttemptView, status_code=status.HTTP_201_CREATED)
async def start_diagnostic(payload: DiagnosticStartRequest, student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    subject = await db.scalar(select(Subject).where(Subject.id == payload.subject_id, Subject.grade_id == student.grade_id, Subject.name.ilike("Science")))
    if not subject: raise HTTPException(status_code=404, detail="Subject is not available for the student's grade.")
    recent = (await db.scalars(select(AttemptQuestion.question_id).join(AssessmentAttempt).where(AssessmentAttempt.student_id == student.id).order_by(AssessmentAttempt.started_at.desc()).limit(60))).all()
    questions = (await db.scalars(select(Question).options(selectinload(Question.options)).where(Question.subject_id == subject.id, Question.validation_status == "validated"))).all()
    selected, warning = select_diagnostic_questions(questions, payload.question_count, frozenset(recent))
    if len(selected) < 20:
        raise HTTPException(status_code=409, detail="Diagnostic assessment is unavailable: this Science subject needs at least 20 validated question-bank questions across its uploaded curriculum.")
    assessment = Assessment(subject_id=subject.id, assessment_type="diagnostic", question_count=len(selected), coverage_warning=warning)
    attempt = AssessmentAttempt(assessment=assessment, student_id=student.id, status="in_progress")
    rng = secrets.SystemRandom()
    for order, question in enumerate(selected, start=1):
        option_ids = [str(option.id) for option in question.options]; rng.shuffle(option_ids)
        attempt.attempt_questions.append(AttemptQuestion(question_id=question.id, display_order=order, option_order_snapshot=option_ids, question=question))
    db.add(attempt); await db.commit()
    return view(await owned_attempt(attempt.id, student.id, db))

@router.get("/attempts/{attempt_id}", response_model=AttemptView)
async def get_attempt(attempt_id: UUID, student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    return view(await owned_attempt(attempt_id, student.id, db))

def result_view(attempt, evaluation):
    return AssessmentResult(attempt_id=attempt.id, subject_id=attempt.assessment.subject_id, total_questions=evaluation.total_questions, correct=evaluation.correct_count, incorrect=evaluation.incorrect_count, unanswered=evaluation.unanswered_count, accuracy=float(evaluation.accuracy), chapter_results=evaluation.chapter_results, topic_results=evaluation.topic_results, difficulty_results=evaluation.difficulty_results)

@router.post("/attempts/{attempt_id}/submit", response_model=AssessmentResult)
async def submit_attempt(attempt_id: UUID, payload: SubmitRequest, student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    # Serialize submissions for the same student, including separate attempts,
    # before recalculating shared mastery and recommendation records.
    await db.execute(select(Student.id).where(Student.id == student.id).with_for_update())
    attempt = await owned_attempt(attempt_id, student.id, db, lock=True)
    if attempt.status == "submitted":
        evaluation = await db.scalar(select(AssessmentEvaluation).where(AssessmentEvaluation.attempt_id == attempt.id))
        return result_view(attempt, evaluation)
    answers = {item.attempt_question_id: item.selected_option_id for item in payload.answers}
    if len(answers) != len(payload.answers): raise HTTPException(status_code=422, detail="Each question may be answered once.")
    if not set(answers).issubset({question.id for question in attempt.attempt_questions}):
        raise HTTPException(status_code=422, detail="Answer does not belong to this attempt.")
    try:
        evaluation_data = evaluate_attempt_questions(attempt.attempt_questions, payload.answers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    for aq, selected_id, is_correct in evaluation_data["graded"]:
        if selected_id is not None:
            db.add(StudentAnswer(attempt_question_id=aq.id, question_id=aq.question_id, selected_option_id=selected_id, is_correct=is_correct))
    evaluation = AssessmentEvaluation(attempt_id=attempt.id, total_questions=evaluation_data["total_questions"], correct_count=evaluation_data["correct"], incorrect_count=evaluation_data["incorrect"], unanswered_count=evaluation_data["unanswered"], accuracy=Decimal(str(evaluation_data["accuracy"])), chapter_results=evaluation_data["chapter_results"], topic_results=evaluation_data["topic_results"], difficulty_results=evaluation_data["difficulty_results"])
    attempt.score = evaluation.accuracy; attempt.status = "submitted"; attempt.submitted_at = datetime.now(timezone.utc); db.add(evaluation)
    await db.flush()
    for topic_id in {question.question.topic_id for question in attempt.attempt_questions}:
        await recalculate_topic_mastery(db, student.id, topic_id, attempt.id)
    await db.flush()
    await refresh_recommendations(db, student.id, student.grade_id)
    await db.commit()
    return result_view(attempt, evaluation)

@router.get("/attempts/{attempt_id}/results", response_model=AssessmentReview)
async def results(attempt_id: UUID, student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    attempt = await owned_attempt(attempt_id, student.id, db)
    if attempt.status != "submitted": raise HTTPException(status_code=409, detail="Results are available after submission.")
    evaluation = await db.scalar(select(AssessmentEvaluation).where(AssessmentEvaluation.attempt_id == attempt.id))
    if not evaluation: raise HTTPException(status_code=409, detail="Evaluation is not available.")
    questions = []
    from app.models.document import Document
    from app.models.learning import Chapter
    source_ids = {aq.question.source_document_id for aq in attempt.attempt_questions if aq.question.source_document_id}
    chapter_ids = {aq.question.chapter_id for aq in attempt.attempt_questions}
    documents = {row.id: row for row in (await db.scalars(select(Document).where(Document.id.in_(source_ids)))).all()}
    chapters = {row.id: row for row in (await db.scalars(select(Chapter).where(Chapter.id.in_(chapter_ids)))).all()}
    for aq in sorted(attempt.attempt_questions, key=lambda item: item.display_order):
        selected = aq.student_answer.selected_option_id if aq.student_answer else None
        source = documents.get(aq.question.source_document_id)
        chapter = chapters.get(aq.question.chapter_id)
        metadata = getattr(aq.question, 'assessment_metadata', None) or {}
        questions.append({"id": aq.id, "question_text": aq.question.question_text, "selected_option_id": selected, "options": [{"id": option.id, "option_text": option.option_text, "is_correct": option.is_correct} for option in aq.question.options], "explanation": aq.question.explanation, "source_document_id": aq.question.source_document_id, "source_page": aq.question.source_page, "source_chunk_id": aq.question.source_chunk_id, "source_title": source.title if source else None, "chapter_name": chapter.name if chapter else None})
        questions[-1].update(difficulty=aq.question.difficulty, question_type=metadata.get('question_type'),
            bloom_level=metadata.get('bloom_level'), concept=metadata.get('concept'), topic_id=aq.question.topic_id,
            source_chunk_ids=metadata.get('source_chunk_ids', []), evidence=metadata.get('evidence'))
    return AssessmentReview(result=result_view(attempt, evaluation), questions=questions)

@router.get("/attempts/history", response_model=list[AttemptHistoryItem])
async def history(student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    attempts = (await db.scalars(select(AssessmentAttempt).options(selectinload(AssessmentAttempt.assessment)).join(Assessment).where(AssessmentAttempt.student_id == student.id, Assessment.assessment_type == "diagnostic").order_by(AssessmentAttempt.started_at.desc()))).all()
    return [AttemptHistoryItem(id=item.id, subject_id=item.assessment.subject_id, started_at=item.started_at, submitted_at=item.submitted_at, status=item.status, score=float(item.score) if item.score is not None else None) for item in attempts]
