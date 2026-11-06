from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_student
from app.core.config import settings
from app.core.db import get_async_db
from app.models.learning import Chapter, MasteryHistory, Student, Subject, Topic, TopicMastery
from app.schemas.mastery import MasteryHistoryItem, MasteryItem
from app.services.mastery_service import mastery_interval_from_summary
router=APIRouter()
def item(row, topic, chapter, subject):
    score=float(row.mastery_score)
    if row.evidence_count < settings.MASTERY_INSUFFICIENT_EVIDENCE_COUNT: classification='Insufficient Evidence'
    elif score >= settings.MASTERY_STRONG_THRESHOLD: classification='Strong'
    elif score >= settings.MASTERY_DEVELOPING_THRESHOLD: classification='Developing'
    else: classification='Needs Improvement'
    low, high = mastery_interval_from_summary(score, row.evidence_count)
    estimate = {"weighted_evidence": None, "evidence_interval_low": low, "evidence_interval_high": high, "interval_note": "Approximate evidence uncertainty for the stored assessment-performance proxy; not a calibrated knowledge probability."}
    return MasteryItem(topic_id=row.topic_id,topic_name=topic.name,chapter_id=chapter.id,chapter_name=chapter.name,subject_id=subject.id,subject_name=subject.name,mastery_score=score,evidence_count=row.evidence_count,confidence_level=row.confidence_level,classification=classification,last_assessed_at=row.last_assessed_at,provisional=row.evidence_count<settings.MASTERY_INSUFFICIENT_EVIDENCE_COUNT,**estimate)
@router.get('/overview',response_model=list[MasteryItem])
async def overview(student:Student=Depends(get_current_student),db:AsyncSession=Depends(get_async_db)):
    rows=(await db.execute(select(TopicMastery,Topic,Chapter,Subject).join(Topic,TopicMastery.topic_id==Topic.id).join(Chapter,Topic.chapter_id==Chapter.id).join(Subject,Chapter.subject_id==Subject.id).where(TopicMastery.student_id==student.id,Subject.grade_id==student.grade_id,Subject.name.ilike('Science')))).all()
    return [item(*row) for row in rows]
@router.get('/subjects/{subject_id}',response_model=list[MasteryItem])
async def subject(subject_id:UUID,student:Student=Depends(get_current_student),db:AsyncSession=Depends(get_async_db)):
    rows=(await db.execute(select(TopicMastery,Topic,Chapter,Subject).join(Topic,TopicMastery.topic_id==Topic.id).join(Chapter,Topic.chapter_id==Chapter.id).join(Subject,Chapter.subject_id==Subject.id).where(TopicMastery.student_id==student.id,Chapter.subject_id==subject_id,Subject.grade_id==student.grade_id,Subject.name.ilike('Science')))).all(); return [item(*row) for row in rows]
@router.get('/topics/{topic_id}',response_model=MasteryItem)
async def topic(topic_id:UUID,student:Student=Depends(get_current_student),db:AsyncSession=Depends(get_async_db)):
    row=(await db.execute(select(TopicMastery,Topic,Chapter,Subject).join(Topic,TopicMastery.topic_id==Topic.id).join(Chapter,Topic.chapter_id==Chapter.id).join(Subject,Chapter.subject_id==Subject.id).where(TopicMastery.student_id==student.id,TopicMastery.topic_id==topic_id,Subject.grade_id==student.grade_id,Subject.name.ilike('Science')))).one_or_none()
    if not row: raise HTTPException(status_code=404,detail='No mastery evidence for this topic.')
    return item(*row)
@router.get('/topics/{topic_id}/history',response_model=list[MasteryHistoryItem])
async def history(topic_id:UUID,student:Student=Depends(get_current_student),db:AsyncSession=Depends(get_async_db)):
    rows=(await db.scalars(select(MasteryHistory).where(MasteryHistory.student_id==student.id,MasteryHistory.topic_id==topic_id).order_by(MasteryHistory.recorded_at))).all()
    return [MasteryHistoryItem(previous_score=float(row.previous_score),updated_score=float(row.updated_score),recorded_at=row.recorded_at,assessment_attempt_id=row.assessment_attempt_id) for row in rows]
