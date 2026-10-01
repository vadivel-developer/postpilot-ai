"""Draft/card endpoints. Generation and publishing are both async: the API enqueues a job and
returns immediately; the worker (must be running separately) does the actual work. The frontend
polls GET /api/drafts/{id} for progress.
"""

from __future__ import annotations

import datetime as dt
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    DraftEditRequest,
    GenerateDraftRequest,
    TranscriptPasteRequest,
)
from app.integrations import youtube_discovery as yd
from app.models.db import (
    Channel,
    Draft,
    PublishRecord,
    Transcript,
    Video,
    get_db_session,
    utcnow,
)
from app.security.auth import get_current_owner
from app.services import publishing
from app.worker.queue import enqueue

log = logging.getLogger("ltp.api.drafts")
router = APIRouter(prefix="/api/drafts", tags=["drafts"], dependencies=[Depends(get_current_owner)])

MAX_EDIT_HISTORY = 10


def _draft_dict(d: Draft) -> dict:
    video = d.video
    publish = d.publish_record
    return {
        "id": d.id,
        "card_date": d.card_date.isoformat(),
        "status": d.status,
        "last_error": d.last_error,
        "video": None
        if video is None
        else {"id": video.id, "title": video.title, "thumbnail_url": video.thumbnail_url, "published_at": video.published_at.isoformat() if video.published_at else None, "source_url": video.source_url, "channel_name": video.channel.name if video.channel else None},
        "source_language": d.source_language,
        "translated_text": d.translated_text,
        "summary_text": d.summary_text,
        "key_points": d.key_points,
        "post_text": d.post_text,
        "hashtags": d.hashtags,
        "verification": d.verification,
        "image_headline": d.image_headline,
        "image_takeaways": d.image_takeaways,
        "image_url": f"/api/drafts/{d.id}/image" if d.image_path else None,
        "image_outdated": d.image_outdated,
        "revision_count": len(d.revisions or []),
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
        "publish": None
        if publish is None
        else {"status": publish.status, "post_url": publish.post_url, "published_at": publish.published_at.isoformat() if publish.published_at else None, "error": publish.error},
    }


@router.get("")
def list_by_date(date_from: dt.date, date_to: dt.date, db: Session = Depends(get_db_session)) -> list[dict]:
    rows = db.query(Draft).filter(Draft.card_date >= date_from, Draft.card_date <= date_to).order_by(Draft.card_date).all()
    return [_draft_dict(d) for d in rows]


@router.get("/{draft_id}")
def get_draft(draft_id: int, db: Session = Depends(get_db_session)) -> dict:
    d = db.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "draft not found")
    return _draft_dict(d)


@router.get("/{draft_id}/image")
def get_image(draft_id: int, db: Session = Depends(get_db_session)):
    from fastapi.responses import FileResponse

    d = db.get(Draft, draft_id)
    if d is None or not d.image_path:
        raise HTTPException(404, "no image for this draft")
    return FileResponse(d.image_path, media_type="image/png")


@router.post("/generate")
async def generate(body: GenerateDraftRequest, db: Session = Depends(get_db_session)) -> dict:
    channel = db.get(Channel, body.channel_id)
    if channel is None:
        raise HTTPException(404, "channel not found")
    if db.query(Draft).filter_by(card_date=body.card_date).one_or_none() is not None:
        raise HTTPException(409, f"a card for {body.card_date} already exists")

    try:
        uploads = await yd.latest_uploads(channel.youtube_channel_id, limit=10)
    except yd.DiscoveryError as exc:
        raise HTTPException(502, f"Could not read this channel's uploads: {exc}") from exc
    if not uploads:
        return {"no_new_video": True}

    for upload in uploads:
        video = db.query(Video).filter_by(youtube_video_id=upload.video_id).one_or_none()
        existing_draft = db.query(Draft).filter_by(video_id=video.id).one_or_none() if video else None
        if existing_draft is not None:
            continue  # already processed elsewhere — check the next upload
        if video is None:
            published_at = None
            try:
                published_at = dt.datetime.fromisoformat(upload.published_at)
            except ValueError:
                pass
            video = Video(channel_id=channel.id, youtube_video_id=upload.video_id, title=upload.title, thumbnail_url=upload.thumbnail_url, published_at=published_at, source_url=upload.source_url)
            db.add(video)
            db.commit()
            db.refresh(video)

        draft = Draft(card_date=body.card_date, video_id=video.id, status="queued")
        db.add(draft)
        db.commit()
        db.refresh(draft)
        enqueue(db, "process_draft", draft_id=draft.id)
        return {"draft": _draft_dict(draft)}

    # every recent upload already has a draft somewhere
    most_recent = uploads[0]
    video = db.query(Video).filter_by(youtube_video_id=most_recent.video_id).one_or_none()
    existing_draft = db.query(Draft).filter_by(video_id=video.id).one_or_none() if video else None
    if existing_draft is not None:
        return {"existing_draft": _draft_dict(existing_draft), "message": "This channel's latest video was already turned into a draft."}
    return {"no_new_video": True}


@router.patch("/{draft_id}")
def edit_draft(draft_id: int, body: DraftEditRequest, db: Session = Depends(get_db_session)) -> dict:
    d = db.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "draft not found")
    if d.status not in ("draft", "needs_review"):
        raise HTTPException(409, f"draft is '{d.status}' and cannot be edited right now")

    revisions = list(d.revisions or [])
    snapshot = {"at": utcnow().isoformat(), "post_text": d.post_text, "hashtags": d.hashtags, "image_headline": d.image_headline, "image_takeaways": d.image_takeaways}
    changed = False
    image_copy_changed = False

    if body.post_text is not None and body.post_text != d.post_text:
        d.post_text = body.post_text
        changed = True
    if body.hashtags is not None and body.hashtags != d.hashtags:
        d.hashtags = body.hashtags
        changed = True
    if body.image_headline is not None and body.image_headline != d.image_headline:
        d.image_headline = body.image_headline
        changed = True
        image_copy_changed = True
    if body.image_takeaways is not None and body.image_takeaways != d.image_takeaways:
        d.image_takeaways = body.image_takeaways
        changed = True
        image_copy_changed = True

    if changed:
        revisions.append(snapshot)
        d.revisions = revisions[-MAX_EDIT_HISTORY:]
    if image_copy_changed:
        d.image_outdated = True
    db.commit()
    return _draft_dict(d)


@router.post("/{draft_id}/restore/{revision_index}")
def restore_revision(draft_id: int, revision_index: int, db: Session = Depends(get_db_session)) -> dict:
    d = db.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "draft not found")
    revisions = d.revisions or []
    if revision_index < 0 or revision_index >= len(revisions):
        raise HTTPException(404, "no such revision")
    snap = revisions[revision_index]
    d.post_text = snap.get("post_text")
    d.hashtags = snap.get("hashtags")
    d.image_headline = snap.get("image_headline")
    d.image_takeaways = snap.get("image_takeaways")
    d.image_outdated = True
    db.commit()
    return _draft_dict(d)


@router.post("/{draft_id}/retry")
def retry(draft_id: int, db: Session = Depends(get_db_session)) -> dict:
    d = db.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "draft not found")
    if d.status not in ("failed", "transcript_unavailable"):
        raise HTTPException(409, f"draft is '{d.status}'; retry is only for failed/transcript_unavailable")
    d.status = "queued"
    d.last_error = None
    db.commit()
    enqueue(db, "process_draft", draft_id=d.id)
    return _draft_dict(d)


@router.post("/{draft_id}/regenerate-text")
def regenerate_text(draft_id: int, db: Session = Depends(get_db_session)) -> dict:
    d = db.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "draft not found")
    if d.status not in ("draft", "needs_review", "failed"):
        raise HTTPException(409, f"draft is '{d.status}'; cannot regenerate right now")
    revisions = list(d.revisions or [])
    revisions.append({"at": utcnow().isoformat(), "post_text": d.post_text, "hashtags": d.hashtags, "image_headline": d.image_headline, "image_takeaways": d.image_takeaways})
    d.revisions = revisions[-MAX_EDIT_HISTORY:]
    d.status = "queued"
    db.commit()
    enqueue(db, "process_draft", draft_id=d.id, payload={"skip_extraction": True})
    return _draft_dict(d)


@router.post("/{draft_id}/regenerate-image")
def regenerate_image(draft_id: int, db: Session = Depends(get_db_session)) -> dict:
    from app.services import app_settings
    from app.services.image_gen import (
        BrandSpec,
        ImageGenerationError,
        generate_linkedin_image,
    )

    d = db.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "draft not found")
    prefs = app_settings.get_all(db)
    brand = BrandSpec(
        brand_name=prefs.get("brand_name", "My Company"),
        footer=prefs.get("image_footer", ""),
        color_primary=prefs.get("brand_color_primary", "#1F4B99"),
        color_secondary=prefs.get("brand_color_secondary", "#0A66C2"),
        color_text=prefs.get("brand_color_text", "#FFFFFF"),
        template=prefs.get("image_template", "classic"),
    )
    try:
        path = generate_linkedin_image(headline=d.image_headline or "", takeaways=d.image_takeaways or [], brand=brand)
    except ImageGenerationError as exc:
        raise HTTPException(422, str(exc)) from exc
    d.image_path = str(path)
    d.image_outdated = False
    db.commit()
    return _draft_dict(d)


@router.post("/{draft_id}/transcript")
def paste_transcript(draft_id: int, body: TranscriptPasteRequest, db: Session = Depends(get_db_session)) -> dict:
    d = db.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "draft not found")
    if d.status != "transcript_unavailable":
        raise HTTPException(409, "manual transcript is only accepted when extraction failed")
    segments = [{"id": "S1", "start_label": "", "text": body.text.strip()}]
    transcript = db.query(Transcript).filter_by(video_id=d.video_id).one_or_none()
    if transcript is None:
        transcript = Transcript(video_id=d.video_id)
        db.add(transcript)
    transcript.segments = segments
    transcript.raw_text = body.text.strip()
    transcript.extraction_method = "manual_paste"
    transcript.error = None
    d.status = "queued"
    d.last_error = None
    db.commit()
    enqueue(db, "process_draft", draft_id=d.id, payload={"skip_extraction": True})
    return _draft_dict(d)


@router.post("/{draft_id}/publish")
def publish(draft_id: int, db: Session = Depends(get_db_session)) -> dict:
    d = db.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "draft not found")
    ok, reason = publishing.can_publish(db, d)
    if not ok:
        raise HTTPException(409, reason)
    record = db.query(PublishRecord).filter_by(draft_id=d.id).one_or_none()
    if record is None:
        record = PublishRecord(draft_id=d.id, status="publishing", idempotency_key=f"pending-{d.id}")
        db.add(record)
    else:
        record.status = "publishing"
    db.commit()
    enqueue(db, "publish_draft", draft_id=d.id, max_attempts=1)  # never auto-retried — see publishing.py
    return {"status": "publishing"}
