from typing import AsyncGenerator, Dict, Any, List
import httpx
from app.core.config import settings


class OllamaLLMService:
    """LLM service interfacing exclusively with local Llama model hosted on Ollama."""

    def __init__(self, base_url: str = settings.OLLAMA_BASE_URL, model: str = settings.LLM_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Synchronous/non-streaming response generation call to Ollama /api/generate."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "system": system_prompt,
            "options": {
                "temperature": 0.2  # Low temperature for strict textbook adherence
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Ollama server is unreachable at {self.base_url}. Single local provider requirement failed."
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to generate text from Ollama model '{self.model}': {str(exc)}") from exc

    async def generate_stream(self, prompt: str, system_prompt: str = "") -> AsyncGenerator[str, None]:
        """Streaming generator emitting answer tokens via SSE/chunked streams."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "system": system_prompt,
            "options": {
                "temperature": 0.2
            }
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line:
                            # TODO: Parse json lines from Ollama streaming output and yield delta text content
                            yield line
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Ollama server is unreachable at {self.base_url}. Single local provider requirement failed."
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Ollama streaming generation error: {str(exc)}") from exc


llm_service = OllamaLLMService()
