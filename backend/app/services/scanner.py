"""
Folder scanner service.

Walks a configured root path, creates Category entries for sub-folders,
and upserts Document entries for each file.  Permissions (AD groups) are
inherited from the ScanConfig that owns the path.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..database import SessionLocal
from ..models import Category, Document, DocumentPermission, ScanConfig
from .indexer import rebuild_fts_index

logger = logging.getLogger(__name__)

# Extensions to silently skip
_IGNORED = {".tmp", ".lnk", ".ini", ".sys", ".dll", ".db", ".log"}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_or_create_category(
    db, name: str, parent_id: Optional[int], path: str
) -> Category:
    cat = (
        db.query(Category)
        .filter(
            Category.name == name,
            Category.parent_id == parent_id,
            Category.auto_generated == True,  # noqa: E712
        )
        .first()
    )
    if not cat:
        cat = Category(name=name, parent_id=parent_id, path=path, auto_generated=True)
        db.add(cat)
        db.flush()
    return cat


def _upsert_document(
    db,
    file_path: str,
    title: str,
    category_id: Optional[int],
    config: ScanConfig,
    stat: os.stat_result,
) -> Document:
    allowed_groups: list[str] = json.loads(config.allowed_groups or "[]")
    last_modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    p = Path(file_path)

    doc = db.query(Document).filter(Document.file_path == file_path).first()
    if doc:
        doc.title = title
        doc.file_name = p.name
        doc.file_extension = p.suffix.lower().lstrip(".")
        doc.file_size = stat.st_size
        doc.category_id = category_id
        doc.last_modified = last_modified
        doc.is_active = True
        doc.scan_config_id = config.id
        db.query(DocumentPermission).filter(DocumentPermission.document_id == doc.id).delete()
    else:
        doc = Document(
            title=title,
            file_path=file_path,
            file_name=p.name,
            file_extension=p.suffix.lower().lstrip("."),
            file_size=stat.st_size,
            category_id=category_id,
            last_modified=last_modified,
            scan_config_id=config.id,
        )
        db.add(doc)
        db.flush()

    for group in allowed_groups:
        db.add(DocumentPermission(document_id=doc.id, ad_group=group))

    return doc


# ── Public entry point ────────────────────────────────────────────────────────

def run_scan(config_id: int) -> None:
    """
    Execute a full scan for the given ScanConfig id.
    Designed to run as a FastAPI BackgroundTask.
    """
    db = SessionLocal()
    try:
        config = db.query(ScanConfig).filter(ScanConfig.id == config_id).first()
        if not config:
            logger.error("run_scan: ScanConfig %s not found.", config_id)
            return

        logger.info("Scan started: '%s' → %s", config.name, config.root_path)
        config.scan_status = "running"
        config.last_scan = datetime.now(timezone.utc)
        config.scan_error = None
        db.commit()

        allowed_exts: Optional[set[str]] = (
            set(json.loads(config.file_extensions)) if config.file_extensions else None
        )

        root = Path(config.root_path)
        if not root.exists():
            raise FileNotFoundError(f"Root path does not exist: {config.root_path}")

        # Pre-mark all documents from this config as inactive; reactivate on encounter
        db.query(Document).filter(Document.scan_config_id == config_id).update(
            {"is_active": False}
        )
        db.flush()

        category_cache: dict[str, Optional[int]] = {}
        docs_found = 0

        def _category_for_folder(folder: Path) -> Optional[int]:
            key = str(folder)
            if key in category_cache:
                return category_cache[key]
            if not config.create_subcategories:
                return config.root_category_id
            parts = folder.relative_to(root).parts
            parent_id = config.root_category_id
            crumb = ""
            for part in parts:
                crumb += f"/{part}"
                cat = _get_or_create_category(db, part, parent_id, crumb)
                parent_id = cat.id
            category_cache[key] = parent_id
            return parent_id

        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).relative_to(root).parts)
            if depth >= config.max_depth:
                dirnames.clear()
                continue

            folder = Path(dirpath)
            cat_id = _category_for_folder(folder)

            for filename in filenames:
                filepath = folder / filename
                ext = filepath.suffix.lower()
                if ext in _IGNORED:
                    continue
                if allowed_exts and ext.lstrip(".") not in allowed_exts:
                    continue
                try:
                    stat = filepath.stat()
                    title = filepath.stem.replace("_", " ").replace("-", " ").title()
                    _upsert_document(db, str(filepath), title, cat_id, config, stat)
                    docs_found += 1
                except (PermissionError, OSError) as exc:
                    logger.warning("Skipping inaccessible file %s: %s", filepath, exc)

        db.commit()
        config.scan_status = "success"
        config.documents_found = docs_found
        db.commit()
        logger.info("Scan completed: %d documents indexed.", docs_found)

        rebuild_fts_index()

    except Exception as exc:
        logger.error("Scan failed for config %s: %s", config_id, exc)
        try:
            cfg = db.query(ScanConfig).filter(ScanConfig.id == config_id).first()
            if cfg:
                cfg.scan_status = "error"
                cfg.scan_error = str(exc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
