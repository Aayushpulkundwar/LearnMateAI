import secrets
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.dependencies import get_current_student
from app.core.db import get_async_db
from app.models.learning import Assessment, AssessmentAttempt, AttemptQuestion, Chapter, LearningRecommendation, Question, Student, Subject, Topic, TopicMastery, MasteryHistory
from app.schemas.assessment import AttemptView, PublicOption
from app.schemas.learning import ProgressItem, RecommendationUpdate, RecommendationView, ReassessmentStartRequest
from app.services.recommendation_service import priority_label, refresh_recommendations

router=APIRouter()
def recommendation_view(rec,topic,chapter,subject,action): return RecommendationView(id=rec.id,topic_id=topic.id,topic_name=topic.name,chapter_name=chapter.name,subject_name=subject.name,priority=priority_label(rec.priority),recommendation_type=rec.recommendation_type,reason=rec.reason,action=action,status=rec.status)
@router.get('/recommendations',response_model=list[RecommendationView])
async def recommendations(student:Student=Depends(get_current_student),db:AsyncSession=Depends(get_async_db)):
    rows=await refresh_recommendations(db,student.id,student.grade_id); await db.commit(); return [recommendation_view(*row) for row in sorted(rows,key=lambda x:x[0].priority)]
@router.patch('/recommendations/{recommendation_id}',response_model=RecommendationView)
async def update_recommendation(recommendation_id:UUID,payload:RecommendationUpdate,student:Student=Depends(get_current_student),db:AsyncSession=Depends(get_async_db)):
    row=(await db.execute(select(LearningRecommendation,Topic,Chapter,Subject).join(Topic,LearningRecommendation.topic_id==Topic.id).join(Chapter,Topic.chapter_id==Chapter.id).join(Subject,Chapter.subject_id==Subject.id).where(LearningRecommendation.id==recommendation_id,LearningRecommendation.student_id==student.id,Subject.grade_id==student.grade_id,Subject.name.ilike('Science')))).one_or_none()
    if not row: raise HTTPException(404,'Recommendation not found.')
    rec,topic,chapter,subject=row; rec.status=payload.status; await db.commit(); return recommendation_view(rec,topic,chapter,subject,'study' if rec.recommendation_type=='study_topic' else 'practice')
@router.post('/reassessments/start',response_model=AttemptView,status_code=status.HTTP_201_CREATED)
async def start_reassessment(payload:ReassessmentStartRequest,student:Student=Depends(get_current_student),db:AsyncSession=Depends(get_async_db)):
    if bool(payload.topic_ids)==bool(payload.chapter_ids): raise HTTPException(422,'Provide either topic_ids or chapter_ids.')
    scope=select(Topic,Chapter,Subject).join(Chapter,Topic.chapter_id==Chapter.id).join(Subject,Chapter.subject_id==Subject.id)
    scope=scope.where(Topic.id.in_(payload.topic_ids)) if payload.topic_ids else scope.where(Topic.chapter_id.in_(payload.chapter_ids))
    curriculum=(await db.execute(scope.where(Subject.grade_id==student.grade_id))).all()
    if not curriculum: raise HTTPException(404,'Selected learning scope is unavailable.')
    topic_ids={topic.id for topic,_,_ in curriculum}; subject_ids={subject.id for _,_,subject in curriculum}
    if len(subject_ids)!=1: raise HTTPException(422,'A reassessment must stay within one subject.')
    recent=set((await db.scalars(select(AttemptQuestion.question_id).join(AssessmentAttempt).where(AssessmentAttempt.student_id==student.id).order_by(AssessmentAttempt.started_at.desc()).limit(60))).all())
    questions=(await db.scalars(select(Question).options(selectinload(Question.options)).where(Question.topic_id.in_(topic_ids),Question.validation_status=='validated'))).all(); rng=secrets.SystemRandom(); rng.shuffle(questions)
    fresh=[q for q in questions if q.id not in recent]; selected=fresh[:payload.question_count]; warning=None
    if len(selected)<payload.question_count:
        # AI practice concepts are not promoted into the curated bank. Generate
        # fresh, source-reviewed concept practice through the same privacy and
        # grading path, explicitly labeled practice rather than independent validation.
        if len(payload.topic_ids) == 1 and payload.question_count <= 10:
            from app.schemas.query import QuizRequest
            from app.services.tutor_quiz_service import create_quiz
            from app.api.routes.assessments import owned_attempt, view
            attempt_id = await create_quiz(QuizRequest(subject_id=next(iter(subject_ids)),
                topic_id=payload.topic_ids[0], num_questions=payload.question_count), student, db)
            return view(await owned_attempt(attempt_id, student.id, db))
        warning=f'Only {len(fresh)} fresh validated questions are available; reassessment was not created to avoid claiming independent coverage.'; raise HTTPException(409,warning)
    assessment=Assessment(subject_id=next(iter(subject_ids)),assessment_type='reassessment',question_count=len(selected),coverage_warning=warning); attempt=AssessmentAttempt(assessment=assessment,student_id=student.id,status='in_progress')
    for order,q in enumerate(selected,1): ids=[str(o.id) for o in q.options]; rng.shuffle(ids); attempt.attempt_questions.append(AttemptQuestion(question_id=q.id,display_order=order,option_order_snapshot=ids,question=q))
    db.add(attempt); await db.commit()
    return AttemptView(id=attempt.id,status=attempt.status,score=None,coverage_warning=warning,questions=[{'id':aq.id,'question_text':aq.question.question_text,'display_order':aq.display_order,'options':[PublicOption(id=next(o.id for o in aq.question.options if str(o.id)==oid),option_text=next(o.option_text for o in aq.question.options if str(o.id)==oid)) for oid in aq.option_order_snapshot]} for aq in attempt.attempt_questions])
@router.get('/progress',response_model=list[ProgressItem])
async def progress(student:Student=Depends(get_current_student),db:AsyncSession=Depends(get_async_db)):
    rows=(await db.execute(select(TopicMastery,Topic).join(Topic).join(Chapter,Topic.chapter_id==Chapter.id).join(Subject,Chapter.subject_id==Subject.id).where(TopicMastery.student_id==student.id,Subject.grade_id==student.grade_id,Subject.name.ilike('Science')))).all(); out=[]
    for mastery,topic in rows:
        previous=await db.scalar(select(MasteryHistory.updated_score).where(MasteryHistory.student_id==student.id,MasteryHistory.topic_id==topic.id).order_by(MasteryHistory.recorded_at.desc()).offset(1).limit(1)); current=float(mastery.mastery_score); old=float(previous) if previous is not None else None; delta=round(current-old,2) if old is not None else None; out.append(ProgressItem(topic_id=topic.id,topic_name=topic.name,current_mastery=current,previous_mastery=old,change=delta,direction='improving' if delta and delta>0 else 'declining' if delta and delta<0 else 'stable'))
    return out
