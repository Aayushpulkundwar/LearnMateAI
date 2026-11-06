"""Live Ollama/NCERT smoke check. All database writes roll back, including accounts.

python -m scripts.verify_tutor_quiz [--chapter-number 1] [--count 10]
"""
import argparse
import asyncio
import logging
import json
import time
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import async_engine, get_async_db
from app.main import app
from app.models.learning import Chapter, Grade, LearningRecommendation, MasteryHistory, Question, Student, Subject, TopicMastery


async def main(count=10, chapter_number=None, trace=False, difficulty='medium', output=None):
    started = time.monotonic()
    logging.getLogger('app.services.tutor_quiz_service').addHandler(logging.StreamHandler())
    logging.getLogger('app.services.tutor_quiz_service').setLevel(logging.INFO)
    if settings.ENVIRONMENT.lower() not in {'local', 'development', 'staging'}:
        raise RuntimeError('This smoke check is for the local/staging stack only.')
    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            async with AsyncSession(bind=connection, expire_on_commit=False, autoflush=False, join_transaction_mode='create_savepoint') as db:
                async def override():
                    yield db
                app.dependency_overrides[get_async_db] = override
                grade = await db.scalar(select(Grade).where(Grade.name == 'Class 10'))
                subject = await db.scalar(select(Subject).where(Subject.grade_id == grade.id, Subject.name == 'Science'))
                payload = {'subject_id': str(subject.id), 'num_questions': count, 'difficulty': difficulty}
                if chapter_number:
                    chapter = await db.scalar(select(Chapter).where(Chapter.subject_id == subject.id, Chapter.chapter_number == chapter_number))
                    payload['chapter_id'] = str(chapter.id)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://quiz.test', timeout=260) as client:
                    registered = await client.post('/api/v1/auth/register', json={'email': f'quiz-{uuid4().hex}@example.com', 'password': 'Temporary quiz check password', 'grade_id': str(grade.id)})
                    assert registered.status_code == 201, registered.text
                    student_id = registered.json()['student']['id']
                    print('Generating live', count, 'questions', payload, flush=True)
                    from app.services.llm_service import llm_service
                    original_generate = llm_service.generate
                    async def traced(*args, **kwargs):
                        raw = await original_generate(*args, **kwargs)
                        if trace:
                            print('MODEL OUTPUT:', raw[:4000], flush=True)
                        return raw
                    with patch('app.services.tutor_quiz_service.llm_service.generate', side_effect=traced):
                        response = await client.post('/api/v1/query/quiz', json=payload)
                    assert response.status_code == 201, response.text
                    attempt = response.json()
                    assert len(attempt['questions']) == count
                    assert all(q['difficulty'] == difficulty for q in attempt['questions'])
                    assert all('____' not in q['question_text'] and 'Complete the textbook' not in q['question_text'] for q in attempt['questions'])
                    from collections import Counter
                    from app.services.quiz_quality import question_plan
                    assert Counter(q['question_type'] for q in attempt['questions']) == question_plan(difficulty, count)
                    assert len({q['concept'].casefold() for q in attempt['questions']}) == count
                    assert 'is_correct' not in response.text and 'correct_option' not in response.text and 'explanation' not in response.text
                    assert all(len(q['options']) == 4 for q in attempt['questions'])
                    before = await client.get(f"/api/v1/assessments/attempts/{attempt['id']}/results")
                    assert before.status_code == 409
                    # Read keys only from the DB to test deterministic grading;
                    # the pre-submission public API never supplies these.
                    from app.models.learning import AttemptQuestion, QuestionOption
                    rows = (await db.execute(select(AttemptQuestion.id, QuestionOption.id).join(Question, AttemptQuestion.question_id == Question.id).join(QuestionOption, QuestionOption.question_id == Question.id).where(AttemptQuestion.attempt_id == attempt['id'], QuestionOption.is_correct.is_(True)))).all()
                    answers = [{'attempt_question_id': str(aq), 'selected_option_id': str(option)} for aq, option in rows]
                    result = await client.post(f"/api/v1/assessments/attempts/{attempt['id']}/submit", json={'answers': answers})
                    assert result.status_code == 200, result.text
                    assert result.json()['accuracy'] == 100
                    repeated = await client.post(f"/api/v1/assessments/attempts/{attempt['id']}/submit", json={'answers': answers})
                    assert repeated.json() == result.json()
                    review = await client.get(f"/api/v1/assessments/attempts/{attempt['id']}/results")
                    assert review.status_code == 200, review.text
                    for question in review.json()['questions']:
                        assert question['source_title'] and question['source_chunk_id'] and question['chapter_name']
                        assert question['explanation'] and sum(o['is_correct'] for o in question['options']) == 1
                    mastery = await db.scalar(select(func.count(TopicMastery.id)).where(TopicMastery.student_id == student_id))
                    history = await db.scalar(select(func.count(MasteryHistory.id)).where(MasteryHistory.student_id == student_id))
                    assert mastery > 0 and history == mastery
                    recommendations = await db.scalar(select(func.count(LearningRecommendation.id)).where(LearningRecommendation.student_id == student_id))
                    assert recommendations == mastery
                    if output:
                        Path(output).parent.mkdir(parents=True, exist_ok=True)
                        Path(output).write_text(json.dumps({'difficulty': difficulty, 'model': settings.LLM_MODEL, 'elapsed_seconds': round(time.monotonic()-started, 2), 'result': review.json()}, indent=2), encoding='utf-8')
                    print('PASS: live generation, hidden keys, scoring, explanations, citations, mastery, idempotent submission; questions=', count, 'topics=', mastery, flush=True)
        finally:
            app.dependency_overrides.pop(get_async_db, None)
            await transaction.rollback()
    await async_engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--chapter-number', type=int)
    parser.add_argument('--trace', action='store_true', help='Print model output for local debugging (may contain textbook excerpts).')
    parser.add_argument('--difficulty', choices=['easy', 'medium', 'hard'], default='medium')
    parser.add_argument('--output', help='Write the generated review for educational audit, without student data.')
    args = parser.parse_args()
    asyncio.run(main(args.count, args.chapter_number, args.trace, args.difficulty, args.output))
