"""Deterministic objective-MCQ evaluation and grouped result calculation."""
from collections import defaultdict


def evaluate_attempt_questions(attempt_questions, submitted_answers):
    """Returns counts plus chapter/topic/difficulty accuracy with unanswered included."""
    answers = {answer.attempt_question_id: answer.selected_option_id for answer in submitted_answers}
    groups = {"chapter": defaultdict(lambda: [0, 0]), "topic": defaultdict(lambda: [0, 0]), "difficulty": defaultdict(lambda: [0, 0])}
    correct = incorrect = unanswered = 0
    graded = []
    for aq in attempt_questions:
        selected = answers.get(aq.id)
        options = {option.id: option for option in aq.question.options}
        if selected is not None and selected not in options:
            raise ValueError("Selected option is invalid for this attempt question.")
        is_correct = bool(selected is not None and options[selected].is_correct)
        if selected is None: unanswered += 1
        elif is_correct: correct += 1
        else: incorrect += 1
        for key, value in (("chapter", str(aq.question.chapter_id)), ("topic", str(aq.question.topic_id)), ("difficulty", aq.question.difficulty)):
            groups[key][value][1] += 1; groups[key][value][0] += int(is_correct)
        graded.append((aq, selected, is_correct))
    total = len(attempt_questions)
    result_groups = {key: [{"id": group_id, "correct": counts[0], "total": counts[1], "accuracy": round(counts[0] * 100 / counts[1], 2)} for group_id, counts in values.items()] for key, values in groups.items()}
    return {"total_questions": total, "correct": correct, "incorrect": incorrect, "unanswered": unanswered, "accuracy": round(correct * 100 / total, 2) if total else 0, "chapter_results": result_groups["chapter"], "topic_results": result_groups["topic"], "difficulty_results": result_groups["difficulty"], "graded": graded}
