"""Concept-generation regression checks; integration writes always roll back."""
import asyncio
import json
import os
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase, skipUnless
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.core.config import settings
from app.core.db import get_async_db
from app.main import app
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.learning import AssessmentAttempt, Chapter, Grade, LearningRecommendation, Question, Subject, TopicMastery
from app.schemas.query import QuizRequest
from app.services.quiz_quality import ConceptQuestion, normalized, question_plan, rejection_reason
from app.services.tutor_quiz_service import content_error, generate_questions, semantic_review

QUOTE = 'Magnesium reacts with oxygen to form magnesium oxide. The substances that undergo chemical change are reactants, while the new substance formed is a product.'
SECOND = 'In a balanced chemical equation the number of atoms of each element is equal on both sides. Mass can neither be created nor destroyed in a chemical reaction.'


def candidate(kind='application', concept='Reactants and products', source=1, difficulty='medium'):
    return dict(question='Magnesium burns in oxygen to form magnesium oxide. Which pair contains only the reactants?',
        options={'A': 'Magnesium and magnesium oxide', 'B': 'Oxygen and magnesium oxide', 'C': 'Magnesium and oxygen', 'D': 'Magnesium oxide alone'},
        correct_answer='C', explanation='Magnesium and oxygen undergo chemical change to produce magnesium oxide, so they are the reactants and magnesium oxide is the product.',
        difficulty=difficulty, question_type=kind, bloom_level='apply', concept=concept,
        learning_objective='Distinguish starting substances from products in a chemical reaction.', sources=[source], evidence=QUOTE,
        misconceptions={'A': 'Confuses a starting material with the product.', 'B': 'Treats the product as another reactant.', 'D': 'Reverses the roles of reactants and product.'})


def second(kind='scenario', difficulty='medium'):
    item = candidate(kind, 'Conservation of atoms', 2, difficulty)
    item.update(question='A student counts unequal numbers of oxygen atoms on the two sides of an equation. What should the student conclude?',
        options={'A': 'Some oxygen atoms were destroyed', 'B': 'Oxygen atoms were created during the reaction', 'C': 'The equation is not balanced', 'D': 'The law of conservation of mass has stopped applying'},
        explanation='A balanced equation contains equal numbers of each type of atom on both sides. Unequal oxygen counts show that this equation is not balanced.',
        learning_objective='Use equal atom counts to evaluate a proposed chemical equation.', evidence=SECOND)
    return item


def source_rows():
    chapter = SimpleNamespace(id=uuid4(), name='Chemical Reactions and Equations')
    return {1: (SimpleNamespace(id=uuid4(), page_number=1), None, QUOTE, chapter),
            2: (SimpleNamespace(id=uuid4(), page_number=2), None, SECOND, chapter)}


class QuizQualityTests(TestCase):
    def setUp(self):
        self.sources = source_rows()
        self.q = ConceptQuestion.model_validate(candidate())
        self.slots = question_plan('medium', 10)

    def reason(self, item, accepted=(), difficulty='medium', sources=None):
        return rejection_reason(ConceptQuestion.model_validate(item), sources or self.sources, accepted, difficulty, self.slots)

    def test_medium_blueprint_and_short_quizzes_keep_diversity(self):
        self.assertEqual(question_plan('medium', 10), Counter(conceptual=2, application=4, scenario=2, analytical=2))
        self.assertEqual(question_plan('medium', 2), Counter(application=1, scenario=1))
        for difficulty in ['easy', 'medium', 'hard']:
            for count in range(1, 11):
                self.assertEqual(sum(question_plan(difficulty, count).values()), count)

    def test_valid_concept_application(self):
        self.assertIsNone(self.reason(candidate()))

    def test_case_punctuation_and_missing_options_are_rejected(self):
        for value in ['MAGNESIUM AND OXYGEN', 'Magnesium and oxygen.']:
            item = candidate(); item['options']['A'] = value
            with self.assertRaises(ValueError): ConceptQuestion.model_validate(item)
        item = candidate(); del item['options']['D']
        with self.assertRaises(ValueError): ConceptQuestion.model_validate(item)

    def test_reject_blank_completion_page_reference_and_corruption(self):
        for text in ['Magnesium burns in ____ to produce an oxide?', 'Complete the textbook statement using its wording?',
                     'Which conclusion is shown on page 12?', 'What does this corrupted \ufffd passage establish?', 'The reaction produces a new substance']:
            item = candidate(); item['question'] = text
            self.assertIsNotNone(self.reason(item))

    def test_reject_unknown_sources_wrong_evidence_and_cross_chapter(self):
        for change in [{'sources': [99]}, {'sources': [1, 1]}, {'evidence': 'This fabricated sentence was not present in the retrieved textbook content.'}]:
            self.assertIsNotNone(self.reason({**candidate(), **change}))
        self.sources[2] = (*self.sources[2][:3], SimpleNamespace(id=uuid4()))
        self.assertIsNotNone(self.reason({**candidate(), 'sources': [1, 2]}))

    def test_concept_and_question_deduplication(self):
        self.assertIsNotNone(self.reason(candidate(), [self.q]))
        item = second(); item['concept'] = 'REACTANTS AND PRODUCTS.'
        self.assertIsNotNone(self.reason(item, [self.q]))
        self.assertIsNone(self.reason(second(), [self.q]))

    def test_reject_wrong_difficulty_bloom_and_missing_misconceptions(self):
        self.assertIsNotNone(self.reason({**candidate(), 'difficulty': 'hard'}))
        self.assertIsNotNone(self.reason({**candidate(), 'bloom_level': 'evaluate'}))
        self.assertIsNotNone(self.reason({**candidate(), 'misconceptions': {'A': 'Not enough alternatives explained'}}))
        self.assertIsNotNone(self.reason({**candidate(), 'question': 'Which equation Mg O 2 -> is balanced?'}))

    def test_error_states_and_request_compatibility(self):
        self.assertEqual(QuizRequest().difficulty, 'medium')
        with self.assertRaises(ValueError): QuizRequest(difficulty='impossible')
        self.assertEqual(content_error([]).status_code, 404)
        for state, code in [('processing',409), ('pending',409), ('failed',409), ('completed',404)]:
            self.assertEqual(content_error([SimpleNamespace(chapter_id=None, processing_status=state)]).status_code, code)


class QuizGenerationTests(IsolatedAsyncioTestCase):
    async def test_only_missing_questions_regenerated_after_semantic_rejection(self):
        calls = []
        async def model(prompt, system='', **kwargs):
            calls.append(prompt)
            if 'verdicts' in kwargs['json_schema']['properties']:
                # First review rejects one item; second approves its replacement.
                if len(calls) == 2:
                    return json.dumps({'verdicts': [dict(id=0, valid=True, supported_answers=['C'], reason=''), dict(id=1, valid=False, supported_answers=['A','C'], reason='Ambiguous alternatives')]})
                return json.dumps({'verdicts': [dict(id=0, valid=True, supported_answers=['C'], reason='')]})
            return json.dumps({'questions': [candidate(), second()] if len(calls) == 1 else [second()]})
        with patch('app.services.tutor_quiz_service.llm_service.generate', side_effect=model):
            result = await generate_questions(source_rows(), QuizRequest(num_questions=2))
        self.assertEqual(len(result), 2)
        self.assertIn('"scenario": 1', calls[2]); self.assertNotIn('"application": 1', calls[2])

    async def test_ambiguous_or_wrong_keys_never_accepted_even_if_reviewer_says_valid(self):
        for answers in [['A', 'C'], ['A'], []]:
            async def model(prompt, system='', **kwargs):
                if 'verdicts' in kwargs['json_schema']['properties']:
                    return json.dumps({'verdicts': [dict(id=0, valid=True, supported_answers=answers, reason='')]})
                return json.dumps({'questions': [candidate()]})
            with patch('app.services.tutor_quiz_service.llm_service.generate', side_effect=model), self.assertRaises(HTTPException) as caught:
                await generate_questions(source_rows(), QuizRequest(num_questions=1))
            self.assertEqual(caught.exception.status_code, 422)

    async def test_malformed_outputs_bounded_and_no_partial_result(self):
        for raw in ['not JSON', '{}', '{"questions": []}', '{"questions": [{"answer": "oxygen", "distractors": []}]}']:
            with patch('app.services.tutor_quiz_service.llm_service.generate', AsyncMock(return_value=raw)) as model, self.assertRaises(HTTPException) as caught:
                await generate_questions(source_rows(), QuizRequest(num_questions=2))
            self.assertEqual(caught.exception.status_code, 422)
            self.assertEqual(model.await_count, 4)

    async def test_missing_and_duplicate_review_verdicts_fail_closed(self):
        q = ConceptQuestion.model_validate(candidate())
        for verdicts in [[], [dict(id=0,valid=True,supported_answers=['C'],reason='')] * 2, [dict(id=99,valid=True,supported_answers=['C'],reason='')]]:
            with patch('app.services.tutor_quiz_service.llm_service.generate', AsyncMock(return_value=json.dumps({'verdicts':verdicts}))):
                self.assertEqual(await semantic_review([q], source_rows(), [], 'medium'), {})


@skipUnless(os.getenv('RUN_QUIZ_INTEGRATION') == '1', 'Requires local PostgreSQL')
class TutorQuizIntegrationTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(settings.DATABASE_URL)
        self.connection = await self.engine.connect(); self.transaction = await self.connection.begin()
        self.db = AsyncSession(bind=self.connection, expire_on_commit=False, autoflush=False, join_transaction_mode='create_savepoint')
        async def override(): yield self.db
        app.dependency_overrides[get_async_db] = override
        self.grade = Grade(name=f'Quiz {uuid4()}'); self.subject = Subject(name='Science', grade=self.grade)
        self.chapter = Chapter(subject=self.subject, name='Chemical Reactions and Equations', chapter_number=1)
        self.db.add(self.chapter); await self.db.flush()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://quiz.test')
        response = await self.client.post('/api/v1/auth/register', json={'email':f'quiz-{uuid4().hex}@example.com','password':'Temporary quiz check password','grade_id':str(self.grade.id)})
        self.student_id = response.json()['student']['id']

    async def asyncTearDown(self):
        await self.client.aclose(); app.dependency_overrides.pop(get_async_db, None)
        await self.db.close(); await self.transaction.rollback(); await self.connection.close(); await self.engine.dispose()

    async def test_scope_privacy_concept_mastery_scoring_and_failures(self):
        payload = {'subject_id':str(self.subject.id), 'num_questions':2}
        self.assertEqual((await self.client.post('/api/v1/query/quiz', json=payload)).status_code, 404)
        document = Document(title='Science chapter', minio_path='quiz-test', grade_id=self.grade.id, subject_id=self.subject.id, chapter_id=self.chapter.id, processing_status='pending')
        self.db.add(document); await self.db.flush()
        self.assertEqual((await self.client.post('/api/v1/query/quiz', json=payload)).status_code, 409)
        document.processing_status='completed'; await self.db.flush()
        self.assertEqual((await self.client.post('/api/v1/query/quiz', json=payload)).status_code, 404)
        for i, quote in enumerate([QUOTE, SECOND]):
            self.db.add(Chunk(id=uuid4(),document_id=document.id,content=(quote+' ')*3,embedding=[.01]*1024,page_number=i+1,chapter=self.chapter.name,chunk_index=i))
        await self.db.flush()
        async def model(prompt, system='', **kwargs):
            if 'verdicts' in kwargs['json_schema']['properties']:
                items=json.loads(prompt.split('ITEMS:\n')[1])
                return json.dumps({'verdicts':[dict(id=i,valid=True,supported_answers=['C'],reason='') for i in range(len(items))]})
            passages=json.loads(prompt.split('PASSAGES:\n')[1])
            first=candidate(); other=second()
            first['sources']=[next(p['source'] for p in passages if QUOTE in p['passage'])]
            other['sources']=[next(p['source'] for p in passages if SECOND in p['passage'])]
            return json.dumps({'questions':[first,other]})
        for chapter_specific in [False, True]:
            request={**payload, **({'chapter_id':str(self.chapter.id)} if chapter_specific else {})}
            with patch('app.services.tutor_quiz_service.llm_service.generate',side_effect=model):
                response=await self.client.post('/api/v1/query/quiz',json=request)
            self.assertEqual(response.status_code,201,response.text)
            for private in ['is_correct','correct_answer','explanation','misconceptions','evidence','learning_objective']:
                self.assertNotIn('"'+private+'"',response.text)
            attempt=response.json(); self.assertEqual(len({q['concept'] for q in attempt['questions']}),2)
            url=f"/api/v1/assessments/attempts/{attempt['id']}"
            self.assertEqual((await self.client.get(url+'/results')).status_code,409)
            answers=[]
            for i,q in enumerate(attempt['questions']):
                text='Magnesium and oxygen' if i==0 else 'Oxygen atoms were created during the reaction'
                option=next(o for o in q['options'] if o['option_text']==text)
                answers.append({'attempt_question_id':q['id'],'selected_option_id':option['id']})
            scored=await self.client.post(url+'/submit',json={'answers':answers})
            self.assertEqual(scored.status_code,200,scored.text); self.assertEqual(scored.json()['accuracy'],50)
            repeated=await self.client.post(url+'/submit',json={'answers':answers}); self.assertEqual(scored.json(),repeated.json())
            review=(await self.client.get(url+'/results')).json()
            for q in review['questions']:
                self.assertTrue(q['source_chunk_ids'] and q['evidence'] and q['topic_id'])
                self.assertEqual(sum(o['is_correct'] for o in q['options']),1)
            # Another authenticated student cannot see this attempt or its answer key.
            cookies=httpx.Cookies(self.client.cookies)
            await self.client.post('/api/v1/auth/register',json={'email':f'quiz-{uuid4().hex}@example.com','password':'Temporary quiz check password','grade_id':str(self.grade.id)})
            self.assertEqual((await self.client.get(url)).status_code,404)
            self.assertEqual((await self.client.get(url+'/results')).status_code,404)
            self.client.cookies=cookies
        self.assertEqual(await self.db.scalar(select(func.count(TopicMastery.id)).where(TopicMastery.student_id==self.student_id)),2)
        self.assertEqual(await self.db.scalar(select(func.count(LearningRecommendation.id)).where(LearningRecommendation.student_id==self.student_id)),2)
        self.assertEqual(await self.db.scalar(select(func.count(Question.id)).where(Question.subject_id==self.subject.id,Question.validation_status=='validated')),0)
        async def slow(*args,**kwargs): await asyncio.sleep(1)
        with patch('app.services.tutor_quiz_service.GENERATION_SECONDS',.01), patch('app.services.tutor_quiz_service.llm_service.generate',side_effect=slow):
            response=await self.client.post('/api/v1/query/quiz',json=payload)
            self.assertEqual(response.status_code,504)
        with patch('app.services.tutor_quiz_service.llm_service.generate',AsyncMock(return_value='{"questions":[]}')):
            response=await self.client.post('/api/v1/query/quiz',json=payload)
            self.assertEqual(response.status_code,422)
        self.assertEqual((await self.client.post('/api/v1/query/quiz',json={**payload,'subject_id':str(uuid4())})).status_code,403)
        self.assertEqual((await self.client.post('/api/v1/query/quiz',json={**payload,'topic_id':str(uuid4())})).status_code,403)
        self.assertEqual(await self.db.scalar(select(func.count(AssessmentAttempt.id)).where(AssessmentAttempt.student_id==self.student_id)),2)
