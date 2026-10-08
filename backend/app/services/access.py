"""
Who can access what: token SIDs for a user, evaluated against folder ACLs.

Folders with identical permissions share one `acls` row, so a whole file server
has a few hundred distinct ACLs at most. Every query that returns files asks
"which of those ACLs let this token open files?" (evaluated here in Python, with
Windows' rules) and filters on `folders.acl_id IN (...)`. A folder without a
readable ACL matches nothing: fail closed.
"""

import threading
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..acl.evaluate import BASELINE_SIDS, InheritedAce, can_read, can_read_files
from ..config import settings
from ..models import Acl, AclEntry, Folder, GroupMember


def baseline_sids_for(user_sid: str) -> set[str]:
    sids = set(BASELINE_SIDS) | set(settings.extra_baseline_sids)
    # Domain Users (RID 513) is the primary group, which LDAP group expansion
    # doesn't return; every user of a domain belongs to it.
    domain, _, rid = user_sid.rpartition("-")
    if domain.startswith("S-1-5-21-") and rid.isdigit():
        sids.add(f"{domain}-513")
    return sids


def token_sids(db: Session, user_sid: str) -> set[str]:
    """
    The SIDs Windows would put in this user's token, limited to groups seen in
    ACLs. For the permission reports; signed-in users use session_token_sids.
    """
    groups = set(db.scalars(select(GroupMember.group_sid).where(GroupMember.member_sid == user_sid)))
    return {user_sid} | baseline_sids_for(user_sid) | groups


def session_token_sids(user_sid: str, group_sids: Iterable[str]) -> set[str]:
    """A signed-in user's token: their SID, their tokenGroups from AD, and the baseline."""
    return {user_sid} | set(group_sids) | baseline_sids_for(user_sid)


class AclCache:
    """
    ACL entries by ACL id. An `acls` row never changes (it is keyed by the hash
    of its content), but ids can be reused after the database is recreated, so
    the cache checks each id's hash before trusting it.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._hashes: dict[int, str] = {}
        self._entries: dict[int, list[InheritedAce]] = {}

    def get(self, db: Session) -> dict[int, list[InheritedAce]]:
        current = dict(db.execute(select(Acl.id, Acl.hash)).all())
        with self._lock:
            stale = [i for i, h in current.items() if self._hashes.get(i) != h]
            if stale or len(current) != len(self._hashes):
                entries: dict[int, list[InheritedAce]] = {i: [] for i in stale}
                for acl_id, sid, ace_type, mask, flags in db.execute(
                    select(AclEntry.acl_id, AclEntry.sid, AclEntry.ace_type, AclEntry.mask, AclEntry.flags)
                    .where(AclEntry.acl_id.in_(stale))
                    .order_by(AclEntry.acl_id, AclEntry.position)
                ):
                    entries[acl_id].append(InheritedAce(sid, ace_type, mask, flags))
                self._entries = {i: self._entries[i] for i in current if i not in entries} | entries
                self._hashes = current
            return self._entries


acl_cache = AclCache()


def readable_file_acl_ids(db: Session, token: set[str] | frozenset[str]) -> list[int]:
    """ACLs whose folders hold files this token can open (the folder's inheritable ACEs: BUG-007)."""
    return [i for i, aces in acl_cache.get(db).items() if can_read_files(aces, token)]


def listable_folder_acl_ids(db: Session, token: set[str] | frozenset[str]) -> list[int]:
    """ACLs whose folders this token can list (the folder's own ACEs)."""
    return [i for i, aces in acl_cache.get(db).items() if can_read(aces, token)]


def can_open_files_in(db: Session, folder: Folder, token: set[str] | frozenset[str]) -> bool:
    return folder.acl_id is not None and folder.acl_id in set(readable_file_acl_ids(db, token))


def can_list(db: Session, folder: Folder, token: set[str] | frozenset[str]) -> bool:
    return folder.acl_id is not None and folder.acl_id in set(listable_folder_acl_ids(db, token))
