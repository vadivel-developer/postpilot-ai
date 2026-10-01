from __future__ import annotations

import pytest

from tests.conftest import make_channel, make_draft, make_video


@pytest.mark.asyncio
async def test_missing_transcript_stops_generation_before_any_gemini_call(db_session, monkeypatch):
    import app.agents.pipeline as pipeline_mod
    from app.integrations.youtube_transcript import TranscriptResult
    from app.services import draft_processing

    async def fake_extract(url, **kw):
        return TranscriptResult(ok=False, error="No 'Show transcript' control was found for this video.")

    monkeypatch.setattr(pipeline_mod, "extract_transcript", fake_extract)

    from app.services import credentials as cred
    cred.set_gemini_api_key(db_session, "fake-key-not-called")

    calls = {"n": 0}

    class ExplodingClient:
        async def generate_structured(self, *a, **k):
            calls["n"] += 1
            raise AssertionError("Gemini must not be called when transcript extraction failed")

    monkeypatch.setattr(draft_processing, "GeminiClient", lambda **kw: ExplodingClient())

    channel = make_channel(db_session)
    video = make_video(db_session, channel)
    draft = make_draft(db_session, video, status="queued")

    await draft_processing.process_draft(db_session, draft.id)

    db_session.refresh(draft)
    assert draft.status == "transcript_unavailable"
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_selected_gemini_model_is_used_for_the_run(db_session, monkeypatch):
    from app.services import credentials as cred
    from app.services import draft_processing

    cred.set_gemini_api_key(db_session, "fake-key")
    cred.set_gemini_model(db_session, "gemini-2.5-pro")

    seen_models = []

    class FakeClient:
        def __init__(self, api_key, model):
            seen_models.append(model)

    monkeypatch.setattr(draft_processing, "GeminiClient", FakeClient)

    async def fake_graph_astream(initial, stream_mode="values"):
        yield {"status": "transcript_unavailable", "error": "stop early for this test"}

    class FakeGraph:
        def astream(self, initial, stream_mode="values"):
            return fake_graph_astream(initial, stream_mode)

    monkeypatch.setattr(draft_processing, "build_pipeline_graph", lambda client: FakeGraph())

    channel = make_channel(db_session)
    video = make_video(db_session, channel)
    draft = make_draft(db_session, video, status="queued")
    await draft_processing.process_draft(db_session, draft.id)

    assert seen_models == ["gemini-2.5-pro"]


def test_manual_transcript_paste_only_accepted_after_extraction_failed(authed_client, db_session):
    channel = make_channel(db_session)
    video = make_video(db_session, channel)
    draft = make_draft(db_session, video, status="draft")  # not transcript_unavailable

    r = authed_client.post(f"/api/drafts/{draft.id}/transcript", json={"text": "A pasted transcript with enough characters to pass validation."})
    assert r.status_code == 409
