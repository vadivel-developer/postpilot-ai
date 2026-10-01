"""Test environment must be set BEFORE any `app.*` module is imported anywhere in the test session,
because app.config.settings is a module-level singleton read once at import time. conftest.py is
always imported by pytest before test modules, so setting env vars here at module scope is what
makes that ordering guarantee hold.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="ltp-test-"))
os.environ["LTP_DATABASE_URL"] = f"sqlite:///{(_TMP_DIR / 'test.db').as_posix()}"
os.environ["LTP_ENCRYPTION_KEY"] = "bgL3o_9MMK9nlOg_IUaZGDo3X4AEMxqfMmFGfQQGup4="  # fixed, obviously-fake test-only Fernet key
os.environ["LTP_SESSION_SECRET"] = "unit-test-session-secret"
os.environ["LTP_HOST"] = "127.0.0.1"

import datetime as dt

import pytest


@pytest.fixture
def db_session():
    from app.models.db import Base, SessionLocal, engine, init_db

    init_db()
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture
def app_client():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.models.db import Base, engine

    Base.metadata.drop_all(engine)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def authed_client(app_client):
    app_client.post("/api/auth/bootstrap", json={"username": "owner", "password": "testpass123"})
    return app_client


def make_channel(db_session, name="Test Channel", youtube_channel_id="UCtest0000000000000"):
    from app.models.db import Channel

    c = Channel(youtube_channel_id=youtube_channel_id, name=name, handle=None, url=f"https://www.youtube.com/channel/{youtube_channel_id}")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def make_video(db_session, channel, youtube_video_id="abc12345678", title="Test video"):
    from app.models.db import Video

    v = Video(channel_id=channel.id, youtube_video_id=youtube_video_id, title=title, source_url=f"https://www.youtube.com/watch?v={youtube_video_id}", published_at=dt.datetime.now(dt.UTC))
    db_session.add(v)
    db_session.commit()
    db_session.refresh(v)
    return v


def make_draft(db_session, video, card_date=None, status="draft", **kwargs):
    from app.models.db import Draft

    d = Draft(card_date=card_date or dt.date.today(), video_id=video.id, status=status, **kwargs)
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d
