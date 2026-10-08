"""
Sign-in form throttling (BUG-029).

Active Directory locks an account after a number of wrong passwords (a domain
policy). Without a limit here, anyone could lock a colleague out by typing their
username into the form a few times. After LOGIN_MAX_FAILURES failures within
LOGIN_WINDOW_MINUTES, the username is refused until the window has passed,
*without asking AD*, so this app alone can't push AD's counter to its threshold.

Keep LOGIN_MAX_FAILURES below the domain's lockout threshold, and
LOGIN_WINDOW_MINUTES at or above its "reset account lockout counter after" time
(ask IT). Counted per account, in memory: the API runs as one process, and a
restart only forgets recent failures.
"""

import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..config import settings

_lock = threading.Lock()
_failures: dict[str, deque[datetime]] = {}


def normalize_username(typed: str) -> str:
    """`DOMAIN\\alice`, `alice@company.com` and `Alice` are all `alice` (BUG-029)."""
    name = typed.strip()
    if "\\" in name:
        name = name.split("\\", 1)[1]
    elif "@" in name:
        user, _, domain = name.rpartition("@")
        if domain.lower() == settings.ldap_domain.lower():
            name = user
    return name.lower()


def _recent(username: str, now: datetime) -> deque[datetime]:
    window = timedelta(minutes=settings.login_window_minutes)
    times = _failures.setdefault(username, deque())
    while times and now - times[0] >= window:
        times.popleft()
    return times


def blocked_for(username: str, now: Optional[datetime] = None) -> Optional[timedelta]:
    """How long this username is still refused, or None if it may try."""
    if settings.login_max_failures <= 0:
        return None
    now = now or datetime.now(timezone.utc)
    with _lock:
        times = _recent(username, now)
        if len(times) < settings.login_max_failures:
            return None
        return times[0] + timedelta(minutes=settings.login_window_minutes) - now


def record_failure(username: str, now: Optional[datetime] = None) -> None:
    now = now or datetime.now(timezone.utc)
    with _lock:
        _recent(username, now).append(now)


def record_success(username: str) -> None:
    with _lock:
        _failures.pop(username, None)


def reset() -> None:
    with _lock:
        _failures.clear()
