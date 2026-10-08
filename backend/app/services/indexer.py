"""
The `index` job: makes scanned files searchable.

1. Metadata pass (fast, no file reads): every file without a `documents` row
   gets one, searchable by name and path straight away. Files whose content
   can be extracted are marked `pending`.
2. Content pass: pending files are read from the share and their text
   extracted (OCR for scans), one file per transaction, until the deadline. The
   job then hands the worker back and queues itself again, so a first run over
   2 TB doesn't hold up the nightly scans.

Reading a file's content also reads its own permissions (BUG-023): a file
stricter than its folder must not show its text to everyone in the folder.

A file is marked `extracting` before it is read. If it takes the worker down
(out of memory, a crash outside the extractor process), the next run marks it
`error` instead of reading it again forever (BUG-024).

The scanner sets a changed file back to `pending`; deleted files take their
document with them (foreign key cascade).
"""

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Document, File, Folder, Share
from .extract import ExtractionError, OcrUnavailable, can_extract, initial_status
from .extract_process import Extractor, make_extractor
from .scanner import AclStore
from .sources import FileSource, source_for
from .text import clean_content, fold, words

logger = logging.getLogger(__name__)

BATCH = 500  # metadata rows per insert
CONTENT_BATCH = 20  # pending files fetched per query (each is committed on its own)
INTERRUPTED = 'The worker stopped while reading this file (crash, out of memory or restart). "Retry failed" reads it again.'

# The search vector. Names and paths are indexed as plain words and also stemmed
# (Spanish + English, so "contratos" matches "contrato"); content is stemmed in
# both languages. Weights rank name matches above path matches above content.
# Weight B is the path and nothing else: a renamed share replaces just that part.
# The name + path part is also kept on its own (title_vector), small enough to
# search when a common word matches too many documents to rank them all (BUG-027).
PG_PATH_VECTOR = "setweight(to_tsvector('simple', :path) || to_tsvector('spanish', :path), 'B')"
PG_TITLE_VECTOR = f"""
    setweight(to_tsvector('simple', :name) || to_tsvector('spanish', :name) || to_tsvector('english', :name), 'A')
    || {PG_PATH_VECTOR}
"""
PG_VECTOR = f"""{PG_TITLE_VECTOR}
    || setweight(to_tsvector('spanish', :content) || to_tsvector('english', :content), 'C')
"""


@dataclass
class IndexStats:
    added: int = 0
    extracted: int = 0
    ocr: int = 0
    empty: int = 0
    failed: int = 0
    interrupted: int = 0  # left `extracting` by a worker that died: marked failed
    pending: int = 0  # still waiting when the job stopped

    def as_dict(self) -> dict:
        return asdict(self)


_PENDING = (Document.status == "pending", Share.enabled)


def _vector_params(name: str, share: str, folder_path: str, content: str) -> dict:
    return {"name": words(name), "path": words(f"{share} {folder_path}"), "content": fold(content)}


def _sqlite(db: Session) -> bool:
    return db.get_bind().dialect.name == "sqlite"


def _set_vector_sql(db: Session) -> str:
    if _sqlite(db):
        # The tests run on SQLite, which has no full-text vectors: keep the folded
        # words and let search fall back to LIKE (see search.py).
        return "(:name || ' ' || :path || ' ' || :content)"
    return PG_VECTOR


def _title_vector_sql(db: Session) -> str:
    return "(:name || ' ' || :path)" if _sqlite(db) else PG_TITLE_VECTOR


def add_missing(db: Session) -> int:
    """Metadata pass: a document row for every file that has none."""
    vector = _set_vector_sql(db)
    insert = text(
        "INSERT INTO documents (file_id, status, search_vector, title_vector) "
        f"VALUES (:file_id, :status, {vector}, {_title_vector_sql(db)})"
    )
    added = 0
    while True:
        rows = db.execute(
            select(File.id, File.name, File.extension, File.size, Folder.path, Share.name)
            .join(Folder, File.folder_id == Folder.id)
            .join(Share, File.share_id == Share.id)
            .outerjoin(Document, Document.file_id == File.id)
            .where(Document.file_id.is_(None))
            .order_by(File.id)
            .limit(BATCH)
        ).all()
        if not rows:
            return added
        db.execute(insert, [
            {"file_id": fid, "status": initial_status(ext, size), **_vector_params(name, share, path, "")}
            for fid, name, ext, size, path, share in rows
        ])
        db.commit()
        added += len(rows)


@dataclass
class _Result:
    status: str
    content: Optional[str] = None
    error: Optional[str] = None
    acl_read: bool = False  # the file's own permissions were read (acl_id is current)
    acl_id: Optional[int] = None


def _store(db: Session, file_id: int, r: _Result, name: str, share: str, folder_path: str) -> None:
    db.execute(
        text(
            "UPDATE documents SET status = :status, content = :stored, error = :error, extracted_at = :now, "
            f"search_vector = {_set_vector_sql(db)}, title_vector = {_title_vector_sql(db)} WHERE file_id = :file_id"
        ),
        {
            "status": r.status, "stored": r.content, "error": r.error, "now": datetime.now(timezone.utc),
            "file_id": file_id, **_vector_params(name, share, folder_path, r.content or ""),
        },
    )
    if r.acl_read:
        # Only when actually read: a failed read keeps the last known (possibly stricter) ACL.
        db.execute(update(File).where(File.id == file_id).values(acl_id=r.acl_id))


def mark_interrupted(db: Session) -> int:
    """Files a dead worker left `extracting` fail instead of being read again (BUG-024)."""
    n = db.execute(
        update(Document).where(Document.status == "extracting").values(status="error", error=INTERRUPTED)
    ).rowcount or 0
    db.commit()
    if n:
        logger.warning("Index: %d file(s) were being read when the worker stopped; marked as failed.", n)
    return n


def _deadline_passed(deadline: Optional[datetime]) -> bool:
    return deadline is not None and datetime.now(timezone.utc) >= deadline


def extract_pending(db: Session, stats: IndexStats, deadline: Optional[datetime] = None,
                    sources: Optional[dict[int, FileSource]] = None,
                    extractor: Optional[Extractor] = None) -> None:
    """Content pass, until nothing is pending or the deadline passes (checked after every file: BUG-026)."""
    sources = dict(sources or {})
    acls = AclStore(db)
    own_extractor = extractor is None
    extractor = extractor or make_extractor()
    try:
        while not _deadline_passed(deadline):
            batch = db.execute(
                select(File.id, File.name, File.extension, File.size, File.share_id, Folder.path, Share.name, Share.path)
                .join(Document, Document.file_id == File.id)
                .join(Folder, File.folder_id == Folder.id)
                .join(Share, File.share_id == Share.id)
                .where(*_PENDING)
                .order_by(File.id)
                .limit(CONTENT_BATCH)
            ).all()
            if not batch:
                break
            for fid, name, ext, size, share_id, folder_path, share_name, share_path in batch:
                # Committed before reading: if this file takes the worker down, it isn't read again.
                db.execute(update(Document).where(Document.file_id == fid).values(status="extracting"))
                db.commit()
                if share_id not in sources:
                    sources[share_id] = source_for(share_path)
                relpath = f"{folder_path}/{name}" if folder_path else name
                result = _extract_one(sources[share_id], acls, extractor, relpath, ext, size)
                if result.status == "error":
                    stats.failed += 1
                elif result.status == "empty":
                    stats.empty += 1
                elif result.status in ("text", "ocr"):
                    stats.extracted += 1
                    stats.ocr += result.status == "ocr"
                _store(db, fid, result, name, share_name, folder_path)
                db.commit()
                if _deadline_passed(deadline):
                    return
    finally:
        if own_extractor:
            extractor.close()


def _extract_one(source: FileSource, acls: AclStore, extractor: Extractor,
                 relpath: str, ext: str, size: int) -> _Result:
    if not can_extract(ext):  # never read a file only its name is indexed for (BUG-025)
        return _Result("metadata")
    if size > settings.extract_max_size:
        return _Result("too_large")
    result = _Result("error")
    try:
        # Permissions first: if they can't be read, the text isn't stored (fail closed).
        sd = source.get_security_descriptor(relpath, is_dir=False)
        result.acl_id = acls.file_acl_id(sd) if sd is not None else None
        result.acl_read = True
        with source.open_read(relpath) as fh:
            data = fh.read(settings.extract_max_size + 1)
        extracted = extractor.extract(ext, data)
    except OcrUnavailable as exc:
        result.status, result.error = "ocr_unavailable", str(exc)[:500]
        return result
    except ExtractionError as exc:
        result.error = str(exc)[:500]
        return result
    except Exception as exc:  # SMB errors, a file that vanished, a corrupt security descriptor
        logger.warning("Index: cannot extract %s: %s: %s", relpath, type(exc).__name__, exc)
        result.error = f"{type(exc).__name__}: {exc}"[:500]
        return result
    content = clean_content(extracted.text, settings.extract_max_chars)
    if not content:
        result.status = "empty"
        return result
    result.status, result.content = extracted.method, content
    return result


def retry_failed(db: Session) -> int:
    """Queue failed / OCR-less documents again (e.g. after installing Tesseract)."""
    n = db.execute(
        update(Document).where(Document.status.in_(("error", "ocr_unavailable"))).values(status="pending")
    ).rowcount or 0
    db.commit()
    return n


def rebuild_share_paths(db: Session, share_id: int) -> int:
    """
    After a share is renamed: put the new name in its documents' search vectors
    (BUG-030). On PostgreSQL only the path part (weight B) is replaced, so the
    text isn't tokenised again; folder by folder, since the path differs per folder.
    """
    share = db.get(Share, share_id)
    if share is None:
        return 0
    updated = 0
    for folder_id, folder_path in db.execute(select(Folder.id, Folder.path).where(Folder.share_id == share_id)):
        if _sqlite(db):
            rows = db.execute(
                select(File.id, File.name, Document.content).join(Document, Document.file_id == File.id)
                .where(File.folder_id == folder_id)
            ).all()
            for fid, name, content in rows:
                db.execute(text(f"UPDATE documents SET search_vector = {_set_vector_sql(db)}, "
                                f"title_vector = {_title_vector_sql(db)} WHERE file_id = :fid"),
                           {"fid": fid, **_vector_params(name, share.name, folder_path, content or "")})
            updated += len(rows)
        else:
            updated += db.execute(
                text(f"UPDATE documents SET search_vector = ts_filter(search_vector, '{{a,c}}') || {PG_PATH_VECTOR}, "
                     f"title_vector = ts_filter(title_vector, '{{a}}') || {PG_PATH_VECTOR} "
                     "WHERE file_id IN (SELECT id FROM files WHERE folder_id = :folder_id)"),
                {"folder_id": folder_id, "path": words(f"{share.name} {folder_path}")},
            ).rowcount or 0
        db.commit()
    logger.info("Index: search vectors of share '%s' updated with its new name (%d documents).", share.name, updated)
    return updated


def run_index(db: Session, deadline: Optional[datetime] = None, retry: bool = False,
              sources: Optional[dict[int, FileSource]] = None,
              extractor: Optional[Extractor] = None, rebuild_share: Optional[int] = None) -> IndexStats:
    stats = IndexStats()
    stats.interrupted = mark_interrupted(db)
    if rebuild_share is not None:
        rebuild_share_paths(db, rebuild_share)
    if retry:
        retry_failed(db)
    stats.added = add_missing(db)
    extract_pending(db, stats, deadline, sources, extractor)
    # Same filter as the content pass: files of a disabled share wait without
    # keeping the job alive.
    stats.pending = db.scalar(
        select(func.count()).select_from(Document)
        .join(File, Document.file_id == File.id).join(Share, File.share_id == Share.id)
        .where(*_PENDING)
    ) or 0
    logger.info("Index: %s", stats.as_dict())
    return stats


def status_counts(db: Session) -> dict[str, int]:
    """Documents per extraction status, plus files not processed yet."""
    counts = dict(db.execute(select(Document.status, func.count()).group_by(Document.status)).all())
    total_files = db.scalar(select(func.count()).select_from(File)) or 0
    counts["not_indexed"] = max(0, total_files - sum(counts.values()))
    return counts
