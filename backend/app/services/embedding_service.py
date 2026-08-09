from typing import List
import httpx
from app.core.config import settings


class OllamaEmbeddingService:
    """Embedding service interfacing exclusively with local BGE-M3 model hosted on Ollama."""

    def __init__(self, base_url: str = settings.OLLAMA_BASE_URL, model: str = settings.EMBEDDING_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def get_embedding(self, text: str) -> List[float]:
        """Fetch vector embedding for a single string using Ollama embedding endpoint."""
        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                embedding = data.get("embedding", [])
                
                # Verify dimension consistency
                if len(embedding) != settings.EMBEDDING_DIM:
                    # TODO: Add logging or dimension normalization if Ollama returns variable length vectors
                    pass
                
                return embedding
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Ollama server is unreachable at {self.base_url}. Please ensure Ollama container is running.") from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to generate embedding with Ollama model '{self.model}': {str(exc)}") from exc

    async def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Batch embedding helper for chunk processing."""
        # TODO: Implement parallel or batched Ollama embedding calls for improved ingestion speed
        embeddings = []
        for text in texts:
            emb = await self.get_embedding(text)
            embeddings.append(emb)
        return embeddings


embedding_service = OllamaEmbeddingService()
