"""Client for NVIDIA's hosted NIM API (https://build.nvidia.com), an OpenAI-compatible chat
completions endpoint serving various open models (Llama, Nemotron, Mistral, etc.) on NVIDIA's
cloud GPUs. An alternative to Gemini (cloud, needs a different API key) and Ollama (local, needs a
capable GPU/CPU on this machine) — this runs in the cloud but on different infrastructure/pricing
than Gemini, and needs an API key from build.nvidia.com.

NIM's structured-output support varies by model, so — like the Ollama client — this asks for JSON
via `response_format: {"type": "json_object"}` plus an explicit schema in the prompt, validates the
result against the Pydantic schema, and retries with the validation error as feedback rather than
assuming a model-side JSON-schema guarantee.
"""

from __future__ import annotations

import json
import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger("ltp.nvidia")

T = TypeVar("T", bound=BaseModel)

BASE_URL = "https://integrate.api.nvidia.com/v1"
# NVIDIA retires NIM-hosted models on a rolling schedule (a previous default,
# meta/llama-3.1-8b-instruct, returned HTTP 410 Gone after its end-of-life date) — these were
# confirmed live against https://integrate.api.nvidia.com/v1/models at the time this was written,
# but if NVIDIA retires one of these too, Settings lets you type any other model ID your account has.
DEFAULT_MODEL = "nvidia/llama-3.1-nemotron-70b-instruct"
SUPPORTED_MODELS = [
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "mistralai/mistral-7b-instruct-v0.3",
    "mistralai/mistral-large-2-instruct",
    "nv-mistralai/mistral-nemo-12b-instruct",
]


class NvidiaError(Exception):
    kind = "unknown"

    def __init__(self, message: str, kind: str | None = None):
        super().__init__(message)
        if kind:
            self.kind = kind


class InvalidKeyError(NvidiaError):
    kind = "invalid_key"


class UnsupportedModelError(NvidiaError):
    kind = "unsupported_model"


class RateLimitError(NvidiaError):
    kind = "rate_limit"


def _classify(status: int, body_text: str) -> NvidiaError:
    lower = body_text.lower()
    if status == 401 or "invalid api key" in lower or "unauthorized" in lower:
        return InvalidKeyError("The NVIDIA API key was rejected. Check it in Settings.", "invalid_key")
    if status == 404 or status == 410 or ("model" in lower and ("not found" in lower or "end of life" in lower or "no longer available" in lower)):
        return UnsupportedModelError(f"The selected model is no longer available: {body_text[:200]}", "unsupported_model")
    if status == 429:
        return RateLimitError("NVIDIA NIM rate limit hit — wait a moment and retry.", "rate_limit")
    return NvidiaError(f"NVIDIA NIM request failed ({status}): {body_text[:300]}", "unknown")


class NvidiaClient:
    def __init__(self, api_key: str, model: str, max_retries: int = 2, timeout_s: int = 120):
        self.api_key = api_key
        self.model = model
        self.max_retries = max_retries
        self.timeout_s = timeout_s

    async def test_connection(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(f"{BASE_URL}/models", headers={"Authorization": f"Bearer {self.api_key}"})
            if resp.status_code >= 400:
                raise _classify(resp.status_code, resp.text)
            names = {m.get("id") for m in resp.json().get("data", [])}
            if names and self.model not in names:
                return False, f"Connected, but model '{self.model}' was not found in this account's list of available models."
            return True, f"Connected to NVIDIA NIM. Model '{self.model}' is available."
        except NvidiaError as exc:
            return False, str(exc)
        except Exception as exc:  # network errors etc.
            return False, f"Could not reach NVIDIA NIM: {exc}"

    async def generate_structured(self, *, system_instruction: str, prompt: str, schema: type[T], temperature: float = 0.4) -> T:
        schema_json = json.dumps(schema.model_json_schema())
        messages = [
            {"role": "system", "content": f"{system_instruction}\n\nRespond with ONLY a single JSON object matching this schema, no prose, no markdown fences:\n{schema_json}"},
            {"role": "user", "content": prompt},
        ]
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            for attempt in range(self.max_retries + 1):
                resp = await client.post(
                    f"{BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "response_format": {"type": "json_object"},
                        "stream": False,
                    },
                )
                if resp.status_code >= 400:
                    raise _classify(resp.status_code, resp.text)
                content = resp.json()["choices"][0]["message"]["content"]
                if not content:
                    last_error = NvidiaError("NVIDIA NIM returned an empty response.")
                    messages.append({"role": "user", "content": "Return ONLY valid JSON matching the schema."})
                    continue
                try:
                    return schema.model_validate_json(content)
                except (json.JSONDecodeError, ValidationError) as ve:
                    feedback = str(ve)[:400]
                    last_error = ve
                    log.warning("nvidia structured output validation failed (attempt %d): %s", attempt + 1, feedback)
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"That was invalid: {feedback}\nReturn corrected JSON only, matching the schema."})
                    continue
        raise NvidiaError(f"NVIDIA NIM did not return valid structured output after {self.max_retries + 1} attempts: {last_error}", "unknown")
