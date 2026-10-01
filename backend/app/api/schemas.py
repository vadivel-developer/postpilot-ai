from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class BootstrapRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    username: str
    password: str


class ChannelResolveRequest(BaseModel):
    input: str = Field(min_length=1, max_length=300)


class ChannelConfirmRequest(BaseModel):
    url: str
    name: str


class GenerateDraftRequest(BaseModel):
    channel_id: int
    card_date: dt.date


class DraftEditRequest(BaseModel):
    post_text: str | None = None
    hashtags: list[str] | None = None
    image_headline: str | None = None
    image_takeaways: list[str] | None = None


class TranscriptPasteRequest(BaseModel):
    text: str = Field(min_length=20, max_length=200_000)


class GeminiKeyRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=400)


class GeminiModelRequest(BaseModel):
    model: str = Field(min_length=3, max_length=80)


class NvidiaKeyRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=400)


class NvidiaModelRequest(BaseModel):
    model: str = Field(min_length=3, max_length=120)


class LinkedInAppRequest(BaseModel):
    client_id: str = Field(min_length=3, max_length=200)
    client_secret: str = Field(min_length=3, max_length=400)


class BrandSettingsRequest(BaseModel):
    brand_name: str | None = None
    image_footer: str | None = None
    brand_color_primary: str | None = None
    brand_color_secondary: str | None = None
    brand_color_text: str | None = None
    image_template: str | None = None
    content_tone: str | None = None
    output_language: str | None = None
    timezone: str | None = None
    default_channel_id: int | None = None
    retry_limit: int | None = None
    llm_provider: str | None = None
    ollama_model: str | None = None
    ollama_base_url: str | None = None
    whisper_fallback: bool | None = None
    whisper_model: str | None = None
