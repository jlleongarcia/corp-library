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

from sqlalchemy import func, literal, literal_column, select, union
from sqlalchemy.orm import Session

from ..models import Document, File, Folder, Share
from .access import file_access
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
# Counting and ranking read every match's vector, which for a common word in a
# 2 TB index takes seconds (BUG-027, scripts/bench_search.py). So matches are
# counted up to COUNT_CAP (the UI says "1,000+" and shows at most 50 pages of
# 20), and when there are more, relevance ranks only the likeliest: the
# COUNT_CAP newest whose name or folder matches, plus the COUNT_CAP newest
# matching anywhere. Up to COUNT_CAP matches, every one is ranked.
COUNT_CAP = 1_000


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
    count: bool = True  # the home page's "recently modified" list shows no total


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


def _rank_candidates(stmt, tsq, newest):
    """Too many matches to rank them all: narrow them to the likeliest ones (BUG-027)."""
    ids = stmt.with_only_columns(File.id)
    by_name = ids.where(Document.title_vector.op("@@")(tsq)).order_by(*newest).limit(COUNT_CAP)
    recent = ids.order_by(*newest).limit(COUNT_CAP)
    candidates = union(by_name, recent).subquery()
    return stmt.where(File.id.in_(select(candidates.c.id)))


def search(db: Session, token: frozenset[str], p: SearchParams) -> dict:
    access = file_access(db, token)
    parsed = parse_query(p.q)
    sqlite = db.get_bind().dialect.name == "sqlite"

    stmt = (
        select(File, Folder.path, Share)
        .join(Folder, File.folder_id == Folder.id)
        .join(Share, File.share_id == Share.id)
        .outerjoin(Document, Document.file_id == File.id)
        .where(access.clause(), Share.enabled)
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
                if p.sort == "relevance":
                    # Only when it orders the results: it reads every match's whole vector.
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

    ranked = p.sort == "relevance" and parsed.terms and not sqlite
    found = None
    if p.count or ranked:
        found = db.scalar(select(func.count()).select_from(stmt.with_only_columns(File.id).limit(COUNT_CAP + 1).subquery())) or 0

    newest = (File.mtime.desc().nulls_last(), File.id)
    if ranked and found > COUNT_CAP:
        stmt = _rank_candidates(stmt, tsq, newest)
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
        "total": min(found, COUNT_CAP) if p.count else None,
        "total_capped": bool(p.count and found > COUNT_CAP),
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
    """Shares with at least one file this user can open (for the share filter)."""
    access = file_access(db, token)
    folder_level = select(Folder.id).where(
        Folder.share_id == Share.id, Folder.acl_id.in_(access.folder_acl_ids)
    ).exists()
    return list(db.scalars(
        select(Share).where(Share.enabled, folder_level | Share.id.in_(access.file_pair_shares))
        .order_by(Share.name)
    ))

