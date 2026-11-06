"""Deterministic aggregation of persisted assessment answers."""
from collections import defaultdict
from app.core.config import settings

def classify(accuracy, total_questions, attempts):
    sufficient = total_questions >= settings.PERFORMANCE_MIN_QUESTIONS and attempts >= settings.PERFORMANCE_MIN_ATTEMPTS
    if accuracy >= settings.PERFORMANCE_STRONG_THRESHOLD: label = "Strong"
    elif accuracy >= settings.PERFORMANCE_DEVELOPING_THRESHOLD: label = "Developing"
    else: label = "Needs Improvement"
    return label, sufficient

def summarize(rows, key):
    buckets = defaultdict(lambda: {"correct":0,"total":0,"attempts":set()})
    for row in rows:
        value = getattr(row, key)
        if value is None: continue
        b=buckets[str(value)]; b["total"]+=1; b["correct"]+=int(bool(row.is_correct)); b["attempts"].add(row.attempt_id)
    output=[]
    for identifier, b in buckets.items():
        accuracy=round(b["correct"]*100/b["total"],2) if b["total"] else 0
        classification,sufficient=classify(accuracy,b["total"],len(b["attempts"]))
        output.append({"id":identifier,"correct":b["correct"],"total_questions":b["total"],"attempt_count":len(b["attempts"]),"accuracy":accuracy,"classification":classification,"evidence_sufficient":sufficient,"provisional":not sufficient})
    return sorted(output,key=lambda item:item["accuracy"],reverse=True)

def trends(attempts):
    points=[{"attempt_id":str(row.id),"subject_id":str(row.subject_id),"submitted_at":row.submitted_at,"accuracy":float(row.score or 0)} for row in attempts]
    return points
