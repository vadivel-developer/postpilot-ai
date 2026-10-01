from __future__ import annotations

import datetime as dt

from tests.conftest import make_channel, make_draft, make_video


def test_generate_refuses_a_second_card_for_the_same_date(authed_client, db_session, monkeypatch):

    channel = make_channel(db_session)
    today = dt.date.today()
    make_draft(db_session, make_video(db_session, channel), card_date=today)

    r = authed_client.post("/api/drafts/generate", json={"channel_id": channel.id, "card_date": today.isoformat()})
    assert r.status_code == 409


async def _fake_latest_uploads(channel_id, limit=10):
    from app.integrations.youtube_discovery import UploadEntry

    return [UploadEntry(video_id="newvid00001", title="Brand new video", published_at=dt.datetime.now(dt.UTC).isoformat(), thumbnail_url=None, source_url="https://www.youtube.com/watch?v=newvid00001")]


def test_generate_opens_an_existing_draft_instead_of_duplicating_a_processed_video(authed_client, db_session, monkeypatch):
    from app.integrations import youtube_discovery as yd

    channel = make_channel(db_session)
    video = make_video(db_session, channel, youtube_video_id="newvid00001", title="Brand new video")
    existing = make_draft(db_session, video, card_date=dt.date.today() - dt.timedelta(days=1))

    monkeypatch.setattr(yd, "latest_uploads", _fake_latest_uploads)
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    r = authed_client.post("/api/drafts/generate", json={"channel_id": channel.id, "card_date": tomorrow.isoformat()})
    assert r.status_code == 200
    body = r.json()
    assert "existing_draft" in body
    assert body["existing_draft"]["id"] == existing.id
    # no new draft/card was created for tomorrow
    assert authed_client.get(f"/api/drafts?date_from={tomorrow}&date_to={tomorrow}").json() == []


def test_generate_creates_a_new_draft_for_a_genuinely_new_video(authed_client, db_session, monkeypatch):
    from app.integrations import youtube_discovery as yd

    channel = make_channel(db_session)
    monkeypatch.setattr(yd, "latest_uploads", _fake_latest_uploads)

    today = dt.date.today()
    r = authed_client.post("/api/drafts/generate", json={"channel_id": channel.id, "card_date": today.isoformat()})
    assert r.status_code == 200
    body = r.json()
    assert "draft" in body
    assert body["draft"]["status"] == "queued"
    assert body["draft"]["video"]["title"] == "Brand new video"


def test_no_new_video_when_channel_has_no_uploads(authed_client, db_session, monkeypatch):
    from app.integrations import youtube_discovery as yd

    channel = make_channel(db_session)

    async def empty(*a, **k):
        return []

    monkeypatch.setattr(yd, "latest_uploads", empty)
    r = authed_client.post("/api/drafts/generate", json={"channel_id": channel.id, "card_date": dt.date.today().isoformat()})
    assert r.status_code == 200 and r.json() == {"no_new_video": True}


def test_manual_edit_persists_and_creates_a_restorable_revision(authed_client, db_session):
    channel = make_channel(db_session)
    video = make_video(db_session, channel)
    draft = make_draft(db_session, video, status="draft", post_text="Original text", hashtags=["#one"])

    r = authed_client.patch(f"/api/drafts/{draft.id}", json={"post_text": "Edited text"})
    assert r.status_code == 200
    assert r.json()["post_text"] == "Edited text"
    assert r.json()["revision_count"] == 1

    r2 = authed_client.get(f"/api/drafts/{draft.id}")
    assert r2.json()["post_text"] == "Edited text"  # survives a fresh read (simulates reload/restart)

    r3 = authed_client.post(f"/api/drafts/{draft.id}/restore/0")
    assert r3.status_code == 200
    assert r3.json()["post_text"] == "Original text"


def test_editing_image_copy_marks_image_outdated(authed_client, db_session):
    channel = make_channel(db_session)
    video = make_video(db_session, channel)
    draft = make_draft(db_session, video, status="draft", image_headline="Old headline", image_outdated=False)

    r = authed_client.patch(f"/api/drafts/{draft.id}", json={"image_headline": "New headline"})
    assert r.json()["image_outdated"] is True


def test_cannot_edit_a_draft_that_is_still_processing(authed_client, db_session):
    channel = make_channel(db_session)
    video = make_video(db_session, channel)
    draft = make_draft(db_session, video, status="translating")
    r = authed_client.patch(f"/api/drafts/{draft.id}", json={"post_text": "x"})
    assert r.status_code == 409


def test_publish_requires_explicit_click_and_only_happens_once(authed_client, db_session):
    channel = make_channel(db_session)
    video = make_video(db_session, channel)
    draft = make_draft(db_session, video, status="draft", post_text="Ready to publish")

    r = authed_client.post(f"/api/drafts/{draft.id}/publish")
    assert r.status_code == 200
    assert r.json()["status"] == "publishing"

    # A second click while the first publish is in flight (or already recorded) is refused, not a
    # second silent job — this is exactly the "repeat clicks -> no duplicate" requirement.
    r2 = authed_client.post(f"/api/drafts/{draft.id}/publish")
    assert r2.status_code == 409


def test_a_future_dated_card_does_not_auto_publish_anything(authed_client, db_session):
    # Generating/creating a card for a future date must never itself trigger a publish job — only
    # an explicit POST /publish does, and that endpoint requires status draft/needs_review.
    channel = make_channel(db_session)
    video = make_video(db_session, channel)
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    draft = make_draft(db_session, video, card_date=tomorrow, status="queued")

    from app.models.db import Job

    jobs = db_session.query(Job).filter_by(job_type="publish_draft").all()
    assert jobs == []
    r = authed_client.post(f"/api/drafts/{draft.id}/publish")
    assert r.status_code == 409  # status is "queued", not draft/needs_review


def test_retry_only_allowed_for_failed_or_transcript_unavailable(authed_client, db_session):
    channel = make_channel(db_session)
    video = make_video(db_session, channel)
    draft_ok = make_draft(db_session, video, status="failed", card_date=dt.date.today())
    r = authed_client.post(f"/api/drafts/{draft_ok.id}/retry")
    assert r.status_code == 200 and r.json()["status"] == "queued"

    video2 = make_video(db_session, channel, youtube_video_id="other000001")
    draft_bad = make_draft(db_session, video2, status="draft", card_date=dt.date.today() + dt.timedelta(days=2))
    r2 = authed_client.post(f"/api/drafts/{draft_bad.id}/retry")
    assert r2.status_code == 409
