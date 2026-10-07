"""
Background worker: `python -m app.worker`.

Runs queued jobs (scans, principal resolution, duplicate detection) and
enqueues the nightly full pipeline at SCAN_HOUR local time.
"""

import logging
import signal
import time
import traceback
from datetime import datetime, timedelta

from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .models import Job, Share
from .services import jobs
from .services.dedupe import run_dedupe
from .services.directory import open_directory, resolve_principals
from .services.scanner import scan_share

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s")
logger = logging.getLogger("worker")

POLL_SECONDS = 5
# A nightly scan missed because the worker was busy still runs if the worker frees
# up within this window; later than that it waits for the next night rather than
# loading the file server during working hours.
CATCH_UP = timedelta(hours=4)
_stop = False


def _handle_stop(*_):
    global _stop
    _stop = True
    logger.info("Stop requested; finishing the current job.")


def run_job(db, job: Job) -> None:
    if job.kind == jobs.SCAN:
        share = db.get(Share, job.payload["share_id"])
        if share is None or not share.enabled:
            raise RuntimeError(f"Share {job.payload['share_id']} missing or disabled")
        run = scan_share(db, share)
        if run.status == "failed":
            raise RuntimeError(run.error_sample or "scan failed")
        # After the last scan of a batch, refresh names/groups and duplicates.
        if jobs.pending_scans(db) <= 1:  # only this job is still running
            jobs.enqueue(db, jobs.RESOLVE, priority=110)
            jobs.enqueue(db, jobs.DEDUPE, priority=120)
    elif job.kind == jobs.RESOLVE:
        directory = open_directory()
        try:
            resolve_principals(db, directory, force=bool(job.payload.get("force")))
        finally:
            if directory is not None:
                directory.close()
    elif job.kind == jobs.DEDUPE:
        run_dedupe(db)
    else:
        raise RuntimeError(f"Unknown job kind {job.kind}")


def maybe_schedule(db, last_scheduled: datetime | None, now: datetime | None = None) -> datetime | None:
    """
    Queue the nightly pipeline once per day, at SCAN_HOUR or as soon as the worker
    is free within CATCH_UP afterwards. The worker only checks between jobs,
    so a long job running across SCAN_HOUR must not make the night's scan vanish.
    Returns the slot that was handled, so it is checked only once.
    """
    if settings.scan_hour < 0:
        return last_scheduled
    now = now or datetime.now().astimezone()  # local time (TZ env var), timezone-aware
    slot = now.replace(hour=settings.scan_hour, minute=0, second=0, microsecond=0)
    if slot > now:
        slot -= timedelta(days=1)  # the most recent SCAN_HOUR
    if slot == last_scheduled or now - slot >= CATCH_UP:
        return last_scheduled
    already = db.scalar(select(Job.id).where(
        Job.kind == jobs.SCAN, Job.requested_by == "schedule", Job.created_at >= slot
    ).limit(1))
    if already is None:
        late = now - slot
        logger.info("Nightly schedule: queueing a full scan%s.",
                    f" ({int(late.total_seconds() // 60)} min late)" if late >= timedelta(minutes=5) else "")
        jobs.enqueue_full_pipeline(db, requested_by="schedule")
    return slot


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    with SessionLocal() as db:
        n = jobs.fail_interrupted(db)
        if n:
            logger.warning("Marked %d interrupted job(s) as failed.", n)

    if settings.scan_hour < 0:
        logger.info("Worker started (nightly scan disabled).")
    else:
        logger.info("Worker started (nightly scan at %02d:00).", settings.scan_hour)
    last_scheduled = None
    while not _stop:
        with SessionLocal() as db:
            last_scheduled = maybe_schedule(db, last_scheduled)
            job = jobs.claim_next(db)
            if job is None:
                time.sleep(POLL_SECONDS)
                continue
            logger.info("Job %d (%s %s) started.", job.id, job.kind, job.payload)
            try:
                run_job(db, job)
            except Exception as exc:
                db.rollback()
                logger.error("Job %d failed: %s", job.id, exc)
                jobs.finish(db, job, error=f"{exc}\n\n{traceback.format_exc()}"[:5000])
            else:
                jobs.finish(db, job)
                logger.info("Job %d done.", job.id)


if __name__ == "__main__":
    main()
