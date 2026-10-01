"""Transcript extraction via Playwright, driving YouTube's normal web UI exactly as a person would:
open the video, expand the description, click "Show transcript", and read the rendered segments.

This selector set (`#description-inline-expander`, `button[aria-label="Show transcript"]`,
`transcript-segment-view-model`) was reverse-engineered against a live YouTube page on 2026-09-25 and
is expected to drift as YouTube ships UI changes — that is exactly why extraction lives behind this
one adapter (see the module docstring in youtube_discovery.py for the matching discovery adapter).

Never invents transcript text: if no segments are found, this returns a clear error instead of
guessing from the title or description. The returned raw text is untrusted, model-facing input —
callers must not execute anything found inside it as an instruction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from playwright.async_api import Page, async_playwright
from playwright.async_api import TimeoutError as PwTimeout

log = logging.getLogger("ltp.transcript")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


@dataclass
class TranscriptSegment:
    id: str
    start_label: str  # "0:08" as shown, kept verbatim rather than reparsed into seconds
    text: str


@dataclass
class TranscriptResult:
    ok: bool
    segments: list[TranscriptSegment] = field(default_factory=list)
    raw_text: str = ""
    language_hint: str | None = None
    extraction_method: str = "playwright_captions"
    error: str | None = None


async def _open_transcript_panel(page: Page) -> bool:
    try:
        await page.wait_for_selector("#description-inline-expander", timeout=15_000)
        await page.locator("#description-inline-expander").click(timeout=5_000)
    except PwTimeout:
        pass  # some layouts show the button without needing this; keep going

    buttons = page.locator('button[aria-label="Show transcript"]')
    count = await buttons.count()
    for i in range(count):
        btn = buttons.nth(i)
        try:
            if await btn.is_visible():
                await btn.click(timeout=5_000)
                return True
        except PwTimeout:
            continue
    return False


async def extract_transcript(video_url: str, *, timeout_s: int = 45) -> TranscriptResult:
    """Best-effort extraction of the transcript YouTube shows to a normal, logged-out viewer.
    Never bypasses a login wall, CAPTCHA, or age/region gate — if one appears, this reports a clear
    error rather than trying to get around it."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page(viewport={"width": 1280, "height": 1200}, user_agent=USER_AGENT)
                page.set_default_timeout(timeout_s * 1000)
                await page.goto(video_url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
                await page.wait_for_timeout(3500)  # YouTube's player/description hydrate after DOMContentLoaded

                if await page.locator("text=/sign in to confirm|verify you.?re human|prove you.?re not a robot/i").count():
                    return TranscriptResult(ok=False, error="YouTube is asking to sign in or verify; extraction stops rather than trying to bypass it.")

                opened = await _open_transcript_panel(page)
                if not opened:
                    # Common, legitimate reason: this video has no transcript/captions at all.
                    return TranscriptResult(ok=False, error="No 'Show transcript' control was found for this video — it likely has no captions available.")

                await page.wait_for_timeout(2500)
                data = await page.evaluate(_EXTRACT_JS)
                segments_raw = data.get("segments", [])
                if not segments_raw:
                    return TranscriptResult(ok=False, error="The transcript panel opened but no segments were rendered — captions may be disabled for this video.")

                segments = [TranscriptSegment(id=f"S{i + 1}", start_label=s["t"] or "", text=s["text"]) for i, s in enumerate(segments_raw) if s["text"]]
                raw_text = "\n".join(f"[{s.start_label}] {s.text}" for s in segments)
                return TranscriptResult(ok=True, segments=segments, raw_text=raw_text, language_hint=data.get("lang"))
            finally:
                await browser.close()
    except PwTimeout:
        return TranscriptResult(ok=False, error=f"Timed out after {timeout_s}s waiting for YouTube's transcript panel.")
    except Exception as exc:  # network errors, browser crash, etc. — never silently fabricate a transcript
        log.exception("transcript extraction failed for %s", video_url)
        return TranscriptResult(ok=False, error=f"Extraction failed: {type(exc).__name__}: {exc}")


_EXTRACT_JS = r"""
() => {
  const els = document.querySelectorAll('transcript-segment-view-model');
  const segments = [];
  for (const el of els) {
    const ts = el.querySelector('.ytwTranscriptSegmentViewModelTimestamp');
    const textSpan = el.querySelector('.ytAttributedStringHost') || el.querySelector('span[role="text"]');
    const text = (textSpan ? textSpan.textContent : el.textContent || '').trim();
    segments.push({ t: ts ? ts.textContent.trim() : null, text });
  }
  const lang = document.documentElement.getAttribute('lang') || null;
  return { segments, lang };
}
"""
