"""SQLAlchemy models + engine/session setup. SQLite file lives under backend/instance/ (git-ignored)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Generator
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.pool import NullPool

from app.config import settings


class Base(DeclarativeBase):
    pass


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# ---------------------------------------------------------------- auth


class Owner(Base):
    __tablename__ = "owners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- YouTube domain


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    youtube_channel_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    handle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    url: Mapped[str] = mapped_column(String(500))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    videos: Mapped[list[Video]] = relationship(back_populates="channel")


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("youtube_video_id", name="uq_video_youtube_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    youtube_video_id: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(500))
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_url: Mapped[str] = mapped_column(String(500))
    discovered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    channel: Mapped[Channel] = relationship(back_populates="videos")
    transcript: Mapped[Transcript | None] = relationship(back_populates="video", uselist=False)
    drafts: Mapped[list[Draft]] = relationship(back_populates="video")


class Transcript(Base):
    __tablename__ = "transcripts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), unique=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    segments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)  # [{id, start, text}, ...]
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(40))  # "playwright_captions" | "manual_paste" | "upload"
    extracted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    video: Mapped[Video] = relationship(back_populates="transcript")


# ---------------------------------------------------------------- drafts / cards


class Draft(Base):
    __tablename__ = "drafts"
    __table_args__ = (UniqueConstraint("card_date", name="uq_draft_card_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_date: Mapped[dt.date] = mapped_column(Date)  # the dated card this draft belongs to
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")

    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_points: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)  # linked to segment ids

    post_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    verification: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)  # findings

    image_headline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    image_takeaways: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_outdated: Mapped[bool] = mapped_column(Boolean, default=False)

    revisions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)  # prior text/image revisions
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    video: Mapped[Video | None] = relationship(back_populates="drafts")
    publish_record: Mapped[PublishRecord | None] = relationship(back_populates="draft", uselist=False)


class PublishRecord(Base):
    __tablename__ = "publish_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20))  # published | uncertain | failed
    linkedin_post_urn: Mapped[str | None] = mapped_column(String(200), nullable=True)
    post_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    connected_account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)

    draft: Mapped[Draft] = relationship(back_populates="publish_record")


# ---------------------------------------------------------------- job queue


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(40))  # "process_draft" | "publish_draft"
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("drafts.id"), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|leased|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_after: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------- credentials (secrets stored encrypted)


class GeminiCredential(Base):
    __tablename__ = "gemini_credential"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # singleton row, id=1
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_four: Mapped[str | None] = mapped_column(String(8), nullable=True)  # for masked display only
    model: Mapped[str] = mapped_column(String(80), default="gemini-2.5-flash")
    source: Mapped[str] = mapped_column(String(10), default="ui")  # "ui" | "env"
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_test_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class NvidiaCredential(Base):
    __tablename__ = "nvidia_credential"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # singleton row, id=1
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_four: Mapped[str | None] = mapped_column(String(8), nullable=True)  # for masked display only
    model: Mapped[str] = mapped_column(String(120), default="nvidia/llama-3.1-nemotron-70b-instruct")
    source: Mapped[str] = mapped_column(String(10), default="ui")  # "ui" | "env"
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_test_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LinkedInCredential(Base):
    __tablename__ = "linkedin_credential"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # singleton row, id=1
    client_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    encrypted_client_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="ui")
    encrypted_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    connected_account_urn: Mapped[str | None] = mapped_column(String(200), nullable=True)
    oauth_state: Mapped[str | None] = mapped_column(String(100), nullable=True)  # in-flight CSRF state, cleared after use
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AppSetting(Base):
    """Generic brand/preference key-value store (non-secret)."""

    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


# ---------------------------------------------------------------- engine / session


_is_sqlite = settings.database_url.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
# SQLite serializes writes at the file level regardless of how many DBAPI connections exist, so a
# fixed-size QueuePool adds nothing but a limit to hit: a worker holding one connection open through
# a slow job (e.g. local Whisper transcription) plus the dashboard's frequent polling can pile up
# enough concurrent checkouts to exceed pool_size+max_overflow and start timing out (seen live as
# `QueuePool limit of size 5 overflow 10 reached`). NullPool opens a plain connection per checkout
# and closes it right after, which is what SQLite wants.
engine = create_engine(settings.database_url, connect_args=_connect_args, poolclass=NullPool if _is_sqlite else None)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.get(GeminiCredential, 1) is None:
            db.add(GeminiCredential(id=1))
        if db.get(NvidiaCredential, 1) is None:
            db.add(NvidiaCredential(id=1))
        if db.get(LinkedInCredential, 1) is None:
            db.add(LinkedInCredential(id=1))
        db.commit()


def get_db_session() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
