"""
Share scanner.

Walks a share folder by folder. For each folder it reads the security descriptor
(stored as a deduplicated ACL) and lists its entries, then reconciles them with
the database: new rows are inserted, changed files updated (and their hashes
cleared), and entries that disappeared are deleted.

Reconciliation happens per folder, so a folder that can't be listed (permission
error, network hiccup) keeps its previous contents instead of being wiped.
"""

import logging
import posixpath
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..acl.descriptor import parse_security_descriptor
from ..config import settings
from ..models import Acl, AclEntry, File, Folder, ScanRun, Share
from .sources import DirEntry, FileSource, source_for

logger = logging.getLogger(__name__)

MAX_ERROR_SAMPLE = 20


class AclStore:
    """Get-or-create ACL rows by hash, cached for the duration of a scan."""

    def __init__(self, db: Session):
        self.db = db
        self.cache: dict[str, int] = {}

    def acl_id_for(self, sd_bytes: bytes) -> tuple[int, Optional[str]]:
        sd = parse_security_descriptor(sd_bytes)
        key = sd.acl_hash()
        if key not in self.cache:
            acl_id = self.db.scalar(select(Acl.id).where(Acl.hash == key))
            if acl_id is None:
                acl = Acl(
                    hash=key,
                    is_protected=sd.is_protected,
                    is_null_dacl=sd.is_null_dacl,
                    has_explicit=sd.has_explicit_aces,
                    entries=[
                        AclEntry(position=i, sid=a.sid, ace_type=a.ace_type, mask=a.mask, flags=a.flags)
                        for i, a in enumerate(sd.aces)
                    ],
                )
                self.db.add(acl)
                self.db.flush()
                acl_id = acl.id
            self.cache[key] = acl_id
        return self.cache[key], sd.owner_sid


def _extension(name: str) -> str:
    _, dot, ext = name.rpartition(".")
    return ext.lower()[:32] if dot and _ else ""


def _ignored(name: str) -> bool:
    if name in settings.scan_ignore_names:
        return True
    return any(name.startswith(p) for p in settings.scan_ignore_prefixes)


def _same_time(a: Optional[datetime], b: Optional[datetime]) -> bool:
    if a is None or b is None:
        return a is b
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    # SQLite and some SMB servers lose sub-second precision.
    return abs((a - b).total_seconds()) < 1


class ShareScanner:
    def __init__(self, db: Session, share: Share, source: Optional[FileSource] = None):
        self.db = db
        self.share = share
        self.source = source or source_for(share.path)
        self.acls = AclStore(db)
        self.run: Optional[ScanRun] = None
        self.errors: list[str] = []

    # ── bookkeeping ───────────────────────────────────────────────────────────

    def _error(self, where: str, exc: Exception) -> None:
        self.run.error_count += 1
        msg = f"{where}: {type(exc).__name__}: {exc}"
        logger.warning("Scan %s: %s", self.share.name, msg)
        if len(self.errors) < MAX_ERROR_SAMPLE:
            self.errors.append(msg)

    def _root(self) -> Folder:
        root = self.db.scalar(
            select(Folder).where(Folder.share_id == self.share.id, Folder.parent_id.is_(None))
        )
        if root is None:
            root = Folder(share_id=self.share.id, parent_id=None, name="", path="", depth=0)
            self.db.add(root)
            self.db.flush()
        return root

    # ── main loop ─────────────────────────────────────────────────────────────

    def scan(self) -> ScanRun:
        self.run = ScanRun(share_id=self.share.id)
        self.db.add(self.run)
        self.db.commit()
        logger.info("Scan started: %s (%s)", self.share.name, self.share.path)

        try:
            stack = [self._root()]
            processed = 0
            while stack:
                folder = stack.pop()
                stack.extend(self._process_folder(folder))
                processed += 1
                if processed % settings.scan_commit_every == 0:
                    self._flush_progress()
            self.run.status = "partial" if self.run.error_count else "success"
        except Exception as exc:  # a failure outside a single folder: abort the run
            self.db.rollback()
            self._error("scan aborted", exc)
            self.run.status = "failed"
        finally:
            self.run.finished_at = datetime.now(timezone.utc)
            self.run.error_sample = "\n".join(self.errors) or None
            self.db.add(self.run)
            self.db.commit()
        logger.info(
            "Scan finished: %s status=%s folders=%d files=%d (+%d ~%d -%d) errors=%d",
            self.share.name, self.run.status, self.run.folders_seen, self.run.files_seen,
            self.run.files_added, self.run.files_updated, self.run.files_removed, self.run.error_count,
        )
        return self.run

    def _flush_progress(self) -> None:
        self.db.add(self.run)
        self.db.commit()

    def _process_folder(self, folder: Folder) -> list[Folder]:
        self.run.folders_seen += 1

        try:
            sd = self.source.get_security_descriptor(folder.path)
            if sd is None:
                folder.acl_id, folder.owner_sid, folder.acl_error = None, None, None
            else:
                folder.acl_id, folder.owner_sid = self.acls.acl_id_for(sd)
                folder.acl_error = None
        except Exception as exc:  # DescriptorError, OSError and the many SMB exception types
            # Without a readable ACL nobody but admins will see this folder (fail closed).
            folder.acl_id = None
            folder.acl_error = f"{type(exc).__name__}: {exc}"[:500]
            self._error(f"ACL {self.source.display_path(folder.path)}", exc)

        try:
            entries = self.source.list_dir(folder.path)
        except Exception as exc:
            self._error(f"list {self.source.display_path(folder.path)}", exc)
            return []  # keep previous contents; don't descend

        dirs: dict[str, DirEntry] = {}
        files: dict[str, DirEntry] = {}
        for e in entries:
            if _ignored(e.name) or e.is_reparse_point:
                continue
            (dirs if e.is_dir else files)[e.name] = e

        self._reconcile_files(folder, files)
        return self._reconcile_subfolders(folder, dirs)

    def _reconcile_files(self, folder: Folder, seen: dict[str, DirEntry]) -> None:
        existing = {
            f.name: f for f in self.db.scalars(select(File).where(File.folder_id == folder.id))
        }
        for name, e in seen.items():
            self.run.files_seen += 1
            row = existing.pop(name, None)
            if row is None:
                self.db.add(
                    File(
                        share_id=self.share.id, folder_id=folder.id, name=name,
                        extension=_extension(name), size=e.size, mtime=e.mtime, ctime=e.ctime,
                    )
                )
                self.run.files_added += 1
            elif row.size != e.size or not _same_time(row.mtime, e.mtime):
                row.size, row.mtime, row.ctime = e.size, e.mtime, e.ctime
                row.quick_hash = row.content_hash = None
                row.indexed_at = datetime.now(timezone.utc)
                self.run.files_updated += 1
        if existing:
            self.db.execute(delete(File).where(File.id.in_([f.id for f in existing.values()])))
            self.run.files_removed += len(existing)

    def _reconcile_subfolders(self, folder: Folder, seen: dict[str, DirEntry]) -> list[Folder]:
        existing = {
            f.name: f for f in self.db.scalars(select(Folder).where(Folder.parent_id == folder.id))
        }
        children = []
        for name, e in seen.items():
            row = existing.pop(name, None)
            if row is None:
                row = Folder(
                    share_id=self.share.id, parent_id=folder.id, name=name,
                    path=posixpath.join(folder.path, name) if folder.path else name,
                    depth=folder.depth + 1,
                )
                self.db.add(row)
            row.mtime = e.mtime
            children.append(row)
        for gone in existing.values():
            self.run.files_removed += self._count_files_under(gone)
            self.db.delete(gone)  # cascades to subfolders and files in the database
        self.db.flush()
        return children

    def _count_files_under(self, folder: Folder) -> int:
        prefix = folder.path + "/"
        return self.db.scalar(
            select(func.count(File.id))
            .join(Folder, File.folder_id == Folder.id)
            .where(
                Folder.share_id == folder.share_id,
                (Folder.id == folder.id) | (func.substr(Folder.path, 1, len(prefix)) == prefix),
            )
        ) or 0


def scan_share(db: Session, share: Share, source: Optional[FileSource] = None) -> ScanRun:
    return ShareScanner(db, share, source).scan()
