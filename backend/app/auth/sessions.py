"""
Sessions: who is signed in, and with which groups.

Django analogy: django.contrib.sessions with the database backend. Sign-in
creates a row in `sessions` and sends its random token in an HttpOnly cookie,
which JavaScript can't read (so an XSS bug can't steal it). Each request looks
the token up; signing out deletes the row, which really ends the session.

The session also holds the user's token SIDs (their groups from AD), which
every permission check uses. They are re-read from AD every
GROUPS_REFRESH_HOURS so group changes reach long-lived sessions.

CSRF: the cookie is SameSite=Lax, and every state-changing request must carry
`X-Requested-With: XMLHttpRequest`. Browsers only let a page add that header
to requests to its own origin, so another site can't forge one.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import AuthSession, User
from ..services.access import session_token_sids
from .dev import dev_identity
from .ldap_client import DirectoryUnavailable, LDAPUser, lookup_user

logger = logging.getLogger(__name__)

COOKIE = "corplib_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
TOUCH_EVERY = timedelta(minutes=10)  # how often the sliding expiry is pushed forward
GROUPS_RETRY_AFTER = timedelta(minutes=15)  # after a failed refresh, don't hammer AD
# If AD can't be reached, cached groups are trusted this many refresh periods, then
# the user must sign in again.
GROUPS_MAX_AGE_FACTOR = 3

_refresh_failed_at: dict[int, datetime] = {}


@dataclass(frozen=True)
class CurrentUser:
    username: str
    display_name: str
    email: str
    is_admin: bool
    sid: Optional[str] = None
    token_sids: frozenset[str] = frozenset()
    session_id: Optional[int] = None


def is_admin_user(username: str) -> bool:
    return username.lower() in {u.lower() for u in settings.admin_users}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(dt: datetime) -> datetime:
    # SQLite (tests) returns naive datetimes.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE, token, max_age=settings.session_days * 86400, httponly=True,
        secure=settings.cookie_secure, samesite="lax", path="/",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")


def _current_user(row: AuthSession) -> CurrentUser:
    u = row.user
    return CurrentUser(
        username=u.username,
        display_name=u.display_name or u.username,
        email=u.email or "",
        # Re-evaluated on every request, so removing someone from ADMIN_USERS is immediate.
        is_admin=is_admin_user(u.username),
        sid=u.sid,
        token_sids=frozenset(row.token_sids),
        session_id=row.id,
    )


def start_session(db: Session, request: Request, response: Response, who: LDAPUser, method: str) -> CurrentUser:
    """Record the user, open a session for them and set the cookie."""
    now = datetime.now(timezone.utc)
    user = db.scalar(select(User).where(User.username == who.username))
    if user is None:
        user = User(username=who.username)
        db.add(user)
    user.display_name, user.email, user.sid = who.display_name, who.email, who.sid
    user.is_admin = is_admin_user(who.username)
    user.last_login = now

    token = secrets.token_urlsafe(32)
    row = AuthSession(
        token_hash=_hash(token), user=user, method=method,
        token_sids=sorted(session_token_sids(who.sid, who.group_sids)),
        groups_resolved_at=now, created_at=now, last_seen_at=now,
        expires_at=now + timedelta(days=settings.session_days),
        client_ip=client_ip(request), user_agent=(request.headers.get("user-agent") or "")[:300],
    )
    db.add(row)
    db.commit()
    _set_cookie(response, token)
    return _current_user(row)


def end_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        row = db.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(token)))
        if row is not None:
            db.delete(row)
            db.commit()
    clear_cookie(response)


def _refresh_groups(db: Session, row: AuthSession, now: datetime) -> bool:
    """Re-read the user's groups from AD. False = the session must end."""
    resolved_at = _aware(row.groups_resolved_at)
    if now - resolved_at < timedelta(hours=settings.groups_refresh_hours):
        return True
    failed_at = _refresh_failed_at.get(row.id)
    if failed_at and now - failed_at < GROUPS_RETRY_AFTER:
        return True

    username = row.user.username
    try:
        who = dev_identity(username) if row.method == "dev" else lookup_user(username)
    except DirectoryUnavailable:
        _refresh_failed_at[row.id] = now
        max_age = timedelta(hours=settings.groups_refresh_hours * GROUPS_MAX_AGE_FACTOR)
        if now - resolved_at < max_age:
            logger.warning("Couldn't refresh the groups of '%s'; using the ones from %s.", username, resolved_at)
            return True
        logger.warning("Groups of '%s' too old to trust and AD unreachable: session ended.", username)
        return False
    _refresh_failed_at.pop(row.id, None)
    if who is None or who.sid != row.user.sid:
        logger.info("Account '%s' is gone or disabled in AD: session ended.", username)
        return False
    row.token_sids = sorted(session_token_sids(who.sid, who.group_sids))
    row.groups_resolved_at = now
    return True


def get_current_user(request: Request, response: Response, db: Session = Depends(get_db)) -> CurrentUser:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    token = request.cookies.get(COOKIE)
    if not token:
        raise unauthorized
    if request.method not in SAFE_METHODS and request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing X-Requested-With header")

    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(token)))
    now = datetime.now(timezone.utc)
    # (A stale cookie stays in the browser until the next sign-in replaces it:
    # headers set here are dropped when an HTTPException is raised.)
    if row is None or _aware(row.expires_at) <= now:
        raise unauthorized
    if not _refresh_groups(db, row, now):
        _refresh_failed_at.pop(row.id, None)
        db.delete(row)
        db.commit()
        raise unauthorized

    if now - _aware(row.last_seen_at) >= TOUCH_EVERY:
        # Sliding expiry: keep signed-in people signed in while they use the app.
        row.last_seen_at = now
        row.expires_at = now + timedelta(days=settings.session_days)
        _set_cookie(response, token)
    if db.dirty:
        db.commit()
    return _current_user(row)


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
