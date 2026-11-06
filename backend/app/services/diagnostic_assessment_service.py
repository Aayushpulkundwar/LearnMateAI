"""Secure, chapter-first sampling for diagnostic assessments."""
import secrets
from collections import defaultdict


def select_diagnostic_questions(questions, requested_count, recent_ids=frozenset(), distribution=None):
    """Chapter coverage is primary; shortages are explicitly reported.

    Policy: allocate evenly over chapters with validated questions, prefer
    questions not recently attempted, then redistribute only among chapters
    with surplus. Missing chapters are reported, never represented as covered.
    """
    distribution = distribution or {"easy": .4, "medium": .4, "hard": .2}
    rng = secrets.SystemRandom()
    by_chapter = defaultdict(list)
    for question in questions:
        by_chapter[question.chapter_id].append(question)
    chapters = list(by_chapter)
    if not chapters:
        return [], "No validated questions are available for this subject."
    base, remainder = divmod(requested_count, len(chapters))
    quotas = {chapter: base + (index < remainder) for index, chapter in enumerate(chapters)}
    chosen, shortages = [], []
    targets = {difficulty: round(requested_count * portion) for difficulty, portion in distribution.items()}
    targets["medium"] += requested_count - sum(targets.values())
    used_difficulties = defaultdict(int)
    for chapter, quota in quotas.items():
        candidates = list(by_chapter[chapter])
        rng.shuffle(candidates)
        fresh = [question for question in candidates if question.id not in recent_ids]
        candidates = fresh + [question for question in candidates if question.id in recent_ids]
        chapter_selected = []
        for question in candidates:
            if len(chapter_selected) >= quota:
                break
            if used_difficulties[question.difficulty] < targets.get(question.difficulty, 0):
                chapter_selected.append(question); used_difficulties[question.difficulty] += 1
        for question in candidates:
            if len(chapter_selected) >= quota:
                break
            if question not in chapter_selected:
                chapter_selected.append(question); used_difficulties[question.difficulty] += 1
        chosen.extend(chapter_selected)
        if len(chapter_selected) < quota:
            shortages.append(f"chapter {chapter} supplied {len(chapter_selected)} of {quota}")
    remaining = [question for values in by_chapter.values() for question in values if question not in chosen]
    rng.shuffle(remaining)
    chosen.extend(remaining[:requested_count - len(chosen)])
    rng.shuffle(chosen)
    warning = None
    if shortages or len(chosen) < requested_count:
        warning = "Incomplete chapter coverage: " + "; ".join(shortages or [f"only {len(chosen)} of {requested_count} validated questions available"])
    return chosen[:requested_count], warning
