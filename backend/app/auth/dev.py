"""
DEV_MODE identities: sign in as anyone, no password, no Active Directory.

Users and groups get stable fake SIDs derived from their names, so the same
permission code that runs in production can be exercised on a developer PC
(see services/devacl.py for the matching fake folder permissions).
"""

import zlib

from ..config import settings
from .ldap_client import LDAPUser

DEV_DOMAIN = "S-1-5-21-999-999-999"
EVERYONE = "S-1-1-0"


def dev_sid(name: str) -> str:
    """A fake domain SID for a user or group name ("everyone" is the real Everyone)."""
    name = name.strip().lower()
    if name == "everyone":
        return EVERYONE
    return f"{DEV_DOMAIN}-{1000 + zlib.crc32(name.encode()) % 1_000_000}"


def dev_groups() -> dict[str, list[str]]:
    """DEV_GROUPS="alice:hr,finance;bob:finance" -> {"alice": ["hr", "finance"], ...}."""
    out: dict[str, list[str]] = {}
    for item in settings.dev_groups.split(";"):
        user, _, groups = item.partition(":")
        if user.strip():
            out[user.strip().lower()] = [g.strip().lower() for g in groups.split(",") if g.strip()]
    return out


def dev_identity(username: str) -> LDAPUser:
    groups = dev_groups().get(username, [])
    return LDAPUser(
        username=username,
        display_name=username.title(),
        email="",
        sid=dev_sid(username),
        group_sids=[dev_sid(g) for g in groups],
    )
