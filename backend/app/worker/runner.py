"""The worker loop: claims one job at a time, runs it, and reports success/failure back to the
queue. Must be running for any processing or publishing to happen — the API only enqueues jobs, it
never runs them inline, so a request to "generate a post" returns immediately and the dashboard
polls for progress.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.models.db import Draft, SessionLocal, init_db
from app.services.draft_processing import process_draft
from app.services.publishing import execute_publish
from app.worker.queue import claim_next, mark_done, mark_failed, recover_expired_leases

log = logging.getLogger("ltp.worker")


async def _run_job(job) -> None:
    db = SessionLocal()
    try:
        if job.job_type == "process_draft":
            skip_extraction = bool((job.payload or {}).get("skip_extraction"))
            await process_draft(db, job.draft_id, skip_extraction=skip_extraction)
        elif job.job_type == "publish_draft":
            draft = db.get(Draft, job.draft_id)
            if draft is None:
                raise RuntimeError(f"draft {job.draft_id} not found")
            await execute_publish(db, draft)
        else:
            raise RuntimeError(f"unknown job type '{job.job_type}'")
    finally:
        db.close()


async def worker_loop(stop_event: asyncio.Event | None = None) -> None:
    init_db()
    logging.basicConfig(level=settings.log_level.upper())
    log.info("worker started; polling every %.1fs", settings.worker_poll_interval_seconds)
    while stop_event is None or not stop_event.is_set():
        db = SessionLocal()
        try:
            recovered = recover_expired_leases(db)
            if recovered:
                log.warning("recovered %d job(s) with an expired lease", recovered)
            job = claim_next(db)
        finally:
            db.close()

        if job is None:
            await asyncio.sleep(settings.worker_poll_interval_seconds)
            continue

        log.info("claimed job %s (%s) draft=%s attempt=%d", job.id, job.job_type, job.draft_id, job.attempts + 1)
        db2 = SessionLocal()
        try:
            await _run_job(job)
            job2 = db2.merge(job)
            mark_done(db2, job2)
            log.info("job %s done", job.id)
        except Exception as exc:  # a single job's failure must never kill the worker loop
            log.exception("job %s failed", job.id)
            job2 = db2.merge(job)
            mark_failed(db2, job2, str(exc))
        finally:
            db2.close()


if __name__ == "__main__":
    asyncio.run(worker_loop())
