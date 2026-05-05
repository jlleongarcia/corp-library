import logging

from sqlalchemy import text

from ..database import SessionLocal

logger = logging.getLogger(__name__)


def update_fts_entry(
    db,
    document_id: int,
    title: str,
    description: str,
    tags: str,
    category_name: str,
) -> None:
    """Insert or replace one document's FTS5 entry."""
    db.execute(text("DELETE FROM documents_fts WHERE rowid = :id"), {"id": document_id})
    db.execute(
        text(
            "INSERT INTO documents_fts(rowid, title, description, tags, category_name)"
            " VALUES (:id, :title, :desc, :tags, :cat)"
        ),
        {
            "id": document_id,
            "title": title,
            "desc": description or "",
            "tags": tags or "",
            "cat": category_name or "",
        },
    )


def rebuild_fts_index() -> None:
    """
    Rebuild the entire FTS5 index from scratch.
    Called after every scan and available as an admin action.
    """
    db = SessionLocal()
    try:
        logger.info("Rebuilding FTS5 index…")
        db.execute(text("DELETE FROM documents_fts"))
        db.execute(text("""
            INSERT INTO documents_fts(rowid, title, description, tags, category_name)
            SELECT d.id,
                   d.title,
                   COALESCE(d.description, ''),
                   COALESCE(d.tags, ''),
                   COALESCE(c.name, '')
            FROM documents d
            LEFT JOIN categories c ON d.category_id = c.id
            WHERE d.is_active = 1
        """))
        db.commit()
        logger.info("FTS5 index rebuilt successfully.")
    except Exception as exc:
        logger.error("FTS rebuild failed: %s", exc)
        db.rollback()
    finally:
        db.close()
