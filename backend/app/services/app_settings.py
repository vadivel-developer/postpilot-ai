"""Brand and application preferences — non-secret key/value settings editable in the UI."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.config import settings as env_settings
from app.models.db import AppSetting

DEFAULTS: dict[str, Any] = {
    "brand_name": "My Company",
    "image_footer": "Generated with LearnToPost AI",
    "brand_color_primary": "#1F4B99",
    "brand_color_secondary": "#0A66C2",
    "brand_color_text": "#FFFFFF",
    "image_template": "classic",  # "classic" | "minimal"
    "content_tone": "professional",  # "professional" | "conversational" | "enthusiastic"
    "output_language": env_settings.default_output_language,
    "timezone": env_settings.default_timezone,
    "default_channel_id": None,
    "retry_limit": env_settings.job_max_attempts,
    "llm_provider": "gemini",  # "gemini" | "ollama" | "nvidia"
    "ollama_model": "llama3.1:latest",
    "ollama_base_url": "http://localhost:11434",
    "whisper_fallback": True,  # when YouTube has no transcript panel, try local Whisper on the audio
    "whisper_model": "base",  # "tiny" | "base" | "small" | "medium"
}


def get_all(db: Session) -> dict[str, Any]:
    rows = {row.key: row.value for row in db.query(AppSetting).all()}
    merged = dict(DEFAULTS)
    merged.update(rows)
    return merged


def get(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    return row.value if row is not None else DEFAULTS.get(key)


def set_many(db: Session, values: dict[str, Any]) -> None:
    for key, value in values.items():
        if key not in DEFAULTS:
            continue
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    db.commit()
