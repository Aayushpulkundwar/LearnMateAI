import logging
from typing import AsyncGenerator

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


class OllamaLLMService:
    """LLM service interfacing exclusively with the configured local Ollama model."""

    def __init__(self, base_url: str = settings.OLLAMA_BASE_URL, model: str = settings.LLM_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model

    @property
    def generation_timeout(self) -> float:
        return settings.OLLAMA_GENERATION_TIMEOUT_SECONDS

    async def check_availability(self) -> None:
        """Confirm Ollama is reachable and has the configured generation model."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            logger.exception("Ollama availability check failed: url=%s", self.base_url)
            raise RuntimeError("Ollama server is unavailable.") from exc
        except ValueError as exc:
            logger.exception("Ollama tags response was invalid JSON: url=%s", self.base_url)
            raise RuntimeError("Ollama returned an invalid availability response.") from exc

        models = payload.get("models") if isinstance(payload, dict) else None
        available_names = {
            str(item.get("name"))
            for item in models or []
            if isinstance(item, dict) and item.get("name")
        }
        accepted_names = {self.model}
        if ":" not in self.model:
            accepted_names.add(f"{self.model}:latest")
        if not available_names.intersection(accepted_names):
            logger.error(
                "Configured Ollama model is unavailable: model=%s url=%s available_models=%s",
                self.model,
                self.base_url,
                sorted(available_names),
            )
            raise RuntimeError(f"Configured Ollama model '{self.model}' is unavailable.")

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Generate one non-streaming answer from Ollama's /api/generate endpoint."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "system": system_prompt,
            "options": {"temperature": settings.LLM_TEMPERATURE},
        }
        try:
            async with httpx.AsyncClient(timeout=self.generation_timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.ConnectError as exc:
            logger.exception("Ollama connection failed: model=%s url=%s", self.model, url)
            raise RuntimeError("Ollama server is unreachable.") from exc
        except httpx.TimeoutException as exc:
            logger.exception(
                "Ollama generation timed out: model=%s url=%s timeout_seconds=%s",
                self.model,
                url,
                self.generation_timeout,
            )
            raise RuntimeError("Ollama generation timed out.") from exc
        except httpx.HTTPStatusError as exc:
            logger.exception(
                "Ollama generation returned HTTP error: model=%s url=%s status=%s",
                self.model,
                url,
                exc.response.status_code,
            )
            raise RuntimeError("Ollama returned an error while generating a response.") from exc
        except httpx.HTTPError as exc:
            logger.exception("Ollama generation request failed: model=%s url=%s", self.model, url)
            raise RuntimeError("Ollama generation request failed.") from exc

        try:
            data = response.json()
        except ValueError as exc:
            logger.exception("Ollama generation returned invalid JSON: model=%s url=%s", self.model, url)
            raise RuntimeError("Ollama returned an invalid generation response.") from exc
        response_text = data.get("response", "") if isinstance(data, dict) else ""
        if not isinstance(response_text, str) or not response_text.strip():
            logger.error("Ollama generation returned an empty response: model=%s url=%s", self.model, url)
            raise RuntimeError("Ollama returned an empty generation response.")
        return response_text.strip()

    async def generate_stream(self, prompt: str, system_prompt: str = "") -> AsyncGenerator[str, None]:
        """Streaming generator emitting raw Ollama JSON lines for the existing SSE route."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "system": system_prompt,
            "options": {"temperature": settings.LLM_TEMPERATURE},
        }
        try:
            async with httpx.AsyncClient(timeout=self.generation_timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line:
                            yield line
        except httpx.HTTPError as exc:
            logger.exception("Ollama streaming generation failed: model=%s url=%s", self.model, url)
            raise RuntimeError("Ollama streaming generation failed.") from exc


llm_service = OllamaLLMService()
