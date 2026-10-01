"""Client for a locally-running Ollama server (https://ollama.com), used as a free, offline
alternative to Gemini when no Gemini key/quota is available. Mirrors GeminiClient's interface
(`generate_structured`, `test_connection`) so the LangGraph pipeline nodes work unchanged
regardless of which provider is selected in Settings.

Ollama's /api/chat supports a `format` field carrying a JSON schema for structured output
(Ollama >= 0.5); the model is instructed to return only JSON matching that schema.
"""

from __future__ import annotations

import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger("ltp.ollama")

T = TypeVar("T", bound=BaseModel)

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:latest"
# A representative list for the Settings dropdown; any locally-pulled model name works too.
SUPPORTED_MODELS = ["llama3.1:latest", "qwen2.5:latest", "llama3.2:latest", "qwen3:4b", "qwen3:1.7b"]


class OllamaError(Exception):
    kind = "unknown"

    def __init__(self, message: str, kind: str | None = None):
        super().__init__(message)
        if kind:
            self.kind = kind


class OllamaConnectionError(OllamaError):
    kind = "connection"


class OllamaModelError(OllamaError):
    kind = "unsupported_model"


class OllamaTimeoutError(OllamaError):
    kind = "timeout"


class OllamaClient:
    def __init__(self, base_url: str, model: str, max_retries: int = 2, timeout_s: int = 600):
        # CPU-only local inference on a full transcript chunk can genuinely take several
        # minutes per call; a short timeout here would misreport a slow-but-working model
        # as broken.
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_retries = max_retries
        self.timeout_s = timeout_s

    async def test_connection(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            names = {m.get("name") for m in resp.json().get("models", [])}
            if self.model not in names:
                return False, f"Ollama is reachable, but model '{self.model}' is not pulled. Run: ollama pull {self.model}"
            return True, f"Connected to Ollama at {self.base_url}. Model '{self.model}' is available."
        except httpx.ConnectError:
            return False, f"Could not reach Ollama at {self.base_url}. Is `ollama serve` running?"
        except Exception as exc:  # network/parse errors
            return False, f"Could not reach Ollama: {exc}"

    async def generate_structured(self, *, system_instruction: str, prompt: str, schema: type[T], temperature: float = 0.4) -> T:
        messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}]
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    resp = await client.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": messages,
                            "format": schema.model_json_schema(),
                            "stream": False,
                            "think": False,  # a "thinking" model (e.g. qwen3) emits a long reasoning
                            # trace before its answer otherwise, which is the dominant cost on CPU —
                            # we only need the structured JSON, not the reasoning trace itself.
                            "options": {"temperature": temperature},
                        },
                    )
                except httpx.ConnectError as exc:
                    raise OllamaConnectionError(f"Could not reach Ollama at {self.base_url}. Is `ollama serve` running?", "connection") from exc
                except httpx.TimeoutException as exc:
                    raise OllamaTimeoutError(f"Ollama did not respond within {self.timeout_s}s. The model may be too slow for this machine (CPU-only inference) — try a smaller model.", "timeout") from exc
                if resp.status_code == 404:
                    raise OllamaModelError(f"Model '{self.model}' is not available locally. Run: ollama pull {self.model}", "unsupported_model")
                if resp.status_code >= 400:
                    try:
                        detail = resp.json().get("error", resp.text)
                    except Exception:
                        detail = resp.text
                    detail_lower = str(detail).lower()
                    if "bad_alloc" in detail_lower or "out of memory" in detail_lower or "cuda out of memory" in detail_lower:
                        raise OllamaError(f"Ollama ran out of memory loading '{self.model}'. Try a smaller model (e.g. qwen3:1.7b or llama3.2:latest) or close other memory-heavy apps.", "out_of_memory")
                    raise OllamaError(f"Ollama request failed ({resp.status_code}): {str(detail)[:300]}", "unknown")
                content = resp.json().get("message", {}).get("content", "")
                if not content:
                    last_error = OllamaError("Ollama returned an empty response.")
                    messages.append({"role": "user", "content": "Return ONLY valid JSON matching the schema."})
                    continue
                try:
                    return schema.model_validate_json(content)
                except ValidationError as ve:
                    feedback = str(ve)[:400]
                    last_error = ve
                    log.warning("ollama structured output validation failed (attempt %d): %s", attempt + 1, feedback)
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"That was invalid: {feedback}\nReturn corrected JSON only, matching the schema."})
                    continue
        raise OllamaError(f"Ollama did not return valid structured output after {self.max_retries + 1} attempts: {last_error}", "unknown")
