from fastapi import APIRouter, Depends
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_student
from app.core.db import get_async_db
from app.models.learning import Assessment, AssessmentAttempt, AttemptQuestion, Question, Student, StudentAnswer, Subject
from app.schemas.analytics import AnalyticsOverview, AssessmentHistory, SubjectAnalytics, TrendsResponse
from app.services.analytics_service import classify, summarize

router = APIRouter()

async def answer_rows(student_id, grade_id, db, subject_id=None, chapter_id=None):
    statement=(select(AssessmentAttempt.id.label("attempt_id"),Assessment.subject_id,AssessmentAttempt.submitted_at,Question.chapter_id,Question.topic_id,Question.difficulty,StudentAnswer.is_correct)
        .join(Assessment,Assessment.id==AssessmentAttempt.assessment_id)
        .join(Subject,Subject.id==Assessment.subject_id)
        .join(AttemptQuestion,AttemptQuestion.attempt_id==AssessmentAttempt.id)
        .join(Question,Question.id==AttemptQuestion.question_id)
        .outerjoin(StudentAnswer,StudentAnswer.attempt_question_id==AttemptQuestion.id)
        .where(AssessmentAttempt.student_id==student_id,AssessmentAttempt.status=="submitted",Subject.grade_id==grade_id,Subject.name.ilike("Science")))
    if subject_id: statement=statement.where(Assessment.subject_id==subject_id)
    if chapter_id: statement=statement.where(Question.chapter_id==chapter_id)
    return (await db.execute(statement)).all()

def subject_metric(rows, subject_id):
    if not rows: return None
    total=len(rows); correct=sum(bool(row.is_correct) for row in rows); attempts=len({row.attempt_id for row in rows}); accuracy=round(correct*100/total,2); classification,sufficient=classify(accuracy,total,attempts)
    return {"id":str(subject_id),"correct":correct,"total_questions":total,"attempt_count":attempts,"accuracy":accuracy,"classification":classification,"evidence_sufficient":sufficient,"provisional":not sufficient}

@router.get("/overview", response_model=AnalyticsOverview)
async def overview(student: Student=Depends(get_current_student), db: AsyncSession=Depends(get_async_db)):
    rows=await answer_rows(student.id,student.grade_id,db); by_subject={}
    for row in rows: by_subject.setdefault(row.subject_id,[]).append(row)
    return AnalyticsOverview(subjects=[{**subject_metric(values,subject_id),"subject_id":str(subject_id)} for subject_id,values in by_subject.items()],total_attempts=len({row.attempt_id for row in rows}))

@router.get("/subjects/{subject_id}", response_model=SubjectAnalytics)
async def subject(subject_id: UUID, student: Student=Depends(get_current_student), db: AsyncSession=Depends(get_async_db)):
    rows=await answer_rows(student.id,student.grade_id,db,subject_id=subject_id); chapters=summarize(rows,"chapter_id"); topics=summarize(rows,"topic_id")
    weakest=sorted(chapters,key=lambda item:item["accuracy"])[:3]
    frequent=sorted(topics,key=lambda item:(item["correct"]-item["total_questions"],-item["total_questions"]))[:5]
    return SubjectAnalytics(subject_id=subject_id,overall=subject_metric(rows,subject_id),strongest_chapters=chapters[:3],weakest_chapters=weakest,frequently_incorrect_topics=frequent)

@router.get("/subjects/{subject_id}/chapters")
async def chapters(subject_id: UUID, student: Student=Depends(get_current_student), db: AsyncSession=Depends(get_async_db)):
    return summarize(await answer_rows(student.id,student.grade_id,db,subject_id=subject_id),"chapter_id")

@router.get("/chapters/{chapter_id}/topics")
async def topics(chapter_id: UUID, student: Student=Depends(get_current_student), db: AsyncSession=Depends(get_async_db)):
    return summarize(await answer_rows(student.id,student.grade_id,db,chapter_id=chapter_id),"topic_id")

@router.get("/assessment-history", response_model=list[AssessmentHistory])
async def history(student: Student=Depends(get_current_student), db: AsyncSession=Depends(get_async_db)):
    attempts=(await db.execute(select(AssessmentAttempt,Assessment).join(Assessment).where(AssessmentAttempt.student_id==student.id,AssessmentAttempt.status=="submitted").order_by(AssessmentAttempt.submitted_at.desc()))).all()
    return [AssessmentHistory(attempt_id=a.id,subject_id=s.subject_id,submitted_at=a.submitted_at,accuracy=float(a.score or 0),total_questions=s.question_count) for a,s in attempts]

@router.get("/performance-trends", response_model=TrendsResponse)
async def performance_trends(student: Student=Depends(get_current_student), db: AsyncSession=Depends(get_async_db)):
    return TrendsResponse(points=await history(student,db))
