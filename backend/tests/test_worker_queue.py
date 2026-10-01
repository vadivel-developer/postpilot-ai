from __future__ import annotations

import datetime as dt


def test_claim_is_atomic_and_marks_leased(db_session):
    from app.worker.queue import claim_next, enqueue

    job = enqueue(db_session, "process_draft", draft_id=None, payload={"x": 1})
    claimed = claim_next(db_session)
    assert claimed is not None and claimed.id == job.id
    assert claimed.status == "leased"
    assert claim_next(db_session) is None  # nothing else pending


def test_failed_job_retries_with_backoff_then_gives_up(db_session):
    from app.models.db import Job
    from app.worker.queue import claim_next, enqueue, mark_failed

    job = enqueue(db_session, "process_draft", draft_id=None, max_attempts=2)
    claimed = claim_next(db_session)
    mark_failed(db_session, claimed, "boom 1")
    refreshed = db_session.get(Job, job.id)
    assert refreshed.status == "pending"  # attempt 1 of 2: requeued
    assert refreshed.attempts == 1
    assert refreshed.run_after > dt.datetime.now(dt.UTC)

    refreshed.run_after = dt.datetime.now(dt.UTC)  # skip the backoff wait for the test
    db_session.commit()
    claimed2 = claim_next(db_session)
    assert claimed2 is not None
    mark_failed(db_session, claimed2, "boom 2")
    refreshed2 = db_session.get(Job, job.id)
    assert refreshed2.status == "failed"  # attempt 2 of 2: gives up
    assert refreshed2.last_error == "boom 2"


def test_expired_lease_is_recovered_after_a_simulated_worker_crash(db_session):
    from app.worker.queue import claim_next, enqueue, recover_expired_leases

    job = enqueue(db_session, "process_draft", draft_id=None)
    claimed = claim_next(db_session)
    assert claimed.status == "leased"

    # Simulate the worker crashing mid-job: force the lease into the past.
    claimed.lease_expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=5)
    db_session.commit()

    recovered = recover_expired_leases(db_session)
    assert recovered == 1
    reclaimed = claim_next(db_session)
    assert reclaimed is not None and reclaimed.id == job.id


def test_done_job_is_not_reclaimed(db_session):
    from app.worker.queue import claim_next, enqueue, mark_done

    enqueue(db_session, "process_draft", draft_id=None)
    job = claim_next(db_session)
    mark_done(db_session, job)
    assert claim_next(db_session) is None
