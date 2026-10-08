"""
A minimal job queue on top of PostgreSQL.

The API enqueues jobs; the worker claims them one at a time with
SELECT … FOR UPDATE SKIP LOCKED, so no message broker is needed.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Job, Share

logger = logging.getLogger(__name__)

SCAN, RESOLVE, DEDUPE, INDEX = "scan", "resolve_principals", "dedupe", "index"
KINDS = {SCAN, RESOLVE, DEDUPE, INDEX}


def enqueue(
    db: Session, kind: str, payload: Optional[dict[str, Any]] = None,
    requested_by: Optional[str] = None, priority: int = 100,
) -> Job:
    """Queue a job unless an identical one is already waiting."""
    if kind not in KINDS:
        raise ValueError(f"Unknown job kind: {kind}")
    payload = payload or {}
    for job in db.scalars(select(Job).where(Job.kind == kind, Job.status == "queued")):
        if job.payload == payload:
            return job
    job = Job(kind=kind, payload=payload, requested_by=requested_by, priority=priority)
    db.add(job)
    db.commit()
    return job


def enqueue_full_pipeline(db: Session, requested_by: Optional[str] = None) -> list[Job]:
    """Scan every enabled share; the last scan queues principal resolution, indexing and dedupe."""
    jobs = [
        enqueue(db, SCAN, {"share_id": sid}, requested_by)
        for sid in db.scalars(select(Share.id).where(Share.enabled).order_by(Share.id))
    ]
    return jobs


def claim_next(db: Session) -> Optional[Job]:
    job = db.scalars(
        select(Job)
        .where(Job.status == "queued")
        .order_by(Job.priority, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is None:
        db.rollback()
        return None
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    db.commit()
    return job


def finish(db: Session, job: Job, error: Optional[str] = None) -> None:
    job.status = "failed" if error else "done"
    job.error = error
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


def fail_interrupted(db: Session) -> int:
    """Jobs left 'running' by a crashed or restarted worker are marked failed."""
    result = db.execute(
        update(Job)
        .where(Job.status == "running")
        .values(status="failed", error="Interrupted (worker restarted)", finished_at=datetime.now(timezone.utc))
    )
    db.commit()
    return result.rowcount or 0


def pending_scans(db: Session) -> int:
    return len(db.scalars(select(Job.id).where(Job.kind == SCAN, Job.status.in_(("queued", "running")))).all())
