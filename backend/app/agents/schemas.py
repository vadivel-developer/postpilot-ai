"""Pydantic schemas for every Gemini-produced structured output. Also drive the SDK's
`response_schema` JSON-mode constraint, so a response either matches this shape or is retried."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LanguageDetection(BaseModel):
    language_code: str = Field(description="ISO 639-1 code, e.g. 'ta', 'en', 'hi'")
    language_name: str
    needs_translation: bool


class TranslationResult(BaseModel):
    english_text: str = Field(description="Full transcript translated to English, preserving names, numbers and technical terms")


class KeyPoint(BaseModel):
    text: str = Field(max_length=280)
    segment_ids: list[str] = Field(description="Transcript segment ids this point is drawn from, e.g. ['S3','S4']")


class SummaryResult(BaseModel):
    summary: str = Field(max_length=900)
    key_points: list[KeyPoint] = Field(min_length=1, max_length=8)


class LinkedInPost(BaseModel):
    post_text: str = Field(max_length=3000)
    hashtags: list[str] = Field(min_length=1, max_length=6)


class VerificationFinding(BaseModel):
    issue_type: str = Field(description="one of: unsupported_claim, incorrect_number, mistranslation, missing_context, overstated_claim")
    description: str = Field(max_length=300)
    evidence_segment_ids: list[str] = Field(default_factory=list)
    severity: str = Field(description="one of: low, medium, high")


class VerificationResult(BaseModel):
    findings: list[VerificationFinding] = Field(default_factory=list)
    accurate: bool = Field(description="true only if findings is empty or all findings are low severity")


class ImageCopy(BaseModel):
    headline: str = Field(max_length=90)
    takeaways: list[str] = Field(min_length=1, max_length=3)
