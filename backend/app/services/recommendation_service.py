"""Deterministic recommendations derived only from persisted learning evidence."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.learning import Chapter, LearningRecommendation, Subject, Topic, TopicMastery

def advise(mastery):
    if mastery.evidence_count < settings.MASTERY_INSUFFICIENT_EVIDENCE_COUNT:
        return "gather_more_evidence", 3, "More assessment evidence is needed before judging this topic.", "practice"
    score=float(mastery.mastery_score)
    if score < settings.MASTERY_DEVELOPING_THRESHOLD:
        return "study_topic", 1, "Low weighted assessment accuracy across sufficient evidence.", "study"
    if score < settings.MASTERY_STRONG_THRESHOLD:
        return "practice_questions", 2, "Developing mastery can be strengthened with additional practice.", "practice"
    return "take_reassessment", 5, "Reassess to confirm this topic remains strong over time.", "reassess"

async def refresh_recommendations(db: AsyncSession, student_id, grade_id=None):
    statement=select(TopicMastery,Topic,Chapter,Subject).join(Topic,TopicMastery.topic_id==Topic.id).join(Chapter,Topic.chapter_id==Chapter.id).join(Subject,Chapter.subject_id==Subject.id).where(TopicMastery.student_id==student_id,Subject.name.ilike('Science'))
    if grade_id is not None: statement=statement.where(Subject.grade_id==grade_id)
    rows=(await db.execute(statement)).all()
    output=[]
    for mastery,topic,chapter,subject in rows:
        kind,priority,reason,action=advise(mastery)
        rec=await db.scalar(select(LearningRecommendation).where(LearningRecommendation.student_id==student_id,LearningRecommendation.topic_id==topic.id,LearningRecommendation.status=="active"))
        if not rec:
            rec=LearningRecommendation(student_id=student_id,topic_id=topic.id,recommendation_type=kind,priority=priority,reason=reason); db.add(rec)
        else: rec.recommendation_type,rec.priority,rec.reason=kind,priority,reason
        output.append((rec,topic,chapter,subject,action))
    return output

def priority_label(value): return "high" if value <= 1 else "medium" if value <= 3 else "low"
