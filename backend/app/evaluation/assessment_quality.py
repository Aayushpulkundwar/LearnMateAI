"""Deterministic assessment-quality summaries; not psychometric validation."""
from collections import Counter, defaultdict
from statistics import mean, pstdev
from typing import Iterable


def question_bank_quality(questions: Iterable) -> dict:
    rows = list(questions); coverage = defaultdict(Counter); invalid = []
    for question in rows:
        options = list(getattr(question, "options", []))
        correct = sum(bool(getattr(option, "is_correct", False)) for option in options)
        if len(options) != 4 or correct != 1 or getattr(question, "validation_status", None) != "validated": invalid.append(str(getattr(question, "id", "unknown")))
        coverage["chapter"][str(getattr(question, "chapter_id", "unknown"))] += 1
        coverage["topic"][str(getattr(question, "topic_id", "unknown"))] += 1
        coverage["difficulty"][str(getattr(question, "difficulty", "unknown"))] += 1
    return {"questions": len(rows), "valid_question_count": len(rows) - len(invalid), "invalid_question_ids": invalid, "coverage": {key: dict(value) for key, value in coverage.items()}}


def diagnostic_reliability_summary(scores: Iterable[float]) -> dict:
    values = [float(value) for value in scores]
    return {"attempts": len(values), "mean_score": round(mean(values), 2) if values else None, "score_standard_deviation": round(pstdev(values), 2) if len(values) > 1 else None, "reliability_note": "Descriptive only; reliability requires a pre-registered psychometric study."}


def reassessment_performance(before: Iterable[float], after: Iterable[float]) -> dict:
    pairs = list(zip(before, after))
    deltas = [float(post) - float(pre) for pre, post in pairs]
    return {"paired_topics": len(deltas), "mean_score_change": round(mean(deltas), 2) if deltas else None, "improved_topics": sum(delta > 0 for delta in deltas), "note": "Observed reassessment change; not causal learning evidence."}
