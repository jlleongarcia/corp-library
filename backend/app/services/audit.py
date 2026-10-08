"""Audit log: sign-ins, searches, document views and downloads."""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AuditEvent

logger = logging.getLogger(__name__)

# audit_read: an admin queried the log itself, so looking at people's activity leaves a trace too.
ACTIONS = ("sign_in", "sign_in_failed", "sign_out", "search", "view", "preview", "download", "denied", "audit_read")


def record(
    db: Session, action: str, username: Optional[str], request: Optional[Request] = None,
    file_id: Optional[int] = None, path: Optional[str] = None, **detail: Any,
) -> None:
    """Store one event. Commits: the record must exist even if the response then fails."""
    assert action in ACTIONS, action
    db.add(AuditEvent(
        action=action, username=username, file_id=file_id, path=path, detail=detail,
        client_ip=request.client.host if request is not None and request.client else None,
    ))
    db.commit()


def purge_old(db: Session, now: Optional[datetime] = None) -> int:
    if settings.audit_retention_days <= 0:
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=settings.audit_retention_days)
    n = db.execute(delete(AuditEvent).where(AuditEvent.at < cutoff)).rowcount or 0
    db.commit()
    if n:
        logger.info("Audit log: removed %d events older than %d days.", n, settings.audit_retention_days)
    return n


def query(
    db: Session, username: Optional[str] = None, action: Optional[str] = None,
    since: Optional[date] = None, until: Optional[date] = None, limit: int = 200, offset: int = 0,
) -> dict:
    stmt = select(AuditEvent)
    if username:
        stmt = stmt.where(AuditEvent.username == username.strip().lower())
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if since:
        stmt = stmt.where(AuditEvent.at >= datetime.combine(since, time.min, timezone.utc))
    if until:
        stmt = stmt.where(AuditEvent.at < datetime.combine(until + timedelta(days=1), time.min, timezone.utc))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    events = db.scalars(stmt.order_by(AuditEvent.id.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "events": events}
