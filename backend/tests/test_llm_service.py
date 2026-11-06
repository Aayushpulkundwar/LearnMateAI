import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.llm_service import OllamaLLMService


def _async_client(response=None, post_error=None, get_error=None):
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client.get = AsyncMock(return_value=response)
    if post_error:
        client.post.side_effect = post_error
    if get_error:
        client.get.side_effect = get_error
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


class OllamaLLMServiceTests(unittest.TestCase):
    def test_quiz_json_schema_is_sent_without_changing_default_chat_payload(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {'response': '{"questions":[]}'}
        client = _async_client(response=response)
        schema = {'type': 'object', 'properties': {'questions': {'type': 'array'}}}
        with patch('app.services.llm_service.httpx.AsyncClient', return_value=client):
            asyncio.run(OllamaLLMService().generate('quiz', json_mode=True, json_schema=schema))
        self.assertEqual(client.post.call_args.kwargs['json']['format'], schema)
        self.assertEqual(client.post.call_args.kwargs['json']['options']['num_ctx'], 4096)
        self.assertEqual(client.post.call_args.kwargs['json']['options']['num_predict'], 2400)
        client.post.reset_mock()
        with patch('app.services.llm_service.httpx.AsyncClient', return_value=client):
            asyncio.run(OllamaLLMService().generate('chat'))
        self.assertNotIn('format', client.post.call_args.kwargs['json'])

    def test_teacher_generation_budgets_reach_ollama_without_switching_models(self):
        response = MagicMock(); response.raise_for_status.return_value = None
        response.json.return_value = {'response': 'A teacher explanation. [Source 1]'}
        for tokens in [256, 512, 1024]:
            client = _async_client(response=response)
            service = OllamaLLMService()
            with patch('app.services.llm_service.httpx.AsyncClient', return_value=client):
                asyncio.run(service.generate('Question', 'Teacher instructions', num_ctx=8192, num_predict=tokens))
            payload = client.post.call_args.kwargs['json']
            self.assertEqual(payload['model'], service.model)
            self.assertEqual(payload['options']['num_ctx'], 8192)
            self.assertEqual(payload['options']['num_predict'], tokens)
            self.assertNotIn('format', payload)

    def setUp(self):
        self.service = OllamaLLMService(base_url="http://ollama.test", model="llama3:8b")

    def test_availability_accepts_exact_qualified_tag(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"models": [{"name": "llama3:8b"}]}
        client = _async_client(response=response)
        with patch("app.services.llm_service.httpx.AsyncClient", return_value=client):
            asyncio.run(self.service.check_availability())

    def test_availability_reports_missing_configured_model(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"models": [{"name": "other:latest"}]}
        client = _async_client(response=response)
        with patch("app.services.llm_service.httpx.AsyncClient", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "llama3:8b.*unavailable"):
                asyncio.run(self.service.check_availability())

    def test_generation_timeout_is_safe_to_callers_and_logged(self):
        client = _async_client(post_error=httpx.ReadTimeout("slow"))
        with patch("app.services.llm_service.httpx.AsyncClient", return_value=client):
            with self.assertLogs("app.services.llm_service", level="ERROR") as logs:
                with self.assertRaisesRegex(RuntimeError, "generation timed out"):
                    asyncio.run(self.service.generate("Question"))
        self.assertIn("Ollama generation timed out", "\n".join(logs.output))

    def test_connection_failure_is_safe_to_callers_and_logged(self):
        client = _async_client(post_error=httpx.ConnectError("offline"))
        with patch("app.services.llm_service.httpx.AsyncClient", return_value=client):
            with self.assertLogs("app.services.llm_service", level="ERROR") as logs:
                with self.assertRaisesRegex(RuntimeError, "server is unreachable"):
                    asyncio.run(self.service.generate("Question"))
        self.assertIn("Ollama connection failed", "\n".join(logs.output))
