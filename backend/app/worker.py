"""
Background worker: `python -m app.worker`.

Runs queued jobs (scans, principal resolution, duplicate detection) and
enqueues the nightly full pipeline at SCAN_HOUR local time.
"""

import logging
import signal
import time
import traceback
from datetime import date, datetime

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


def maybe_schedule(db, last_scheduled: date | None) -> date | None:
    if settings.scan_hour < 0:
        return last_scheduled
    now = datetime.now().astimezone()  # local time (TZ env var), timezone-aware
    if now.hour == settings.scan_hour and last_scheduled != now.date():
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        already = db.scalar(select(Job.id).where(
            Job.kind == jobs.SCAN, Job.requested_by == "schedule", Job.created_at >= midnight
        ).limit(1))
        if already is None:
            logger.info("Nightly schedule: queueing a full scan.")
            jobs.enqueue_full_pipeline(db, requested_by="schedule")
        return now.date()
    return last_scheduled


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
