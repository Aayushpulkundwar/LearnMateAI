import os
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.db import get_async_db
from app.main import app
from app.models.document import Document
from app.models.learning import Grade, Subject
from app.services.retrieval_service import RetrievedChunk


@skipUnless(os.getenv('RUN_TUTOR_INTEGRATION') == '1', 'Requires local PostgreSQL')
class TutorDepthAPITests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(settings.DATABASE_URL)
        self.connection = await self.engine.connect()
        self.transaction = await self.connection.begin()
        self.db = AsyncSession(bind=self.connection, expire_on_commit=False, autoflush=False, join_transaction_mode='create_savepoint')
        async def override(): yield self.db
        app.dependency_overrides[get_async_db] = override
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://depth.test')
        self.grade = await self.db.scalar(select(Grade).where(Grade.name == 'Class 10'))
        self.subject = await self.db.scalar(select(Subject).where(Subject.grade_id == self.grade.id, Subject.name == 'Science'))
        self.document = Document(id=uuid4(), title='Depth integration source', minio_path='test-only.pdf', processing_status='completed', grade_id=self.grade.id, subject_id=self.subject.id)
        self.db.add(self.document); await self.db.flush()
        registered = await self.client.post('/api/v1/auth/register', json={'email': f'depth-api-{uuid4().hex}@example.com', 'password': 'Temporary verification password', 'grade_id': str(self.grade.id)})
        self.assertEqual(registered.status_code, 201, registered.text)

    async def asyncTearDown(self):
        app.dependency_overrides.pop(get_async_db, None)
        await self.client.aclose(); await self.db.close()
        await self.transaction.rollback(); await self.connection.close(); await self.engine.dispose()

    async def test_authenticated_requests_carry_all_modes_through_real_graph_and_same_scope(self):
        source = RetrievedChunk(str(uuid4()), str(self.document.id), self.document.title,
            'In textbook reactions the starting substances are transformed into different substances.', 1, 'Chemical reactions', 0, .8)
        with patch('app.graph.nodes.embedding_service.get_embedding', AsyncMock(return_value=[.1]*1024)), patch('app.graph.nodes.retrieval_service.retrieve_chunks', AsyncMock(return_value=[source])) as retrieve:
            for mode in ['brief', 'standard', 'detailed']:
                with patch('app.graph.nodes.llm_service.generate', AsyncMock(return_value='A reaction forms new substances from the original materials. [Source 1]')) as model:
                    response = await self.client.post('/api/v1/query/', json={'question': 'What is a chemical reaction?', 'subject_id': str(self.subject.id), 'explanation_depth': mode})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertIn(mode.upper()+' MODE', model.await_args.kwargs['system_prompt'])
                    self.assertIn('Class 10', model.await_args.kwargs['system_prompt'])
                    citation = response.json()['citations'][0]
                    self.assertEqual(citation['document_id'], str(self.document.id))
                    self.assertEqual(citation['similarity_score'], .8)
            filters = [call.kwargs for call in retrieve.await_args_list]
            self.assertTrue(all(row['grade_id'] == str(self.grade.id) and row['subject_id'] == str(self.subject.id) and row['top_k'] == 5 for row in filters))

    async def test_invalid_modes_are_rejected_and_foreign_scopes_stay_forbidden(self):
        with patch('app.graph.nodes.llm_service.generate', AsyncMock()) as model:
            for invalid in ['long', '', None]:
                response = await self.client.post('/api/v1/query/', json={'question': 'Question', 'explanation_depth': invalid})
                self.assertEqual(response.status_code, 422)
            response = await self.client.post('/api/v1/query/', json={'question': 'Question', 'subject_id': str(uuid4()), 'explanation_depth': 'detailed'})
            self.assertEqual(response.status_code, 403)
            model.assert_not_awaited()
