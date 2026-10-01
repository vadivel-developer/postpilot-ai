"""Runs the LangGraph pipeline for one draft and writes every stage's result back to the database,
so progress is visible and durable even if the worker restarts mid-job. This is the deterministic
glue: DB writes, image rendering, and status transitions are plain code, not model output.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.agents.pipeline import PipelineState, build_pipeline_graph
from app.integrations.local_transcription import DEFAULT_MODEL_SIZE as WHISPER_DEFAULT_MODEL
from app.integrations.local_transcription import LocalTranscriptionError, transcribe_with_whisper
from app.models.db import Draft, Transcript, Video
from app.services import app_settings
from app.services import credentials as cred_service
from app.services.gemini_client import DEFAULT_MODEL, GeminiClient, GeminiError
from app.services.image_gen import (
    BrandSpec,
    ImageGenerationError,
    generate_linkedin_image,
)
from app.services.nvidia_client import DEFAULT_MODEL as NVIDIA_DEFAULT_MODEL
from app.services.nvidia_client import NvidiaClient, NvidiaError
from app.services.ollama_client import DEFAULT_BASE_URL as OLLAMA_DEFAULT_BASE_URL
from app.services.ollama_client import DEFAULT_MODEL as OLLAMA_DEFAULT_MODEL
from app.services.ollama_client import OllamaClient, OllamaError

log = logging.getLogger("ltp.draft_processing")

_PIPELINE_ERRORS = (GeminiError, OllamaError, NvidiaError)

STATUS_LABELS = {
    "translating": "Translating",
    "generating_content": "Generating content",
    "verifying": "Verifying",
    "creating_image": "Creating image",
    "draft": "Draft",
    "needs_review": "Needs review",
    "transcript_unavailable": "Transcript unavailable",
    "failed": "Failed",
}


class _PipelineFailed(Exception):
    """Raised by _run_graph after it has already written the failure to the draft."""


async def _run_graph(graph, initial: PipelineState, draft: Draft, db: Session) -> PipelineState:
    """Streams the graph (not invoke) so draft.status is committed after every node — progress is
    visible, and durable if the worker restarts mid-run. On failure, writes draft.status='failed'
    with a clear message and raises _PipelineFailed so the caller can stop without re-handling it."""
    final_state: PipelineState = dict(initial)  # type: ignore[assignment]
    try:
        async for state_update in graph.astream(initial, stream_mode="values"):
            final_state = state_update
            new_status = final_state.get("status")
            if new_status and new_status != draft.status:
                draft.status = new_status
                db.commit()
    except _PIPELINE_ERRORS as exc:
        draft.status = "failed"
        draft.last_error = f"[{exc.kind}] {exc}"
        db.commit()
        raise _PipelineFailed from exc
    except Exception as exc:  # never leave a draft stuck mid-pipeline
        log.exception("pipeline crashed for draft %s", draft.id)
        draft.status = "failed"
        draft.last_error = f"Unexpected error: {type(exc).__name__}: {exc}"
        db.commit()
        raise _PipelineFailed from exc
    return final_state


async def process_draft(db: Session, draft_id: int, *, skip_extraction: bool = False) -> None:
    draft = db.get(Draft, draft_id)
    if draft is None:
        raise RuntimeError(f"draft {draft_id} not found")
    video = db.get(Video, draft.video_id) if draft.video_id else None
    if video is None:
        raise RuntimeError(f"draft {draft_id} has no associated video")

    draft.status = "extracting_transcript"
    db.commit()

    existing_segments: list[dict] | None = None
    existing_raw_text: str | None = None
    existing_method: str | None = None
    if skip_extraction:
        transcript = db.query(Transcript).filter_by(video_id=video.id).one_or_none()
        if transcript is None or not transcript.segments:
            draft.status = "failed"
            draft.last_error = "No existing transcript to reuse; run extraction first."
            db.commit()
            return
        existing_segments, existing_raw_text, existing_method = transcript.segments, transcript.raw_text, transcript.extraction_method

    prefs = app_settings.get_all(db)
    provider = prefs.get("llm_provider", "gemini")
    client: GeminiClient | OllamaClient | NvidiaClient
    if provider == "ollama":
        client = OllamaClient(base_url=prefs.get("ollama_base_url") or OLLAMA_DEFAULT_BASE_URL, model=prefs.get("ollama_model") or OLLAMA_DEFAULT_MODEL)
    elif provider == "nvidia":
        api_key = cred_service.get_nvidia_api_key(db)
        if not api_key:
            draft.status = "failed"
            draft.last_error = "NVIDIA NIM is not configured. Add an API key in Settings."
            db.commit()
            return
        model = cred_service.get_nvidia_model(db)
        client = NvidiaClient(api_key=api_key, model=model or NVIDIA_DEFAULT_MODEL)
    else:
        api_key = cred_service.get_gemini_api_key(db)
        if not api_key:
            draft.status = "failed"
            draft.last_error = "Gemini is not configured. Add an API key in Settings, or switch provider."
            db.commit()
            return
        model = cred_service.get_gemini_model(db)
        client = GeminiClient(api_key=api_key, model=model or DEFAULT_MODEL)
    graph = build_pipeline_graph(client)

    initial: PipelineState = {
        "video_url": video.source_url,
        "video_title": video.title,
        "tone": prefs.get("content_tone", "professional"),
        "creator_name": video.channel.name if video.channel else "",
        "output_language": prefs.get("output_language", "English"),
        "status": "extracting_transcript",
    }
    if existing_segments is not None:
        initial["segments"] = existing_segments
        initial["raw_text"] = existing_raw_text or ""
        initial["extraction_method"] = existing_method or "manual_paste"

    try:
        final_state = await _run_graph(graph, initial, draft, db)
    except _PipelineFailed:
        return

    if final_state.get("status") == "transcript_unavailable":
        if not prefs.get("whisper_fallback", True):
            draft.status = "transcript_unavailable"
            draft.last_error = final_state.get("error")
            db.commit()
            return

        original_error = final_state.get("error")
        draft.status = "extracting_transcript"
        draft.last_error = f"{original_error} Trying local speech-to-text (Whisper) instead — this can take a few minutes."
        db.commit()
        try:
            whisper_result = await transcribe_with_whisper(video.source_url, model_size=prefs.get("whisper_model") or WHISPER_DEFAULT_MODEL)
        except LocalTranscriptionError as exc:
            draft.status = "transcript_unavailable"
            draft.last_error = f"{original_error} Local transcription also failed: {exc}"
            db.commit()
            return

        initial["segments"] = [{"id": s.id, "start_label": s.start_label, "text": s.text} for s in whisper_result.segments]
        initial["raw_text"] = whisper_result.raw_text
        initial["extraction_method"] = "local_whisper"
        initial["language_code"] = whisper_result.language_hint
        try:
            final_state = await _run_graph(graph, initial, draft, db)
        except _PipelineFailed:
            return
        if final_state.get("status") == "transcript_unavailable":
            draft.status = "transcript_unavailable"
            draft.last_error = final_state.get("error")
            db.commit()
            return

    transcript = db.query(Transcript).filter_by(video_id=video.id).one_or_none()
    if transcript is None:
        transcript = Transcript(video_id=video.id)
        db.add(transcript)
    transcript.language = final_state.get("language_code")
    transcript.segments = final_state.get("segments")
    transcript.raw_text = final_state.get("raw_text")
    transcript.extraction_method = final_state.get("extraction_method", "playwright_captions")

    draft.source_language = final_state.get("language_name")
    draft.translated_text = final_state.get("translated_text")
    draft.summary_text = final_state.get("summary")
    draft.key_points = final_state.get("key_points")
    draft.post_text = final_state.get("post_text")
    draft.hashtags = final_state.get("hashtags")
    draft.verification = final_state.get("verification_findings")
    draft.image_headline = final_state.get("image_headline")
    draft.image_takeaways = final_state.get("image_takeaways")
    draft.image_outdated = False

    try:
        brand = BrandSpec(
            brand_name=prefs.get("brand_name", "My Company"),
            footer=prefs.get("image_footer", ""),
            color_primary=prefs.get("brand_color_primary", "#1F4B99"),
            color_secondary=prefs.get("brand_color_secondary", "#0A66C2"),
            color_text=prefs.get("brand_color_text", "#FFFFFF"),
            template=prefs.get("image_template", "classic"),
        )
        path = generate_linkedin_image(headline=draft.image_headline or video.title[:80], takeaways=draft.image_takeaways or [], brand=brand)
        draft.image_path = str(path)
    except ImageGenerationError as exc:
        draft.last_error = f"Image generation issue: {exc}"

    draft.status = final_state.get("status", "draft")
    db.commit()
