"""Fallback transcription for videos with no YouTube transcript panel (e.g. many Shorts, or videos
with auto-captions disabled): download the public audio track with yt-dlp and transcribe it locally
with faster-whisper (CTranslate2, CPU-friendly, runs fully offline — no paid API, nothing sent
anywhere). Used only when `youtube_transcript.extract_transcript` has already reported the
transcript panel is unavailable; this never bypasses a login wall, age gate, or region block — a
video yt-dlp itself cannot fetch publicly fails here too, honestly.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.integrations.youtube_transcript import TranscriptSegment

log = logging.getLogger("ltp.local_transcription")

DEFAULT_MODEL_SIZE = "base"
SUPPORTED_MODEL_SIZES = ["tiny", "base", "small", "medium"]

_model_cache: dict[str, object] = {}


class LocalTranscriptionError(Exception):
    pass


@dataclass
class LocalTranscriptResult:
    segments: list[TranscriptSegment] = field(default_factory=list)
    raw_text: str = ""
    language_hint: str | None = None


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _get_model(model_size: str):
    if model_size not in _model_cache:
        from faster_whisper import WhisperModel  # imported lazily: heavy, only needed on this path

        log.info("loading local whisper model '%s' (first use downloads it and caches it under the user's home dir)", model_size)
        _model_cache[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _model_cache[model_size]


def _download_audio(video_url: str, dest_dir: Path) -> Path:
    import yt_dlp

    out_template = str(dest_dir / "audio.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav", "preferredquality": "192"}],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([video_url])
    produced = list(dest_dir.glob("audio.*"))
    if not produced:
        raise LocalTranscriptionError("yt-dlp did not produce an audio file for this video.")
    return produced[0]


def _transcribe_sync(video_url: str, model_size: str) -> LocalTranscriptResult:
    with tempfile.TemporaryDirectory(prefix="ltp-audio-") as tmp:
        dest = Path(tmp)
        try:
            audio_path = _download_audio(video_url, dest)
        except Exception as exc:  # yt_dlp raises its own broad DownloadError family
            raise LocalTranscriptionError(f"Could not download audio for this video: {exc}") from exc

        model = _get_model(model_size)
        segments_iter, info = model.transcribe(str(audio_path), beam_size=5)

        segments: list[TranscriptSegment] = []
        text_parts: list[str] = []
        for i, seg in enumerate(segments_iter):
            text = seg.text.strip()
            if not text:
                continue
            segments.append(TranscriptSegment(id=f"w{i}", start_label=_format_timestamp(seg.start), text=text))
            text_parts.append(text)

        if not segments:
            raise LocalTranscriptionError("Whisper produced no speech segments — the audio may be silent, music-only, or too short.")

        return LocalTranscriptResult(segments=segments, raw_text=" ".join(text_parts), language_hint=info.language)


async def transcribe_with_whisper(video_url: str, *, model_size: str = DEFAULT_MODEL_SIZE) -> LocalTranscriptResult:
    """Downloads audio and runs it through a local Whisper model. CPU-bound and can take a while
    for longer videos — run off the event loop so it doesn't block other async work."""
    return await asyncio.to_thread(_transcribe_sync, video_url, model_size)
