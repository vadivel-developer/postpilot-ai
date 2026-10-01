"""Thin wrapper around the official Google Gen AI Python SDK (`google-genai`): structured JSON
output validated against a Pydantic schema, bounded retries, and errors classified into the
categories the UI needs to show clearly (invalid key, unsupported model, rate limit, quota, other).

A Gemini API key never guarantees unlimited free usage — quota/rate-limit errors are surfaced
verbatim (truncated), not hidden behind a generic message.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TypeVar

from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError, ServerError
from pydantic import BaseModel, ValidationError

log = logging.getLogger("ltp.gemini")

T = TypeVar("T", bound=BaseModel)

# A currently-supported, fast, inexpensive default — selectable/overridable in Settings.
DEFAULT_MODEL = "gemini-2.5-flash"
SUPPORTED_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"]


class GeminiError(Exception):
    """Base class; `kind` drives what the UI shows."""

    kind = "unknown"

    def __init__(self, message: str, kind: str | None = None):
        super().__init__(message)
        if kind:
            self.kind = kind


class InvalidKeyError(GeminiError):
    kind = "invalid_key"


class UnsupportedModelError(GeminiError):
    kind = "unsupported_model"


class RateLimitError(GeminiError):
    kind = "rate_limit"


class QuotaError(GeminiError):
    kind = "quota"


def _classify(exc: Exception) -> GeminiError:
    msg = str(exc)
    lower = msg.lower()
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status == 401 or "api key not valid" in lower or "api_key_invalid" in lower or "permission denied" in lower:
        return InvalidKeyError("The Gemini API key was rejected. Check it in Settings.", "invalid_key")
    if status == 404 or "not found" in lower and "model" in lower:
        return UnsupportedModelError(f"The selected model is not available for this key: {msg[:200]}", "unsupported_model")
    if status == 429 or "rate limit" in lower:
        return RateLimitError("Gemini rate limit hit — wait a moment and retry.", "rate_limit")
    if "quota" in lower or "resource_exhausted" in lower:
        return QuotaError("Gemini quota exceeded for this key/model. A configured key does not guarantee unlimited free usage.", "quota")
    return GeminiError(f"Gemini request failed: {msg[:300]}", "unknown")


class GeminiClient:
    def __init__(self, api_key: str, model: str, max_retries: int = 2, timeout_s: int = 60):
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.max_retries = max_retries
        self.timeout_s = timeout_s

    async def test_connection(self) -> tuple[bool, str]:
        try:
            await asyncio.wait_for(asyncio.to_thread(self._client.models.get, model=self.model), timeout=self.timeout_s)
            return True, f"Connected. Model '{self.model}' is available for this key."
        except (APIError, ClientError, ServerError) as exc:
            return False, str(_classify(exc))
        except Exception as exc:  # network errors etc.
            return False, f"Could not reach Gemini: {exc}"

    async def generate_structured(self, *, system_instruction: str, prompt: str, schema: type[T], temperature: float = 0.4) -> T:
        """One call, retried on transient failures; validates the response against `schema`,
        re-prompting once more with the validation error if the model's JSON doesn't match."""
        last_error: Exception | None = None
        feedback = ""
        for attempt in range(self.max_retries + 1):
            try:
                full_prompt = prompt if not feedback else f"{prompt}\n\nYour previous answer was invalid: {feedback}\nReturn corrected JSON only."
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    response_mime_type="application/json",
                    response_schema=schema,
                )
                response = await asyncio.wait_for(
                    asyncio.to_thread(self._client.models.generate_content, model=self.model, contents=full_prompt, config=config),
                    timeout=self.timeout_s,
                )
                text = response.text
                if not text:
                    raise GeminiError("Gemini returned an empty response.", "unknown")
                try:
                    return schema.model_validate(json.loads(text))
                except (json.JSONDecodeError, ValidationError) as ve:
                    feedback = str(ve)[:400]
                    last_error = ve
                    log.warning("gemini structured output validation failed (attempt %d): %s", attempt + 1, feedback)
                    continue
            except (APIError, ClientError, ServerError) as exc:
                raise _classify(exc) from exc
            except TimeoutError as exc:
                last_error = exc
                log.warning("gemini call timed out (attempt %d)", attempt + 1)
                continue
        raise GeminiError(f"Gemini did not return valid structured output after {self.max_retries + 1} attempts: {last_error}", "unknown")
