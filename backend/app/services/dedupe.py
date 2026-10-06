"""
Duplicate detection without reading 2 TB.

1. Only files whose size matches at least one other file can be duplicates.
2. For those, a quick hash (size + first and last 64 KiB) narrows candidates.
3. Files that still collide get a full SHA-256, up to a size limit. Above the
   limit, matching quick hashes are reported as "probable" duplicates.

Hashes are cleared by the scanner when a file's size or mtime changes, so each
run only reads new or modified candidates.
"""

import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import File, Folder, Share
from .sources import FileSource, source_for

logger = logging.getLogger(__name__)

CHUNK = 64 * 1024


@dataclass
class DedupeStats:
    quick_hashed: int = 0
    full_hashed: int = 0
    errors: int = 0


def _relpath(folder_path: str, name: str) -> str:
    return f"{folder_path}/{name}" if folder_path else name


def quick_hash(f, size: int) -> str:
    h = hashlib.sha256(str(size).encode())
    h.update(f.read(CHUNK))
    if size > 2 * CHUNK:
        f.seek(size - CHUNK)
        h.update(f.read(CHUNK))
    elif size > CHUNK:
        h.update(f.read())
    return h.hexdigest()


def full_hash(f) -> str:
    h = hashlib.sha256()
    while chunk := f.read(1024 * 1024):
        h.update(chunk)
    return h.hexdigest()


def run_dedupe(db: Session, sources: dict[int, FileSource] | None = None) -> DedupeStats:
    stats = DedupeStats()
    sources = dict(sources or {})

    def source(share_id: int) -> FileSource:
        if share_id not in sources:
            sources[share_id] = source_for(db.get(Share, share_id).path)
        return sources[share_id]

    def hash_files(rows, full: bool) -> None:
        for file_id, share_id, folder_path, name, size in rows:
            rel = _relpath(folder_path, name)
            try:
                with source(share_id).open_read(rel) as fh:
                    value = full_hash(fh) if full else quick_hash(fh, size)
            except Exception as exc:
                stats.errors += 1
                logger.warning("Dedupe: cannot read %s: %s", rel, exc)
                continue
            row = db.get(File, file_id)
            if full:
                row.content_hash = value
                stats.full_hashed += 1
            else:
                row.quick_hash = value
                stats.quick_hashed += 1
            if (stats.quick_hashed + stats.full_hashed) % 200 == 0:
                db.commit()
        db.commit()

    # Stage 1+2: quick-hash every file whose size is shared with another file.
    dup_sizes = (
        select(File.size)
        .where(File.size >= settings.dedupe_min_size)
        .group_by(File.size)
        .having(func.count(File.id) > 1)
    )
    need_quick = db.execute(
        select(File.id, File.share_id, Folder.path, File.name, File.size)
        .join(Folder, File.folder_id == Folder.id)
        .where(File.size.in_(dup_sizes), File.quick_hash.is_(None))
        .order_by(File.size.desc())
    ).all()
    hash_files(need_quick, full=False)

    # Stage 3: full hash where (size, quick_hash) still collides.
    colliding = (
        select(File.size, File.quick_hash)
        .where(File.quick_hash.is_not(None))
        .group_by(File.size, File.quick_hash)
        .having(func.count(File.id) > 1)
        .subquery()
    )
    need_full = db.execute(
        select(File.id, File.share_id, Folder.path, File.name, File.size)
        .join(Folder, File.folder_id == Folder.id)
        .join(colliding, (File.size == colliding.c.size) & (File.quick_hash == colliding.c.quick_hash))
        .where(File.content_hash.is_(None), File.size <= settings.dedupe_full_hash_max_size)
    ).all()
    hash_files(need_full, full=True)

    logger.info("Dedupe finished: %s", stats)
    return stats
