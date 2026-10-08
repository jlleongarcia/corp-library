"""
The `index` job: makes scanned files searchable.

1. Metadata pass (fast, no file reads): every file without a `documents` row
   gets one, searchable by name and path straight away. Files whose content
   can be extracted are marked `pending`.
2. Content pass: pending files are read from the share and their text
   extracted (OCR for scans), until the deadline. The job then hands the worker
   back and queues itself again, so a first run over 2 TB doesn't hold up the
   nightly scans.

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
from .extract import ExtractionError, OcrUnavailable, can_extract, extract
from .sources import FileSource, source_for
from .text import clean_content, fold, words

logger = logging.getLogger(__name__)

BATCH = 500  # metadata rows per insert
CONTENT_BATCH = 20  # files read per transaction

# The search vector. Names and paths are indexed as plain words and also stemmed
# (Spanish + English, so "contratos" matches "contrato"); content is stemmed in
# both languages. Weights rank name matches above path matches above content.
PG_VECTOR = """
    setweight(to_tsvector('simple', :name) || to_tsvector('spanish', :name) || to_tsvector('english', :name), 'A')
    || setweight(to_tsvector('simple', :path) || to_tsvector('spanish', :path), 'B')
    || setweight(to_tsvector('spanish', :content) || to_tsvector('english', :content), 'C')
"""


@dataclass
class IndexStats:
    added: int = 0
    extracted: int = 0
    ocr: int = 0
    empty: int = 0
    failed: int = 0
    pending: int = 0  # still waiting when the job stopped

    def as_dict(self) -> dict:
        return asdict(self)


_PENDING = (Document.status == "pending", Share.enabled)


def _initial_status(extension: str, size: int) -> str:
    if not can_extract(extension):
        return "metadata"
    if size > settings.extract_max_size:
        return "too_large"
    return "pending"


def _vector_params(name: str, share: str, folder_path: str, content: str) -> dict:
    return {"name": words(name), "path": words(f"{share} {folder_path}"), "content": fold(content)}


def _set_vector_sql(db: Session) -> str:
    if db.get_bind().dialect.name == "sqlite":
        # The tests run on SQLite, which has no full-text vectors: keep the folded
        # words and let search fall back to LIKE (see search.py).
        return "(:name || ' ' || :path || ' ' || :content)"
    return PG_VECTOR


def add_missing(db: Session) -> int:
    """Metadata pass: a document row for every file that has none."""
    vector = _set_vector_sql(db)
    insert = text(
        f"INSERT INTO documents (file_id, status, search_vector) VALUES (:file_id, :status, {vector})"
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
            {"file_id": fid, "status": _initial_status(ext, size), **_vector_params(name, share, path, "")}
            for fid, name, ext, size, path, share in rows
        ])
        db.commit()
        added += len(rows)


def _store(db: Session, file_id: int, status: str, content: Optional[str], error: Optional[str],
           name: str, share: str, folder_path: str) -> None:
    db.execute(
        text(
            "UPDATE documents SET status = :status, content = :stored, error = :error, "
            f"extracted_at = :now, search_vector = {_set_vector_sql(db)} WHERE file_id = :file_id"
        ),
        {
            "status": status, "stored": content, "error": error, "now": datetime.now(timezone.utc),
            "file_id": file_id, **_vector_params(name, share, folder_path, content or ""),
        },
    )


def extract_pending(db: Session, stats: IndexStats, deadline: Optional[datetime] = None,
                    sources: Optional[dict[int, FileSource]] = None) -> None:
    """Content pass, until nothing is pending or the deadline passes."""
    sources = dict(sources or {})
    while deadline is None or datetime.now(timezone.utc) < deadline:
        # Every file handled below leaves `pending`, so each round gets new ones.
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
            relpath = f"{folder_path}/{name}" if folder_path else name
            status, content, error = _extract_one(sources, share_id, share_path, relpath, ext, size)
            if status == "error":
                stats.failed += 1
            elif status == "empty":
                stats.empty += 1
            elif status in ("text", "ocr"):
                stats.extracted += 1
                stats.ocr += status == "ocr"
            _store(db, fid, status, content, error, name, share_name, folder_path)
        db.commit()


def _extract_one(sources, share_id, share_path, relpath, ext, size) -> tuple[str, Optional[str], Optional[str]]:
    if size > settings.extract_max_size:
        return "too_large", None, None
    if share_id not in sources:
        sources[share_id] = source_for(share_path)
    try:
        with sources[share_id].open_read(relpath) as fh:
            data = fh.read(settings.extract_max_size + 1)
        result = extract(ext, data)
    except OcrUnavailable as exc:
        return "ocr_unavailable", None, str(exc)[:500]
    except ExtractionError as exc:
        return "error", None, str(exc)[:500]
    except Exception as exc:  # SMB errors, a file that vanished, a library bug on a strange file
        logger.warning("Index: cannot extract %s: %s: %s", relpath, type(exc).__name__, exc)
        return "error", None, f"{type(exc).__name__}: {exc}"[:500]
    content = clean_content(result.text, settings.extract_max_chars)
    if not content:
        return "empty", None, None
    return result.method, content, None


def retry_failed(db: Session) -> int:
    """Queue failed / OCR-less documents again (e.g. after installing Tesseract)."""
    n = db.execute(
        update(Document).where(Document.status.in_(("error", "ocr_unavailable"))).values(status="pending")
    ).rowcount or 0
    db.commit()
    return n


def run_index(db: Session, deadline: Optional[datetime] = None, retry: bool = False,
              sources: Optional[dict[int, FileSource]] = None) -> IndexStats:
    stats = IndexStats()
    if retry:
        retry_failed(db)
    stats.added = add_missing(db)
    extract_pending(db, stats, deadline, sources)
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
