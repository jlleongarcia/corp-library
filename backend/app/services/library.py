"""
Browsing the shares and opening documents, permission-filtered.

Browsing behaves like a share with access-based enumeration: a user sees the
folders they can list, and the files of a folder only if they can open files
there. Anything they can't see answers "not found", the same as something that
doesn't exist, so the app never confirms what's behind a closed door.

Opening or downloading a file asks the file server again: its live ACL is read
over SMB and checked against the user's groups. That catches a file with
stricter permissions than its folder, and changes since the last scan.
"""

import logging
import posixpath
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..acl.descriptor import parse_security_descriptor
from ..acl.evaluate import can_read
from ..models import Document, File, Folder, Share
from . import plan
from .access import file_access, listable_folder_acl_ids
from .search import file_path
from .sources import FileSource, source_for

logger = logging.getLogger(__name__)

MAX_FILES_LISTED = 1000
CHUNK = 1024 * 1024


class NotFound(Exception):
    """Doesn't exist, or the user may not see it (deliberately indistinguishable)."""


class AccessDenied(Exception):
    """The file server's live ACL refuses the user."""


class CheckUnavailable(Exception):
    """The file server couldn't be asked; fail closed."""


# ── Browse ────────────────────────────────────────────────────────────────────

def browsable_shares(db: Session, token: frozenset[str]) -> list[dict]:
    listable = listable_folder_acl_ids(db, token)
    rows = db.execute(
        select(Share, Folder.id)
        .join(Folder, (Folder.share_id == Share.id) & Folder.parent_id.is_(None))
        .where(Share.enabled, Folder.acl_id.in_(listable))
        .order_by(Share.name)
    ).all()
    return [{"id": s.id, "name": s.name, "path": s.path, "root_folder_id": fid} for s, fid in rows]


def _breadcrumbs(db: Session, folder: Folder, listable: set[int]) -> list[dict]:
    """Ancestors from the share root, each linkable only if the user can list it."""
    parts = folder.path.split("/") if folder.path else []
    prefixes = [""] + ["/".join(parts[: i + 1]) for i in range(len(parts))]
    by_path = {
        f.path: f for f in db.scalars(
            select(Folder).where(Folder.share_id == folder.share_id, Folder.path.in_(prefixes))
        )
    }
    share_name = db.get(Share, folder.share_id).name
    crumbs = []
    for p in prefixes:
        f = by_path.get(p)
        crumbs.append({
            "folder_id": f.id if f is not None and f.acl_id in listable else None,
            "name": posixpath.basename(p) if p else share_name,
        })
    return crumbs


def browse(db: Session, token: frozenset[str], folder_id: int) -> dict:
    listable = set(listable_folder_acl_ids(db, token))
    folder = db.get(Folder, folder_id)
    if folder is None or folder.acl_id not in listable:
        raise NotFound()
    share = db.get(Share, folder.share_id)
    if not share.enabled:
        raise NotFound()

    subfolders = db.scalars(
        select(Folder).where(Folder.parent_id == folder.id, Folder.acl_id.in_(listable))
        .order_by(func.lower(Folder.name))
    ).all()
    access = file_access(db, token)
    files = db.scalars(
        select(File).join(Folder, File.folder_id == Folder.id)
        .where(File.folder_id == folder.id, access.clause())
        .order_by(func.lower(File.name)).limit(MAX_FILES_LISTED + 1)
    ).all()
    # Files with permissions of their own (BUG-023) may be visible where the rest aren't.
    files_hidden = not files and folder.acl_id not in access.folder_acl_ids

    return {
        "folder": {
            "id": folder.id, "name": folder.name or share.name, "share_id": share.id, "share": share.name,
            "path": file_path(share, folder.path, ""),
        },
        "breadcrumbs": _breadcrumbs(db, folder, listable),
        "folders": [{"id": f.id, "name": f.name, "mtime": f.mtime} for f in subfolders],
        "files": [
            {"file_id": f.id, "name": f.name, "extension": f.extension, "size": f.size, "mtime": f.mtime}
            for f in files[:MAX_FILES_LISTED]
        ],
        "files_hidden": files_hidden,  # can list the folder but not open its files
        "files_truncated": len(files) > MAX_FILES_LISTED,
        "plan": _placement(db, share, folder),
    }


def _placement(db: Session, share: Share, folder: Folder) -> Optional[dict]:
    """The folder guide for this folder: its plan entry, or the one it falls under."""
    placed = plan.placement_for_folder(db, share.id, folder.path)
    if placed is None:
        return None
    entry = placed.entry
    return {
        "status": placed.status,
        "entry": plan.entry_dict(entry, share, folder_id=folder.id if placed.status == "planned" else None)
        if entry else None,
    }


# ── Documents ─────────────────────────────────────────────────────────────────

@dataclass
class DocumentRef:
    file: File
    folder: Folder
    share: Share
    document: Optional[Document]

    @property
    def relpath(self) -> str:
        return f"{self.folder.path}/{self.file.name}" if self.folder.path else self.file.name

    @property
    def path(self) -> str:
        return file_path(self.share, self.folder.path, self.file.name)


def get_document(db: Session, token: frozenset[str], file_id: int) -> DocumentRef:
    """The file, if the index says this user can open it."""
    row = db.execute(
        select(File, Folder, Share)
        .join(Folder, File.folder_id == Folder.id)
        .join(Share, File.share_id == Share.id)
        .where(File.id == file_id)
    ).first()
    if row is None:
        raise NotFound()
    file, folder, share = row
    if not share.enabled or not file_access(db, token).can_open(file.acl_id, folder.acl_id):
        raise NotFound()
    return DocumentRef(file, folder, share, db.get(Document, file.id))


def check_live_access(ref: DocumentRef, token: frozenset[str], source: Optional[FileSource] = None) -> FileSource:
    """Ask the file server: may this token read the file right now? Returns the source to read it from."""
    source = source or source_for(ref.share.path)
    try:
        sd = source.get_security_descriptor(ref.relpath, is_dir=False)
    except Exception as exc:  # SMB errors, the file vanished, ...
        logger.warning("Live ACL check failed for %s: %s: %s", ref.path, type(exc).__name__, exc)
        raise CheckUnavailable(str(exc)) from exc
    if sd is None or not can_read(parse_security_descriptor(sd).aces, token):
        raise AccessDenied()
    return source


def open_stream(source: FileSource, relpath: str) -> tuple[Iterator[bytes], Callable[[], None]]:
    """
    Open the file now (so a failure is still an HTTP error, not a cut-off
    download). Returns an iterator over its chunks and a function that closes
    it: the response calls that when it ends, however it ends, because a browser
    that disconnects before the first chunk never runs the iterator (BUG-032).
    """
    stack = ExitStack()
    fh = stack.enter_context(source.open_read(relpath))

    def chunks() -> Iterator[bytes]:
        with stack:
            while chunk := fh.read(CHUNK):
                yield chunk

    return chunks(), stack.close
