import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..auth.jwt import CurrentUser, get_current_user
from ..database import get_db
from ..models import Category
from ..schemas import SearchResponse, SearchResult

router = APIRouter(prefix="/search", tags=["search"])
logger = logging.getLogger(__name__)


def _sanitize_fts(q: str) -> str:
    """
    Convert a user query into a safe FTS5 MATCH expression.
    Adds prefix-matching on the last token so partial words work.
    """
    # Strip FTS5 special characters to prevent injection into the query syntax
    safe = q.replace('"', "").replace("*", "").replace("(", "").replace(")", "").strip()
    if not safe:
        return '""'
    tokens = safe.split()
    # Prefix-match the last token for autocomplete-style behaviour
    tokens[-1] = tokens[-1] + "*"
    return " ".join(f'"{t}"' if len(t) == 1 else t for t in tokens)


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=200),
    category_id: Optional[int] = None,
    file_type: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    fts_query = _sanitize_fts(q)
    offset = (page - 1) * page_size
    params: dict = {"fts_query": fts_query, "limit": page_size, "offset": offset}

    # --- Permission filter ---
    if current_user.is_admin:
        perm_clause = ""
    elif not current_user.groups:
        perm_clause = "AND NOT EXISTS (SELECT 1 FROM document_permissions dp WHERE dp.document_id = d.id)"
    else:
        placeholders = ", ".join(f":grp{i}" for i in range(len(current_user.groups)))
        perm_clause = f"""
            AND (
                NOT EXISTS (SELECT 1 FROM document_permissions dp WHERE dp.document_id = d.id)
                OR EXISTS (
                    SELECT 1 FROM document_permissions dp
                    WHERE dp.document_id = d.id AND dp.ad_group IN ({placeholders})
                )
            )
        """
        for i, g in enumerate(current_user.groups):
            params[f"grp{i}"] = g

    # --- Optional extra filters ---
    extra = ""
    if category_id is not None:
        extra += " AND d.category_id = :category_id"
        params["category_id"] = category_id
    if file_type:
        extra += " AND d.file_extension = :file_type"
        params["file_type"] = file_type.lower().lstrip(".")

    base_where = f"""
        FROM documents_fts
        JOIN documents d ON documents_fts.rowid = d.id
        WHERE documents_fts MATCH :fts_query
          AND d.is_active = 1
          {perm_clause}
          {extra}
    """

    select_sql = text(f"""
        SELECT
            d.id, d.title, d.description, d.file_path, d.file_name,
            d.file_extension, d.category_id, d.tags, d.last_modified, d.indexed_at,
            snippet(documents_fts, 0, '<mark>', '</mark>', '...', 15) AS hl_title,
            snippet(documents_fts, 1, '<mark>', '</mark>', '...', 40) AS hl_desc,
            bm25(documents_fts) AS rank
        {base_where}
        ORDER BY bm25(documents_fts)
        LIMIT :limit OFFSET :offset
    """)

    count_sql = text(f"SELECT COUNT(*) {base_where}")
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}

    try:
        rows = db.execute(select_sql, params).fetchall()
        total = db.execute(count_sql, count_params).scalar() or 0
    except Exception as exc:
        logger.error("FTS search error: %s", exc)
        rows, total = [], 0

    # Fetch category names in one query
    cat_ids = {r.category_id for r in rows if r.category_id}
    cat_names: dict[int, str] = {}
    if cat_ids:
        cats = db.query(Category).filter(Category.id.in_(cat_ids)).all()
        cat_names = {c.id: c.name for c in cats}

    results = [
        SearchResult(
            id=row.id,
            title=row.title,
            description=row.description,
            file_path=row.file_path,
            file_name=row.file_name,
            file_extension=row.file_extension,
            category_id=row.category_id,
            category_name=cat_names.get(row.category_id),
            tags=[t.strip() for t in (row.tags or "").split(",") if t.strip()],
            last_modified=row.last_modified,
            indexed_at=row.indexed_at,
            highlight_title=row.hl_title or row.title,
            highlight_description=row.hl_desc or row.description,
        )
        for row in rows
    ]

    return SearchResponse(query=q, total=total, results=results, page=page, page_size=page_size)
