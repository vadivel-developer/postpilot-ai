"""Persistent, database-backed job queue: safe atomic claiming (a single UPDATE...WHERE, race-free
even across multiple worker processes because SQLite serializes writers), leases with expiry so a
crashed worker's job is recovered rather than stuck forever, and bounded retries with backoff.
"""

from __future__ import annotations

import datetime as dt
import socket
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.db import Job

WORKER_ID = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


def enqueue(db: Session, job_type: str, *, draft_id: int | None = None, payload: dict[str, Any] | None = None, max_attempts: int | None = None) -> Job:
    job = Job(job_type=job_type, draft_id=draft_id, payload=payload, status="pending", max_attempts=max_attempts or settings.job_max_attempts)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def recover_expired_leases(db: Session) -> int:
    """Runs at worker startup and periodically: a job whose lease expired (worker died mid-job)
    goes back to pending so another (or the same, restarted) worker can pick it up."""
    now = dt.datetime.now(dt.UTC)
    result = db.execute(
        text("UPDATE jobs SET status='pending', lease_owner=NULL, lease_expires_at=NULL WHERE status='leased' AND lease_expires_at < :now"),
        {"now": now},
    )
    db.commit()
    return int(result.rowcount) if result.rowcount is not None else 0  # type: ignore[attr-defined]


def claim_next(db: Session) -> Job | None:
    now = dt.datetime.now(dt.UTC)
    lease_until = now + dt.timedelta(seconds=settings.job_lease_seconds)
    picked = db.execute(
        text(
            "UPDATE jobs SET status='leased', lease_owner=:owner, lease_expires_at=:lease_until "
            "WHERE id = (SELECT id FROM jobs WHERE status='pending' AND run_after <= :now ORDER BY id LIMIT 1) "
            "AND status='pending' RETURNING id"
        ),
        {"owner": WORKER_ID, "lease_until": lease_until, "now": now},
    ).fetchone()
    db.commit()
    if not picked:
        return None
    # The UPDATE above ran as raw SQL, bypassing the ORM's unit-of-work — if this session already
    # has this row cached (e.g. the caller just enqueued it), db.get() would otherwise hand back a
    # stale in-memory copy still showing status='pending'. Force a fresh load.
    db.expire_all()
    return db.get(Job, picked[0])


def mark_done(db: Session, job: Job) -> None:
    job.status = "done"
    job.lease_owner = None
    job.lease_expires_at = None
    db.commit()


def mark_failed(db: Session, job: Job, error: str) -> None:
    job.attempts += 1
    job.last_error = error[:2000]
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.lease_owner = None
        job.lease_expires_at = None
    else:
        backoff = min(300, 5 * (2 ** job.attempts))
        job.status = "pending"
        job.run_after = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=backoff)
        job.lease_owner = None
        job.lease_expires_at = None
    db.commit()
