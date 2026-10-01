"""Splits a long transcript into segment-id-tagged chunks so translation and analysis never
silently truncate the source. Each chunk is a contiguous run of transcript segments, kept under a
character budget generous enough for a single Gemini call."""

from __future__ import annotations

from dataclasses import dataclass

from app.integrations.youtube_transcript import TranscriptSegment

MAX_CHUNK_CHARS = 6000


@dataclass
class TranscriptChunk:
    index: int
    segment_ids: list[str]
    text: str  # "[S12] text\n[S13] text..." — segment ids preserved for linking claims back


def chunk_transcript(segments: list[TranscriptSegment], max_chars: int = MAX_CHUNK_CHARS) -> list[TranscriptChunk]:
    chunks: list[TranscriptChunk] = []
    current_ids: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current_ids, current_lines, current_len
        if current_lines:
            chunks.append(TranscriptChunk(index=len(chunks), segment_ids=list(current_ids), text="\n".join(current_lines)))
        current_ids, current_lines, current_len = [], [], 0

    for seg in segments:
        line = f"[{seg.id}] {seg.text}"
        if current_len + len(line) + 1 > max_chars and current_lines:
            flush()
        current_ids.append(seg.id)
        current_lines.append(line)
        current_len += len(line) + 1
    flush()
    return chunks
