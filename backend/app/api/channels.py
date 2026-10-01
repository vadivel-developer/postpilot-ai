from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import ChannelConfirmRequest, ChannelResolveRequest
from app.integrations import youtube_discovery as yd
from app.models.db import Channel, get_db_session
from app.security.auth import get_current_owner

router = APIRouter(prefix="/api/channels", tags=["channels"], dependencies=[Depends(get_current_owner)])


def _channel_dict(c: Channel) -> dict:
    return {"id": c.id, "youtube_channel_id": c.youtube_channel_id, "name": c.name, "handle": c.handle, "url": c.url, "is_default": c.is_default}


@router.get("")
def list_channels(db: Session = Depends(get_db_session)) -> list[dict]:
    return [_channel_dict(c) for c in db.query(Channel).order_by(Channel.added_at.desc()).all()]


@router.post("/resolve")
async def resolve(body: ChannelResolveRequest, db: Session = Depends(get_db_session)) -> dict:
    text = body.input.strip()
    if not text:
        raise HTTPException(422, "Enter a channel name, channel URL, or video URL.")

    video_id = yd.extract_video_id(text) if yd.looks_like_url(text) else None
    try:
        if video_id:
            resolved = await yd.resolve_video_url(text)
        elif yd.looks_like_url(text) or text.startswith("@") or text.startswith("UC"):
            resolved = await yd.resolve_channel_url(text)
        else:
            candidates = await yd.search_channels_by_name(text)
            if not candidates:
                raise HTTPException(404, f"No YouTube channel found matching '{text}'.")
            if len(candidates) == 1:
                resolved = await yd.resolve_channel_url(candidates[0].url)
            else:
                return {"candidates": [{"name": c.name, "handle": c.handle, "url": c.url} for c in candidates]}
    except yd.DiscoveryError as exc:
        raise HTTPException(404, str(exc)) from exc

    existing = db.query(Channel).filter_by(youtube_channel_id=resolved.channel_id).one_or_none()
    return {"resolved": {"channel_id": resolved.channel_id, "name": resolved.name, "handle": resolved.handle, "url": resolved.url, "already_saved": existing is not None}}


@router.post("/confirm")
async def confirm(body: ChannelConfirmRequest, db: Session = Depends(get_db_session)) -> dict:
    try:
        resolved = await yd.resolve_channel_url(body.url)
    except yd.DiscoveryError as exc:
        raise HTTPException(404, str(exc)) from exc

    channel = db.query(Channel).filter_by(youtube_channel_id=resolved.channel_id).one_or_none()
    if channel is None:
        channel = Channel(youtube_channel_id=resolved.channel_id, name=body.name or resolved.name, handle=resolved.handle, url=resolved.url)
        db.add(channel)
    else:
        channel.name = body.name or resolved.name
    db.commit()
    db.refresh(channel)
    return _channel_dict(channel)


@router.post("/{channel_id}/default")
def set_default(channel_id: int, db: Session = Depends(get_db_session)) -> dict:
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(404, "channel not found")
    for c in db.query(Channel).filter_by(is_default=True).all():
        c.is_default = False
    channel.is_default = True
    db.commit()
    return _channel_dict(channel)
