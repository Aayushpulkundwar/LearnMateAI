"""Replaceable deterministic performance-based topic mastery proxy.

Score = ((weighted correct + prior_strength * prior_mean) /
         (weighted total + prior_strength)) * 100.
This is explicitly a performance proxy, not a calibrated probability.
"""
from datetime import datetime, timezone
from decimal import Decimal
from math import sqrt
from sqlalchemy import select
from app.core.config import settings
from app.models.learning import AssessmentAttempt, AttemptQuestion, LearningRecommendation, MasteryHistory, Question, StudentAnswer, TopicMastery

def calculate_mastery(evidence):
    weights={"easy":settings.MASTERY_EASY_WEIGHT,"medium":settings.MASTERY_MEDIUM_WEIGHT,"hard":settings.MASTERY_HARD_WEIGHT}
    total=sum(weights.get(row.difficulty,1.0) for row in evidence); correct=sum(weights.get(row.difficulty,1.0) for row in evidence if row.is_correct)
    score=((correct+settings.MASTERY_PRIOR_STRENGTH*settings.MASTERY_PRIOR_MEAN)/(total+settings.MASTERY_PRIOR_STRENGTH))*100
    count=len(evidence)
    if count < settings.MASTERY_INSUFFICIENT_EVIDENCE_COUNT: confidence="Insufficient Evidence"
    elif count < settings.MASTERY_LOW_CONFIDENCE_COUNT: confidence="Low Confidence"
    elif count < settings.MASTERY_MODERATE_CONFIDENCE_COUNT: confidence="Moderate Confidence"
    else: confidence="Higher Confidence"
    if confidence == "Insufficient Evidence": classification="Insufficient Evidence"
    elif score >= settings.MASTERY_STRONG_THRESHOLD: classification="Strong"
    elif score >= settings.MASTERY_DEVELOPING_THRESHOLD: classification="Developing"
    else: classification="Needs Improvement"
    return round(score,2),count,confidence,classification


def calculate_mastery_estimate(evidence):
    """Return the existing score plus an evidence interval, not a knowledge probability.

    The interval is a transparent beta-posterior uncertainty indicator over the
    weighted assessment proxy. It must not be interpreted as calibrated student
    knowledge without prospective validation.
    """
    rows = list(evidence)
    score, count, confidence, classification = calculate_mastery(rows)
    weights = {"easy": settings.MASTERY_EASY_WEIGHT, "medium": settings.MASTERY_MEDIUM_WEIGHT, "hard": settings.MASTERY_HARD_WEIGHT}
    weighted_total = sum(weights.get(row.difficulty, 1.0) for row in rows)
    weighted_correct = sum(weights.get(row.difficulty, 1.0) for row in rows if row.is_correct)
    alpha = weighted_correct + settings.MASTERY_PRIOR_STRENGTH * settings.MASTERY_PRIOR_MEAN
    beta = weighted_total - weighted_correct + settings.MASTERY_PRIOR_STRENGTH * (1 - settings.MASTERY_PRIOR_MEAN)
    mean = alpha / (alpha + beta)
    standard_error = sqrt((alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1)))
    return {
        "mastery_score": score, "evidence_count": count, "confidence_level": confidence, "classification": classification,
        "weighted_evidence": round(weighted_total, 2),
        "evidence_interval_low": round(max(0.0, mean - 1.96 * standard_error) * 100, 2),
        "evidence_interval_high": round(min(1.0, mean + 1.96 * standard_error) * 100, 2),
        "interval_note": "Evidence uncertainty for the assessment-performance proxy; not a calibrated knowledge probability.",
    }


def mastery_interval_from_summary(mastery_score, evidence_count):
    """Approximate an evidence interval when only persisted summary fields exist."""
    total = max(0, evidence_count) + settings.MASTERY_PRIOR_STRENGTH
    mean = min(1.0, max(0.0, float(mastery_score) / 100))
    alpha, beta = mean * total, (1 - mean) * total
    standard_error = sqrt((alpha * beta) / ((total ** 2) * (total + 1))) if alpha and beta else 0.0
    return round(max(0.0, mean - 1.96 * standard_error) * 100, 2), round(min(1.0, mean + 1.96 * standard_error) * 100, 2)

async def recalculate_topic_mastery(db, student_id, topic_id, attempt_id):
    evidence=(await db.execute(select(Question.difficulty,StudentAnswer.is_correct).join(AttemptQuestion,AttemptQuestion.question_id==Question.id).join(StudentAnswer,StudentAnswer.attempt_question_id==AttemptQuestion.id).join(AssessmentAttempt,AssessmentAttempt.id==AttemptQuestion.attempt_id).where(AssessmentAttempt.student_id==student_id,AssessmentAttempt.status=="submitted",Question.topic_id==topic_id))).all()
    score,count,confidence,_=calculate_mastery(evidence)
    mastery=await db.scalar(select(TopicMastery).where(TopicMastery.student_id==student_id,TopicMastery.topic_id==topic_id))
    previous=Decimal("0") if mastery is None else mastery.mastery_score
    if mastery is None:
        mastery=TopicMastery(student_id=student_id,topic_id=topic_id,mastery_score=Decimal(str(score)),confidence_level=confidence,evidence_count=count,last_assessed_at=datetime.now(timezone.utc)); db.add(mastery)
    else:
        mastery.mastery_score=Decimal(str(score)); mastery.confidence_level=confidence; mastery.evidence_count=count; mastery.last_assessed_at=datetime.now(timezone.utc)
    exists=await db.scalar(select(MasteryHistory.id).where(MasteryHistory.student_id==student_id,MasteryHistory.topic_id==topic_id,MasteryHistory.assessment_attempt_id==attempt_id))
    if not exists: db.add(MasteryHistory(student_id=student_id,topic_id=topic_id,previous_score=previous,updated_score=Decimal(str(score)),assessment_attempt_id=attempt_id))
    recommendations=(await db.scalars(select(LearningRecommendation).where(LearningRecommendation.student_id==student_id,LearningRecommendation.topic_id==topic_id,LearningRecommendation.status=="active"))).all()
    for recommendation in recommendations: recommendation.priority=1 if score<50 else 3 if score<80 else 5
    return mastery
