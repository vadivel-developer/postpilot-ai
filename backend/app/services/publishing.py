"""Publish gating and execution. A draft can only ever have one PublishRecord (unique on draft_id)
— repeat clicks on "Publish to LinkedIn" cannot create a second publish job once one exists in a
non-failed state, and an "uncertain" outcome is never retried automatically; a fresh attempt after
"uncertain" or "failed" requires the person to click Publish again explicitly, which stays
consistent with the spec's "never retry blindly and risk a duplicate."
"""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy.orm import Session

from app.integrations import linkedin
from app.models.db import Draft, PublishRecord, utcnow
from app.services import credentials as cred_service

log = logging.getLogger("ltp.publishing")


def _idempotency_key(draft_id: int, post_text: str) -> str:
    # Includes the draft's current text so an edit-then-republish after a genuine failure is a new
    # attempt, while identical repeat clicks collide on the same key.
    return hashlib.sha256(f"{draft_id}:{post_text}".encode()).hexdigest()[:40]


def can_publish(db: Session, draft: Draft) -> tuple[bool, str | None]:
    if draft.status not in ("draft", "needs_review"):
        return False, f"draft is '{draft.status}', not ready to publish"
    if not draft.post_text or not draft.post_text.strip():
        return False, "no post text to publish"
    existing = db.query(PublishRecord).filter_by(draft_id=draft.id).one_or_none()
    if existing and existing.status != "failed":
        # "publishing" blocks a second click while the job is still in flight (the case a plain
        # published/uncertain check alone misses); published/uncertain block permanently. Only a
        # genuinely failed attempt may be retried, and only by the person clicking Publish again.
        return False, f"this draft already has a publish record with status '{existing.status}'; re-publishing is blocked to avoid a duplicate post"
    return True, None


async def execute_publish(db: Session, draft: Draft) -> PublishRecord:
    """Called by the worker for a claimed 'publish_draft' job. Never called twice concurrently for
    the same draft because the job queue only ever holds one leased job per draft at a time."""
    from app.models.db import LinkedInCredential

    access_token = cred_service.get_linkedin_access_token(db)
    if not access_token:
        raise RuntimeError("LinkedIn is not connected.")
    li = db.get(LinkedInCredential, 1)
    if not li or not li.connected_account_urn:
        raise RuntimeError("LinkedIn account information is missing; reconnect in Settings.")

    idem_key = _idempotency_key(draft.id, draft.post_text or "")
    record = db.query(PublishRecord).filter_by(draft_id=draft.id).one_or_none()
    if record is None:
        record = PublishRecord(draft_id=draft.id, status="publishing", idempotency_key=idem_key)
        db.add(record)
        db.commit()
        db.refresh(record)
    elif record.idempotency_key != idem_key:
        record.idempotency_key = idem_key
        record.status = "publishing"
        record.error = None
        db.commit()

    try:
        image_asset_urn = None
        if draft.image_path:
            from pathlib import Path

            image_bytes = Path(draft.image_path).read_bytes()
            image_asset_urn = await linkedin.upload_image(access_token, li.connected_account_urn, image_bytes)

        assert draft.post_text  # can_publish() already rejected an empty post_text before enqueueing
        result = await linkedin.create_post(access_token=access_token, person_urn=li.connected_account_urn, text=draft.post_text, image_asset_urn=image_asset_urn)
        record.status = "published"
        record.linkedin_post_urn = result.get("post_urn")
        record.post_url = linkedin.post_url_from_urn(result.get("post_urn"))
        record.connected_account_name = li.connected_account_name
        record.published_at = utcnow()
        record.error = None
        db.commit()
        return record
    except linkedin.LinkedInError as exc:
        if exc.status_code in (408, 502, 503, 504):
            record.status = "uncertain"
            record.error = str(exc)
            db.commit()
            log.error("publish outcome uncertain for draft %s: %s", draft.id, exc)
            return record
        record.status = "failed"
        record.error = str(exc)
        db.commit()
        raise
