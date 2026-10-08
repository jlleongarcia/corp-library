"""
Document search, permission-filtered.

PostgreSQL full-text search over the `documents.search_vector` built by the
indexer: names rank above paths, paths above content. The query is matched
three ways (as typed, Spanish stems, English stems) and any of them counts.
Only files in folders whose ACL lets the user open files are considered.

The test suite runs on SQLite, which has no full-text search: there every
word must appear somewhere in the name, path or content (LIKE).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal, Optional

from sqlalchemy import func, literal, literal_column, select
from sqlalchemy.orm import Session

from ..models import Document, File, Folder, Share
from .access import readable_file_acl_ids
from .reports import display_path
from .text import parse_query, snippet

# File types users filter by. Anything else is "other".
TYPE_GROUPS: dict[str, tuple[str, list[str]]] = {
    "pdf": ("PDF", ["pdf"]),
    "word": ("Word", ["doc", "docx", "docm", "dot", "dotx", "odt", "rtf"]),
    "excel": ("Excel", ["xls", "xlsx", "xlsm", "xlsb", "xltx", "csv", "ods"]),
    "powerpoint": ("PowerPoint", ["ppt", "pptx", "pptm", "pps", "ppsx", "odp"]),
    "text": ("Text", ["txt", "md", "log", "json", "xml", "html", "htm"]),
    "email": ("Email", ["msg", "eml"]),
    "image": ("Images", ["jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "webp", "heic"]),
    "cad": ("CAD", ["dwg", "dxf", "dgn", "step", "stp", "ifc"]),
    "archive": ("Archives", ["zip", "rar", "7z", "tar", "gz"]),
    "media": ("Audio & video", ["mp3", "wav", "m4a", "mp4", "avi", "mov", "mkv", "wmv"]),
}
KNOWN_EXTENSIONS = [e for _, exts in TYPE_GROUPS.values() for e in exts]

Sort = Literal["relevance", "newest", "name"]


@dataclass
class SearchParams:
    q: str = ""
    share_id: Optional[int] = None
    type: Optional[str] = None  # a TYPE_GROUPS key, or "other"
    modified_from: Optional[date] = None
    modified_to: Optional[date] = None
    sort: Sort = "relevance"
    limit: int = 20
    offset: int = 0


def file_path(share: Share, folder_path: str, name: str) -> str:
    """The path people paste into Explorer: \\\\server\\share\\folder\\file."""
    return display_path(share.path, folder_path, name)


def _tsquery(q: str, parse=func.websearch_to_tsquery):
    configs = ("simple", "spanish", "english")
    parts = [parse(literal_column(f"'{c}'::regconfig"), q) for c in configs]
    query = parts[0]
    for p in parts[1:]:
        query = query.op("||")(p)
    return query


def _matches(q: str, parse=func.websearch_to_tsquery):
    # NULL vector (no document row yet) counts as no match.
    return func.coalesce(Document.search_vector.op("@@")(_tsquery(q, parse)), False)


def search(db: Session, token: frozenset[str], p: SearchParams) -> dict:
    readable = readable_file_acl_ids(db, token)
    parsed = parse_query(p.q)
    sqlite = db.get_bind().dialect.name == "sqlite"

    stmt = (
        select(File, Folder.path, Share)
        .join(Folder, File.folder_id == Folder.id)
        .join(Share, File.share_id == Share.id)
        .outerjoin(Document, Document.file_id == File.id)
        .where(Folder.acl_id.in_(readable), Share.enabled)
    )
    rank = literal(0)
    if parsed.terms or parsed.excluded:
        if sqlite:
            # On SQLite the "vector" is the folded words themselves (see indexer.py).
            stmt = stmt.where(
                *[func.instr(Document.search_vector, t) > 0 for t in parsed.terms],
                *[func.coalesce(func.instr(Document.search_vector, t), 0) == 0 for t in parsed.excluded],
            )
        else:
            if parsed.terms:
                tsq = _tsquery(parsed.text)
                stmt = stmt.where(Document.search_vector.op("@@")(tsq))
                rank = func.ts_rank_cd(Document.search_vector, tsq)
            # Each exclusion is matched as typed and stemmed in both languages, and
            # any match rejects the document. (Left inside the OR-ed query above, a
            # stemming that didn't notice the word would let the document through.)
            stmt = stmt.where(*[~_matches(e, func.phraseto_tsquery) for e in parsed.excluded])

    if p.share_id:
        stmt = stmt.where(File.share_id == p.share_id)
    if p.type == "other":
        stmt = stmt.where(File.extension.not_in(KNOWN_EXTENSIONS))
    elif p.type in TYPE_GROUPS:
        stmt = stmt.where(File.extension.in_(TYPE_GROUPS[p.type][1]))
    if p.modified_from:
        stmt = stmt.where(File.mtime >= datetime.combine(p.modified_from, time.min, timezone.utc))
    if p.modified_to:
        stmt = stmt.where(File.mtime < datetime.combine(p.modified_to + timedelta(days=1), time.min, timezone.utc))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    newest = (File.mtime.desc().nulls_last(), File.id)
    if p.sort == "name":
        order = (func.lower(File.name), File.id)
    elif p.sort == "newest" or not parsed.terms:
        order = newest
    else:
        order = (rank.desc(), *newest)
    rows = db.execute(stmt.add_columns(rank).order_by(*order).limit(p.limit).offset(p.offset)).all()

    contents = dict(db.execute(
        select(Document.file_id, Document.content).where(Document.file_id.in_([f.id for f, *_ in rows]))
    ).all()) if rows and parsed.terms else {}

    return {
        "total": total,
        "results": [
            {
                "file_id": f.id,
                "name": f.name,
                "extension": f.extension,
                "size": f.size,
                "mtime": f.mtime,
                "share_id": share.id,
                "share": share.name,
                "folder_id": f.folder_id,
                "folder_path": folder_path,
                "path": file_path(share, folder_path, f.name),
                "snippet": snippet(contents.get(f.id) or "", parsed.terms),
            }
            for f, folder_path, share, _rank in rows
        ],
    }


def file_types() -> list[dict]:
    return [{"key": k, "label": label} for k, (label, _) in TYPE_GROUPS.items()] + [{"key": "other", "label": "Other"}]


def visible_shares(db: Session, token: frozenset[str]) -> list[Share]:
    """Shares with at least one folder whose files this user can open (for the share filter)."""
    readable = readable_file_acl_ids(db, token)
    return list(db.scalars(
        select(Share).where(
            Share.enabled,
            select(Folder.id).where(Folder.share_id == Share.id, Folder.acl_id.in_(readable)).exists(),
        ).order_by(Share.name)
    ))

