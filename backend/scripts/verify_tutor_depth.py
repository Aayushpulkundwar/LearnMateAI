"""Measure retrieval, then optionally exercise the real authenticated tutor API.

python -m scripts.verify_tutor_depth [--live depths|others]
Live test accounts and sessions are rolled back. Model responses are never mocked.
"""
import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import AsyncSessionLocal, async_engine, get_async_db
from app.main import app
from app.models.learning import Grade, Subject
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.embedding_service import embedding_service
from app.services.retrieval_service import retrieval_service
from app.services.context_selection import select_context_chunks
from app.services.retrieval_quality import evidence_tier, lexical_query

QUESTIONS = ['What is a chemical reaction?', 'What is photosynthesis?', 'Explain the difference between acids and bases.',
             'What happens when magnesium burns in oxygen?', 'Explain displacement reactions with examples.']


async def curriculum():
    async with AsyncSessionLocal() as db:
        grade = await db.scalar(select(Grade).where(Grade.name == 'Class 10'))
        subject = await db.scalar(select(Subject).where(Subject.grade_id == grade.id, Subject.name == 'Science'))
        return grade, subject


def save(name, payload):
    folder = Path('verification'); folder.mkdir(exist_ok=True)
    (folder / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


async def measure():
    grade, subject = await curriculum()
    vectors = await embedding_service.get_embeddings_batch(QUESTIONS)
    report = {'model': settings.EMBEDDING_MODEL, 'grade_id': str(grade.id), 'subject_id': str(subject.id),
              'top_k': settings.RETRIEVAL_TOP_K, 'dense_threshold': settings.RELEVANCE_THRESHOLD, 'lexical_threshold': settings.LEXICAL_RELEVANCE_THRESHOLD, 'questions': []}
    for question, embedding in zip(QUESTIONS, vectors):
        outputs = {}
        for label, educational in [('before', False), ('after', True)]:
            rows = await retrieval_service.retrieve_chunks(embedding, query_text=question, grade_id=grade.id, subject_id=subject.id,
                top_k=settings.RETRIEVAL_TOP_K, educational=educational)
            chunks = [row.__dict__ for row in rows]
            if educational:
                selected = select_context_chunks(chunks, minimum_similarity=settings.CONTEXT_MIN_SIMILARITY,
                    maximum_similarity_drop=settings.CONTEXT_MAX_SIMILARITY_DROP, minimum_lexical_score=settings.LEXICAL_RELEVANCE_THRESHOLD)
            else:
                # The prior selector admitted every positive lexical score.
                best = chunks[0]['similarity_score'] if chunks else 0
                selected = chunks[:1] + [chunk for chunk in chunks[1:] if
                    (chunk['similarity_score'] >= settings.CONTEXT_MIN_SIMILARITY and best - chunk['similarity_score'] <= settings.CONTEXT_MAX_SIMILARITY_DROP)
                    or (chunk['lexical_rank'] is not None and chunk['lexical_score'] > 0)]
            outputs[label] = {'selected_ids': [chunk['id'] for chunk in selected], 'results': [
                {**row.__dict__, 'evidence_tier': evidence_tier(row.content, question)} for row in rows]}
        report['questions'].append({'question': question, 'lexical_query': lexical_query(question), **outputs})
        print(json.dumps({'question': question, **{label: [{'page': row['page_number'], 'chapter': row['chapter'], 'dense': round(row['similarity_score'], 4), 'lexical': round(row['lexical_score'], 4), 'tier': row['evidence_tier']} for row in outputs[label]['results'][:3]] for label in outputs}}), flush=True)
    save('tutor_retrieval.json', report)


async def live(group, only_depth=None):
    import app.graph.nodes as nodes
    original_quality = nodes.answer_quality_issues
    def traced_quality(answer, chunks):
        issues, audit = original_quality(answer, chunks)
        if issues:
            print(json.dumps({'rejected_draft': answer, 'quality_issues': issues}, ensure_ascii=True), flush=True)
        return issues, audit
    nodes.answer_quality_issues = traced_quality
    if settings.ENVIRONMENT.lower() not in {'local', 'development', 'staging'}:
        raise RuntimeError('Run live checks only against a local/staging stack.')
    grade, subject = await curriculum()
    cases = [(QUESTIONS[0], depth) for depth in ['brief', 'standard', 'detailed']] if group == 'depths' else [(q, 'standard') for q in QUESTIONS[1:]]
    report = {'model': settings.LLM_MODEL, 'grade': grade.name, 'subject_id': str(subject.id), 'results': []}
    if only_depth:
        if group != 'depths': raise ValueError('--depth is only valid with --live depths')
        cases = [(question, depth) for question, depth in cases if depth == only_depth]
        previous = Path('verification/tutor_live_depths.json')
        if previous.exists():
            saved = json.loads(previous.read_text(encoding='utf-8'))
            if saved.get('model') == report['model'] and saved.get('subject_id') == report['subject_id']:
                report['results'] = [result for result in saved['results'] if result['depth'] != only_depth]
    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            async with AsyncSession(bind=connection, expire_on_commit=False, autoflush=False, join_transaction_mode='create_savepoint') as db:
                async def override(): yield db
                app.dependency_overrides[get_async_db] = override
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://depth.test') as client:
                    registered = await client.post('/api/v1/auth/register', json={'email': f'depth-{uuid4().hex}@example.com', 'password': 'Temporary verification password', 'grade_id': str(grade.id)})
                    assert registered.status_code == 201, registered.text
                    for question, depth in cases:
                        print(f'LIVE {depth}: {question}', flush=True)
                        response = await client.post('/api/v1/query/', json={'question': question, 'subject_id': str(subject.id), 'explanation_depth': depth})
                        body = response.json()
                        record = {'question': question, 'depth': depth, 'status': response.status_code, **body}
                        record['words'] = len(body.get('answer', '').split())
                        for citation in body.get('citations', []):
                            source = await db.get(Chunk, UUID(citation['chunk_id']))
                            document = await db.get(Document, UUID(citation['document_id']))
                            assert source.document_id == document.id
                            assert document.grade_id == grade.id and document.subject_id == subject.id
                            assert source.page_number == citation['page_number'] and document.title == citation['document_title']
                        report['results'].append(record)
                        if group == 'depths': report['results'].sort(key=lambda result: ['brief', 'standard', 'detailed'].index(result['depth']))
                        save(f'tutor_live_{group}.json', report)
                        print(json.dumps(record, ensure_ascii=False), flush=True)
        finally:
            nodes.answer_quality_issues = original_quality
            app.dependency_overrides.pop(get_async_db, None)
            await transaction.rollback()
    assert all(result['status'] == 200 for result in report['results']), 'One or more live requests failed; see the saved report.'
    if group == 'depths':
        assert all(not result['is_refused'] and result['citations'] for result in report['results'])
        counts = [result['words'] for result in report['results']]
        if len(counts) == 3: assert counts[0] < counts[1] < counts[2], f'Depth separation needs review: {counts}'


async def main(group, depth=None):
    if group: await live(group, depth)
    else: await measure()
    await async_engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', choices=['depths', 'others'])
    parser.add_argument('--depth', choices=['brief', 'standard', 'detailed'], help='Recheck one depth while retaining the other recorded live results.')
    args = parser.parse_args()
    asyncio.run(main(args.live, args.depth))
