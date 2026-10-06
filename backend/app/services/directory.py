"""
Resolve the SIDs found in ACLs to names, and expand groups to their users.

ACLs only contain SIDs. To show readable reports (and, from phase 1, to match
users to folders) we look each SID up in Active Directory and store the result
in `principals`. For every group referenced by an ACL we also store its
transitive user members in `group_members`.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

from sqlalchemy import delete, select, union
from sqlalchemy.orm import Session

from ..acl.descriptor import parse_sid
from ..config import settings
from ..models import AclEntry, Folder, GroupMember, Principal

logger = logging.getLogger(__name__)

REFRESH_AFTER = timedelta(days=1)

WELL_KNOWN = {
    "S-1-1-0": "Everyone",
    "S-1-3-0": "CREATOR OWNER",
    "S-1-3-1": "CREATOR GROUP",
    "S-1-3-4": "OWNER RIGHTS",
    "S-1-5-2": "NETWORK",
    "S-1-5-4": "INTERACTIVE",
    "S-1-5-9": "Enterprise Domain Controllers",
    "S-1-5-11": "Authenticated Users",
    "S-1-5-18": "SYSTEM",
    "S-1-5-32-544": "BUILTIN\\Administrators",
    "S-1-5-32-545": "BUILTIN\\Users",
    "S-1-5-32-547": "BUILTIN\\Power Users",
    "S-1-5-32-549": "BUILTIN\\Server Operators",
    "S-1-5-32-551": "BUILTIN\\Backup Operators",
}


class Directory(Protocol):
    def lookup_sid(self, sid: str) -> Optional[dict]:
        """Return {name, display_name, kind, dn} or None if the SID is unknown."""

    def group_user_members(self, group_dn: str) -> list[str]:
        """Return the SIDs of all users that are (transitively) members of the group."""


class LdapDirectory:
    def __init__(self):
        from ldap3 import Connection, Server

        server = Server(settings.ldap_server, port=settings.ldap_port, use_ssl=settings.ldap_use_ssl)
        self.conn = Connection(
            server, user=settings.ldap_bind_dn, password=settings.ldap_bind_password,
            auto_bind=True, read_only=True,
        )

    def lookup_sid(self, sid: str) -> Optional[dict]:
        from ldap3.utils.conv import escape_filter_chars

        self.conn.search(
            settings.ldap_base_dn,
            f"(objectSid={escape_filter_chars(sid)})",
            attributes=["sAMAccountName", "displayName", "objectClass"],
        )
        if not self.conn.entries:
            return None
        e = self.conn.entries[0]
        classes = {c.lower() for c in e.objectClass.values}
        kind = "group" if "group" in classes else "computer" if "computer" in classes else "user"
        sam = str(e.sAMAccountName) if e.sAMAccountName else sid
        return {
            "name": sam,
            "display_name": str(e.displayName) if e.displayName else sam,
            "kind": kind,
            "dn": e.entry_dn,
        }

    def group_user_members(self, group_dn: str) -> list[str]:
        from ldap3 import SUBTREE
        from ldap3.utils.conv import escape_filter_chars

        # LDAP_MATCHING_RULE_IN_CHAIN expands nested groups server-side.
        flt = (
            "(&(objectCategory=person)(objectClass=user)"
            f"(memberOf:1.2.840.113556.1.4.1941:={escape_filter_chars(group_dn)}))"
        )
        sids = []
        for item in self.conn.extend.standard.paged_search(
            settings.ldap_base_dn, flt, SUBTREE, attributes=["objectSid"], paged_size=500, generator=True
        ):
            raw = item.get("raw_attributes", {}).get("objectSid")
            if raw:
                sids.append(parse_sid(raw[0])[0])
        return sids

    def close(self) -> None:
        self.conn.unbind()


def referenced_sids(db: Session) -> set[str]:
    q = union(
        select(AclEntry.sid),
        select(Folder.owner_sid).where(Folder.owner_sid.is_not(None)),
    )
    return {row[0] for row in db.execute(q)}


def resolve_principals(db: Session, directory: Optional[Directory], force: bool = False) -> dict:
    """Resolve new or stale SIDs. Without a directory only well-known SIDs get names."""
    now = datetime.now(timezone.utc)
    known = {p.sid: p for p in db.scalars(select(Principal))}
    stats = {"resolved": 0, "unknown": 0, "groups_expanded": 0}

    for sid in sorted(referenced_sids(db)):
        p = known.get(sid)
        resolved_at = p.resolved_at if p else None
        if resolved_at and resolved_at.tzinfo is None:
            resolved_at = resolved_at.replace(tzinfo=timezone.utc)
        if p and not force and resolved_at and now - resolved_at < REFRESH_AFTER:
            continue
        if p is None:
            p = Principal(sid=sid)
            db.add(p)

        if sid in WELL_KNOWN:
            p.name, p.display_name, p.kind, p.dn = WELL_KNOWN[sid], WELL_KNOWN[sid], "wellknown", None
        else:
            info = None
            if directory is not None:
                try:
                    info = directory.lookup_sid(sid)
                except Exception as exc:
                    logger.warning("LDAP lookup failed for %s: %s", sid, exc)
            if info:
                p.name, p.display_name, p.kind, p.dn = info["name"], info["display_name"], info["kind"], info["dn"]
            elif directory is not None:
                # Typically a local group on the file server, or a deleted account.
                p.kind = "unknown"
        if p.kind == "unknown":
            stats["unknown"] += 1
        else:
            stats["resolved"] += 1

        if p.kind == "group" and p.dn and directory is not None:
            try:
                members = set(directory.group_user_members(p.dn))
            except Exception as exc:
                logger.warning("LDAP member expansion failed for %s: %s", p.name, exc)
            else:
                db.execute(delete(GroupMember).where(GroupMember.group_sid == sid))
                db.add_all(GroupMember(group_sid=sid, member_sid=m) for m in members)
                stats["groups_expanded"] += 1
                # Make sure member users have a principal row (for report names).
                for m in members - known.keys():
                    info = directory.lookup_sid(m)
                    if info:
                        u = Principal(sid=m, resolved_at=now, **info)
                        db.merge(u)
                        known[m] = u
        p.resolved_at = now
        known[sid] = p
        db.commit()

    logger.info("Principals: %s", stats)
    return stats


def open_directory() -> Optional[LdapDirectory]:
    if not settings.ldap_server or not settings.ldap_bind_dn:
        logger.info("LDAP not configured; only well-known SIDs will be named.")
        return None
    return LdapDirectory()
