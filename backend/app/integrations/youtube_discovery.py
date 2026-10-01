"""YouTube channel/video discovery: resolves a channel name, handle, channel URL, or a direct video
URL to a canonical channel id, and lists the channel's latest uploads.

Two adapters, matched to what each is good for:
  - `resolve_channel_url`: a plain HTTPS fetch of the public channel page and its canonical link
    (`<link rel="canonical" href=".../channel/UC...">`). No login, no JS execution needed — this is
    the primary path for a channel URL, handle (@name) or a video URL.
  - `search_channels_by_name`: YouTube's public channel-search results page, read with Playwright,
    for the case a bare name matches more than one channel and the person must confirm which one.
  - `latest_uploads`: the channel's public RSS feed (`/feeds/videos.xml?channel_id=...`), which needs
    no API key and returns real upload data (title, video id, publish time, thumbnail).

Verified against a live channel and its real RSS feed during development (see docs/VERIFICATION.md).
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

import feedparser
import httpx

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})")
_CHANNEL_ID_RE = re.compile(r"channel/(UC[A-Za-z0-9_-]{20,})")
_CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]+)"')
_TITLE_RE = re.compile(r'"title":"((?:[^"\\]|\\.)*?)","description"')
_EXTERNAL_ID_RE = re.compile(r'"externalId":"(UC[A-Za-z0-9_-]{20,})"')


class DiscoveryError(Exception):
    pass


@dataclass
class ResolvedChannel:
    channel_id: str
    name: str
    handle: str | None
    url: str


@dataclass
class ChannelCandidate:
    """A search hit shown for the user to confirm — not yet resolved to a channel id."""

    name: str
    handle: str | None
    url: str


@dataclass
class UploadEntry:
    video_id: str
    title: str
    published_at: str  # ISO 8601, as reported by the feed
    thumbnail_url: str | None
    source_url: str


def extract_video_id(text: str) -> str | None:
    m = _VIDEO_ID_RE.search(text)
    return m.group(1) if m else None


def looks_like_url(text: str) -> bool:
    return text.strip().lower().startswith(("http://", "https://", "www.youtube.com", "youtube.com", "youtu.be"))


def _normalize_channel_input(text: str) -> str:
    text = text.strip()
    if looks_like_url(text):
        return text if text.startswith("http") else f"https://{text}"
    if text.startswith("@"):
        return f"https://www.youtube.com/{text}"
    if text.startswith("UC") and len(text) >= 20:
        return f"https://www.youtube.com/channel/{text}"
    return text  # a bare name — caller should use search_channels_by_name instead


async def resolve_video_url(video_url: str) -> ResolvedChannel:
    """Given a specific video URL, resolve the channel that uploaded it."""
    video_id = extract_video_id(video_url)
    if not video_id:
        raise DiscoveryError(f"'{video_url}' does not look like a YouTube video URL.")
    canonical = f"https://www.youtube.com/watch?v={video_id}"
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=15) as client:
        r = await client.get(canonical)
        r.raise_for_status()
        html = r.text
    m = _EXTERNAL_ID_RE.search(html) or _CHANNEL_ID_RE.search(html)
    if not m:
        raise DiscoveryError("Could not find the uploading channel for that video.")
    channel_id = m.group(1)
    return await resolve_channel_url(f"https://www.youtube.com/channel/{channel_id}")


async def resolve_channel_url(channel_input: str) -> ResolvedChannel:
    """Resolve a channel URL, @handle, or raw channel id to its canonical id and display name."""
    url = _normalize_channel_input(channel_input)
    if not looks_like_url(url):
        raise DiscoveryError("Not a channel URL/handle; use search_channels_by_name for a bare name.")

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=15) as client:
        r = await client.get(url)
        if r.status_code == 404:
            raise DiscoveryError(f"No YouTube channel found at '{channel_input}'.")
        r.raise_for_status()
        html = r.text

    id_match = _EXTERNAL_ID_RE.search(html)
    if not id_match:
        canon = _CANONICAL_RE.search(html)
        id_match = _CHANNEL_ID_RE.search(canon.group(1)) if canon else None
    if not id_match:
        raise DiscoveryError(f"Could not resolve a channel id from '{channel_input}'. The page may require sign-in or the channel does not exist.")
    channel_id = id_match.group(1)

    title_match = _TITLE_RE.search(html)
    name = _unescape_json_string(title_match.group(1)) if title_match else channel_input
    handle_match = re.search(r"/(@[^/?#]+)", url) or re.search(r"^(@[^/?#]+)", channel_input.strip())
    handle = handle_match.group(1) if handle_match else None

    return ResolvedChannel(channel_id=channel_id, name=name, handle=handle, url=f"https://www.youtube.com/channel/{channel_id}")


def _unescape_json_string(s: str) -> str:
    try:
        import json

        return json.loads(f'"{s}"')
    except Exception:
        return s


async def search_channels_by_name(name: str, limit: int = 5) -> list[ChannelCandidate]:
    """Browser-driven fallback: YouTube's public channel search results, for disambiguating a bare
    name that isn't a URL or handle. Used only when the input doesn't already resolve directly.
    Results carry a handle/URL but not yet a channel id — the caller resolves the one the person
    confirms via resolve_channel_url, rather than resolving every candidate up front."""
    from playwright.async_api import async_playwright

    candidates: list[ChannelCandidate] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(user_agent=USER_AGENT)
            search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(name)}&sp=EgIQAg%253D%253D"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=20_000)
            await page.wait_for_timeout(2000)
            data = await page.evaluate(_SEARCH_EXTRACT_JS)
            seen: set[str] = set()
            for item in data:
                href = item.get("href")
                if not href or href in seen:
                    continue
                seen.add(href)
                url = href if href.startswith("http") else f"https://www.youtube.com{href}"
                handle = href.lstrip("/") if href.startswith("/@") else None
                candidates.append(ChannelCandidate(name=item.get("name") or name, handle=handle, url=url))
                if len(candidates) >= limit:
                    break
        finally:
            await browser.close()
    return candidates


_SEARCH_EXTRACT_JS = r"""
() => {
  const renderers = document.querySelectorAll('ytd-channel-renderer');
  const out = [];
  for (const r of renderers) {
    const link = r.querySelector('a.channel-link');
    const nameEl = r.querySelector('#text.ytd-channel-name, yt-formatted-string#text, #channel-title #text');
    out.push({ href: link ? link.getAttribute('href') : null, name: nameEl ? nameEl.textContent.trim() : null });
  }
  return out;
}
"""


async def latest_uploads(channel_id: str, limit: int = 5) -> list[UploadEntry]:
    """Public RSS feed — no API key, real data, capped at the ~15 most recent uploads by design."""
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15) as client:
        r = await client.get(feed_url)
        r.raise_for_status()
        feed_text = r.text
    parsed = feedparser.parse(feed_text)
    if parsed.bozo and not parsed.entries:
        raise DiscoveryError("This channel's upload feed could not be read.")
    out: list[UploadEntry] = []
    for entry in parsed.entries[:limit]:
        video_id = getattr(entry, "yt_videoid", None) or extract_video_id(entry.link)
        if not video_id:
            continue
        thumb = None
        media_thumb = entry.get("media_thumbnail")
        if media_thumb:
            thumb = media_thumb[0].get("url")
        out.append(UploadEntry(video_id=video_id, title=entry.title, published_at=entry.published, thumbnail_url=thumb, source_url=entry.link))
    return out
