"""Validated BGE-M3 embeddings through the project's local Ollama service."""

import math
from typing import Any, List, Sequence

import httpx

from app.core.config import settings


class EmbeddingValidationError(ValueError):
    """Raised when Ollama returns embeddings unsuitable for pgvector storage."""


class OllamaEmbeddingService:
    """Embedding service backed exclusively by the configured local Ollama model."""

    def __init__(
        self,
        base_url: str = settings.OLLAMA_BASE_URL,
        model: str = settings.EMBEDDING_MODEL,
        expected_dimension: int = settings.EMBEDDING_DIM,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.expected_dimension = expected_dimension

    def _validate_vector(self, embedding: Any) -> List[float]:
        if not isinstance(embedding, list) or not embedding:
            raise EmbeddingValidationError("Ollama returned an empty or malformed embedding.")
        if len(embedding) != self.expected_dimension:
            raise EmbeddingValidationError(
                f"Ollama returned embedding dimension {len(embedding)}; "
                f"expected {self.expected_dimension}."
            )
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in embedding):
            raise EmbeddingValidationError("Ollama embedding contains non-numeric values.")
        vector = [float(value) for value in embedding]
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingValidationError("Ollama embedding contains non-finite values.")
        return vector

    def _validate_response(self, data: Any, expected_count: int) -> List[List[float]]:
        if not isinstance(data, dict):
            raise EmbeddingValidationError("Ollama returned a malformed embedding response.")
        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != expected_count:
            received_count = len(embeddings) if isinstance(embeddings, list) else 0
            raise EmbeddingValidationError(
                f"Ollama returned {received_count} embeddings for {expected_count} inputs."
            )
        return [self._validate_vector(embedding) for embedding in embeddings]

    def _payload(self, texts: Sequence[str]) -> dict[str, Any]:
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise EmbeddingValidationError("Embeddings can only be generated for non-empty text.")
        return {"model": self.model, "input": list(texts)}

    def embed_text(self, text: str) -> List[float]:
        """Generate one validated embedding for a non-empty final chunk."""
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        """Generate one validated embedding for each input using Ollama batching."""
        payload = self._payload(texts)
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(f"{self.base_url}/api/embed", json=payload)
                response.raise_for_status()
                return self._validate_response(response.json(), len(texts))
        except EmbeddingValidationError:
            raise
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Embedding request failed for Ollama model '{self.model}'."
            ) from exc
        except (TypeError, ValueError) as exc:
            raise EmbeddingValidationError("Ollama returned invalid embedding JSON.") from exc

    async def get_embedding(self, text: str) -> List[float]:
        """Async compatibility method for existing callers."""
        return (await self.get_embeddings_batch([text]))[0]

    async def get_embeddings_batch(self, texts: Sequence[str]) -> List[List[float]]:
        """Async validated batch API for callers that already use async code."""
        payload = self._payload(texts)
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(f"{self.base_url}/api/embed", json=payload)
                response.raise_for_status()
                return self._validate_response(response.json(), len(texts))
        except EmbeddingValidationError:
            raise
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Embedding request failed for Ollama model '{self.model}'."
            ) from exc
        except (TypeError, ValueError) as exc:
            raise EmbeddingValidationError("Ollama returned invalid embedding JSON.") from exc


embedding_service = OllamaEmbeddingService()
