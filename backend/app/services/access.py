"""
Who can access what: token SIDs for a user, evaluated against folder ACLs.

Folders with identical permissions share one `acls` row, so a whole file server
has a few hundred distinct ACLs at most. Every query that returns files asks
"which of those ACLs let this token open files?" (evaluated here in Python, with
Windows' rules) and filters on `folders.acl_id IN (...)`. A folder without a
readable ACL matches nothing: fail closed.

A few files have permissions of their own (explicit ACEs, or inheritance
disabled: BUG-023). Those are evaluated per (file ACL, folder ACL) pair, as
Windows would: the file's explicit ACEs first, then what it inherits from the
folder unless inheritance is disabled.
"""

import threading
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from ..acl.evaluate import BASELINE_SIDS, InheritedAce, can_read, can_read_files, file_aces
from ..config import settings
from ..models import Acl, AclEntry, File, Folder, GroupMember


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
        self._protected: frozenset[int] = frozenset()

    def get(self, db: Session) -> dict[int, list[InheritedAce]]:
        rows = db.execute(select(Acl.id, Acl.hash, Acl.is_protected)).all()
        current = {i: h for i, h, _ in rows}
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
                self._protected = frozenset(i for i, _, p in rows if p)
            return self._entries

    def is_protected(self, acl_id: int) -> bool:
        return acl_id in self._protected


acl_cache = AclCache()


@dataclass
class FileAccess:
    """Which files one token may open: the answer to every "can they see this file?"."""

    # Folders whose (inheriting) files this token can open.
    folder_acl_ids: set[int]
    # For files with their own permissions: file ACL id -> folder ACL ids it can be opened in.
    file_pairs: dict[int, set[int]] = field(default_factory=dict)
    # Shares holding at least one such file.
    file_pair_shares: set[int] = field(default_factory=set)

    def can_open(self, file_acl_id: int | None, folder_acl_id: int | None) -> bool:
        if file_acl_id is None:
            return folder_acl_id in self.folder_acl_ids
        return folder_acl_id in self.file_pairs.get(file_acl_id, ())

    def clause(self) -> ColumnElement[bool]:
        """SQL condition on File and Folder (both must be in the query)."""
        inheriting = and_(File.acl_id.is_(None), Folder.acl_id.in_(self.folder_acl_ids))
        own = [and_(File.acl_id == f, Folder.acl_id.in_(folders)) for f, folders in self.file_pairs.items()]
        return or_(inheriting, *own) if own else inheriting


def file_access(db: Session, token: set[str] | frozenset[str]) -> FileAccess:
    acls = acl_cache.get(db)
    access = FileAccess({i for i, aces in acls.items() if can_read_files(aces, token)})
    # Distinct (file ACL, folder ACL) pairs: few, and served by the partial index on files.acl_id.
    pairs = db.execute(
        select(File.acl_id, Folder.acl_id, File.share_id).distinct()
        .join(Folder, File.folder_id == Folder.id)
        .where(File.acl_id.is_not(None))
    ).all()
    readable: dict[int, set[int]] = defaultdict(set)
    for file_acl, folder_acl, share_id in pairs:
        if folder_acl is None:
            continue  # its folder's permissions are unknown: like every file there, hidden
        own = acls.get(file_acl, [])
        if acl_cache.is_protected(file_acl):
            aces = own
        else:
            # Windows' order: the file's explicit ACEs, then the inherited ones.
            aces = [*own, *file_aces(acls.get(folder_acl, []))]
        if can_read(aces, token):
            readable[file_acl].add(folder_acl)
            access.file_pair_shares.add(share_id)
    access.file_pairs = dict(readable)
    return access


def listable_folder_acl_ids(db: Session, token: set[str] | frozenset[str]) -> list[int]:
    """ACLs whose folders this token can list (the folder's own ACEs)."""
    return [i for i, aces in acl_cache.get(db).items() if can_read(aces, token)]
