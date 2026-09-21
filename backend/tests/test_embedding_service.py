import math
import unittest
from unittest.mock import MagicMock, patch

from app.services.embedding_service import EmbeddingValidationError, OllamaEmbeddingService


class EmbeddingServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = OllamaEmbeddingService(
            base_url="http://ollama.test",
            model="bge-m3",
            expected_dimension=3,
        )

    def _client_response(self, payload):
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        client = MagicMock()
        client.post.return_value = response
        client.__enter__.return_value = client
        return client

    def test_one_text_produces_one_validated_embedding(self):
        client = self._client_response({"embeddings": [[0.1, 0.2, 0.3]]})
        with patch("app.services.embedding_service.httpx.Client", return_value=client):
            embedding = self.service.embed_text("A valid chunk.")

        self.assertEqual(embedding, [0.1, 0.2, 0.3])

    def test_empty_embedding_is_rejected(self):
        client = self._client_response({"embeddings": [[]]})
        with patch("app.services.embedding_service.httpx.Client", return_value=client):
            with self.assertRaisesRegex(EmbeddingValidationError, "empty"):
                self.service.embed_text("A valid chunk.")

    def test_wrong_dimension_is_rejected(self):
        client = self._client_response({"embeddings": [[0.1, 0.2]]})
        with patch("app.services.embedding_service.httpx.Client", return_value=client):
            with self.assertRaisesRegex(EmbeddingValidationError, "dimension"):
                self.service.embed_text("A valid chunk.")

    def test_non_finite_values_are_rejected(self):
        client = self._client_response({"embeddings": [[0.1, math.nan, 0.3]]})
        with patch("app.services.embedding_service.httpx.Client", return_value=client):
            with self.assertRaisesRegex(EmbeddingValidationError, "non-finite"):
                self.service.embed_text("A valid chunk.")

    def test_batch_count_mismatch_is_rejected(self):
        client = self._client_response({"embeddings": [[0.1, 0.2, 0.3]]})
        with patch("app.services.embedding_service.httpx.Client", return_value=client):
            with self.assertRaisesRegex(EmbeddingValidationError, "2 inputs"):
                self.service.embed_texts(["First chunk.", "Second chunk."])

    def test_ollama_http_failure_is_controlled(self):
        client = MagicMock()
        client.__enter__.return_value = client
        client.post.side_effect = __import__("httpx").ConnectError("offline")
        with patch("app.services.embedding_service.httpx.Client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "Embedding request failed"):
                self.service.embed_text("A valid chunk.")
