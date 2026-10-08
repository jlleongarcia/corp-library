"""Phase 0 discovery reports: inventory, duplicates, stale files, hygiene, permissions."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, case, exists, func, literal, or_, select
from sqlalchemy.orm import Session, aliased

from ..acl.evaluate import BASELINE_SIDS, INHERIT_ONLY_ACE, access_level, effective_mask
from ..config import settings
from ..models import Acl, AclEntry, File, Folder, GroupMember, Principal, ScanRun, Share
from .access import token_sids

LONG_PATH_LIMIT = 240  # Explorer and many apps fail beyond ~260 characters
DEEP_FOLDER_LIMIT = 8


def _share_filter(stmt, column, share_id: Optional[int]):
    return stmt.where(column == share_id) if share_id else stmt


def display_path(share_path: str, folder_path: str, name: str = "") -> str:
    parts = [share_path.rstrip("\\/")]
    if folder_path:
        parts.append(folder_path.replace("/", "\\"))
    if name:
        parts.append(name)
    return "\\".join(parts)


# ── Inventory ─────────────────────────────────────────────────────────────────

def summary(db: Session) -> list[dict]:
    files = (
        select(File.share_id, func.count(File.id).label("files"), func.coalesce(func.sum(File.size), 0).label("bytes"))
        .group_by(File.share_id).subquery()
    )
    folders = select(Folder.share_id, func.count(Folder.id).label("folders")).group_by(Folder.share_id).subquery()
    run2 = aliased(ScanRun)
    last_run_id = (
        select(func.max(run2.id)).where(run2.share_id == Share.id).correlate(Share).scalar_subquery()
    )
    rows = db.execute(
        select(Share, files.c.files, files.c.bytes, folders.c.folders, ScanRun)
        .outerjoin(files, files.c.share_id == Share.id)
        .outerjoin(folders, folders.c.share_id == Share.id)
        .outerjoin(ScanRun, ScanRun.id == last_run_id)
        .order_by(Share.name)
    ).all()
    return [
        {
            "share_id": s.id, "share": s.name, "path": s.path, "enabled": s.enabled,
            "files": n_files or 0, "bytes": int(n_bytes or 0), "folders": n_folders or 0,
            "last_scan_status": run.status if run else None,
            "last_scan_finished": run.finished_at if run else None,
        }
        for s, n_files, n_bytes, n_folders, run in rows
    ]


def by_extension(db: Session, share_id: Optional[int] = None, limit: int = 30) -> list[dict]:
    stmt = select(File.extension, func.count(File.id), func.coalesce(func.sum(File.size), 0))
    stmt = _share_filter(stmt, File.share_id, share_id)
    stmt = stmt.group_by(File.extension).order_by(func.sum(File.size).desc()).limit(limit)
    return [{"extension": ext or "(none)", "files": n, "bytes": int(b)} for ext, n, b in db.execute(stmt)]


AGE_BUCKETS = [("< 1 year", 1), ("1-3 years", 3), ("3-5 years", 5), ("5-10 years", 10)]


def by_age(db: Session, share_id: Optional[int] = None) -> list[dict]:
    now = datetime.now(timezone.utc)
    whens = [(File.mtime >= now - timedelta(days=365 * years), label) for label, years in AGE_BUCKETS]
    bucket = case((File.mtime.is_(None), literal("unknown")), *whens, else_=literal("> 10 years"))
    stmt = select(bucket.label("bucket"), func.count(File.id), func.coalesce(func.sum(File.size), 0))
    # Group by the label: with server-side parameters PostgreSQL can't tell that
    # two copies of the CASE expression (with distinct placeholders) are identical.
    stmt = _share_filter(stmt, File.share_id, share_id).group_by("bucket")
    found = {b: (n, int(s)) for b, n, s in db.execute(stmt)}
    order = [label for label, _ in AGE_BUCKETS] + ["> 10 years", "unknown"]
    return [{"bucket": b, "files": found.get(b, (0, 0))[0], "bytes": found.get(b, (0, 0))[1]} for b in order]


# ── Duplicates ────────────────────────────────────────────────────────────────

def duplicates(db: Session, limit: int = 50, offset: int = 0) -> dict:
    key = func.coalesce(File.content_hash, File.quick_hash)
    groups_q = (
        select(
            File.size, key.label("key"), func.count(File.id).label("copies"),
            func.max(case((File.content_hash.is_not(None), 1), else_=0)).label("exact"),
        )
        .where(File.quick_hash.is_not(None))
        .group_by(File.size, key)
        .having(func.count(File.id) > 1)
    ).subquery()
    total = db.execute(
        select(func.count(), func.coalesce(func.sum(groups_q.c.size * (groups_q.c.copies - 1)), 0))
    ).one()
    page = db.execute(
        select(groups_q).order_by((groups_q.c.size * (groups_q.c.copies - 1)).desc()).limit(limit).offset(offset)
    ).all()

    out = []
    for size, k, copies, exact in page:
        files = db.execute(
            select(Share.path, Folder.path, File.name, File.mtime)
            .join(Folder, File.folder_id == Folder.id).join(Share, File.share_id == Share.id)
            .where(File.size == size, key == k)
            .order_by(File.mtime)
        ).all()
        out.append({
            "size": size, "copies": copies, "wasted_bytes": size * (copies - 1),
            "confidence": "exact" if exact else "probable",
            "files": [{"path": display_path(sp, fp, n), "mtime": m} for sp, fp, n, m in files],
        })
    return {"total_groups": total[0], "total_wasted_bytes": int(total[1]), "groups": out}


# ── Stale files ───────────────────────────────────────────────────────────────

def stale_folders(db: Session, years: int = 5, share_id: Optional[int] = None, limit: int = 100) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=365 * years)
    stmt = (
        select(Share.path, Folder.path, func.count(File.id), func.sum(File.size), func.max(File.mtime))
        .join(Folder, File.folder_id == Folder.id).join(Share, File.share_id == Share.id)
        .where(File.mtime < cutoff)
    )
    stmt = _share_filter(stmt, File.share_id, share_id)
    stmt = stmt.group_by(Share.path, Folder.path).order_by(func.sum(File.size).desc()).limit(limit)
    return [
        {"folder": display_path(sp, fp), "stale_files": n, "stale_bytes": int(b or 0), "newest_stale": newest}
        for sp, fp, n, b, newest in db.execute(stmt)
    ]


# ── Hygiene ───────────────────────────────────────────────────────────────────

def hygiene(db: Session, share_id: Optional[int] = None, limit: int = 200) -> dict:
    path_len = func.length(Share.path) + 1 + func.length(Folder.path) + 1 + func.length(File.name)
    long_q = (
        select(Share.path, Folder.path, File.name, path_len.label("length"))
        .join(Folder, File.folder_id == Folder.id).join(Share, File.share_id == Share.id)
        .where(path_len > LONG_PATH_LIMIT)
    )
    long_q = _share_filter(long_q, File.share_id, share_id)
    long_count = db.scalar(select(func.count()).select_from(long_q.subquery()))
    long_rows = db.execute(long_q.order_by(path_len.desc()).limit(limit)).all()

    deep_q = select(Share.path, Folder.path, Folder.depth).join(Share, Folder.share_id == Share.id).where(
        Folder.depth > DEEP_FOLDER_LIMIT
    )
    deep_q = _share_filter(deep_q, Folder.share_id, share_id)
    deep_count = db.scalar(select(func.count()).select_from(deep_q.subquery()))
    deep_rows = db.execute(deep_q.order_by(Folder.depth.desc()).limit(limit)).all()

    child = aliased(Folder)
    empty_q = (
        select(Share.path, Folder.path)
        .join(Share, Folder.share_id == Share.id)
        .where(
            Folder.parent_id.is_not(None),
            Folder.list_error.is_(None),  # unknown contents are not "empty"
            ~exists().where(File.folder_id == Folder.id),
            ~exists().where(child.parent_id == Folder.id),
        )
    )
    empty_q = _share_filter(empty_q, Folder.share_id, share_id)
    empty_count = db.scalar(select(func.count()).select_from(empty_q.subquery()))
    empty_rows = db.execute(empty_q.order_by(Folder.path).limit(limit)).all()

    unlisted_q = (
        select(Share.path, Folder.path, Folder.list_error)
        .join(Share, Folder.share_id == Share.id)
        .where(Folder.list_error.is_not(None))
    )
    unlisted_q = _share_filter(unlisted_q, Folder.share_id, share_id)
    unlisted_count = db.scalar(select(func.count()).select_from(unlisted_q.subquery()))
    unlisted_rows = db.execute(unlisted_q.order_by(Folder.path).limit(limit)).all()

    return {
        "long_paths": {"limit": LONG_PATH_LIMIT, "count": long_count, "items": [
            {"path": display_path(sp, fp, n), "length": ln} for sp, fp, n, ln in long_rows]},
        "deep_folders": {"limit": DEEP_FOLDER_LIMIT, "count": deep_count, "items": [
            {"path": display_path(sp, fp), "depth": d} for sp, fp, d in deep_rows]},
        "empty_folders": {"count": empty_count, "items": [
            {"path": display_path(sp, fp)} for sp, fp in empty_rows]},
        "unlisted_folders": {"count": unlisted_count, "items": [
            {"path": display_path(sp, fp), "error": err} for sp, fp, err in unlisted_rows]},
    }


# ── Permissions ───────────────────────────────────────────────────────────────

def _principal_map(db: Session) -> dict[str, Principal]:
    return {p.sid: p for p in db.scalars(select(Principal))}


def _describe(sid: str, principals: dict[str, Principal]) -> dict:
    p = principals.get(sid)
    return {
        "sid": sid,
        "name": (p.name if p and p.name else sid),
        "display_name": (p.display_name if p and p.display_name else None),
        "kind": p.kind if p else "unknown",
    }


def acl_exceptions(db: Session, share_id: Optional[int] = None, limit: int = 500) -> list[dict]:
    """Folders where permissions were set explicitly, inheritance is off, or the ACL is unreadable."""
    principals = _principal_map(db)
    stmt = (
        select(Folder, Share.path, Acl)
        .join(Share, Folder.share_id == Share.id)
        .outerjoin(Acl, Folder.acl_id == Acl.id)
        .where(or_(
            Acl.has_explicit, Acl.is_protected, Acl.is_null_dacl,
            Folder.acl_error.is_not(None),
            and_(Folder.acl_id.is_(None), Folder.parent_id.is_(None)),
        ))
    )
    stmt = _share_filter(stmt, Folder.share_id, share_id).order_by(Share.path, Folder.path).limit(limit)
    out = []
    for folder, share_path, acl in db.execute(stmt):
        entries = []
        if acl:
            for e in acl.entries:
                if e.flags & INHERIT_ONLY_ACE:
                    continue
                entries.append({
                    **_describe(e.sid, principals),
                    "type": e.ace_type, "level": access_level(e.mask),
                    "inherited": bool(e.flags & 0x10),
                })
        out.append({
            "folder_id": folder.id,
            "path": display_path(share_path, folder.path),
            "is_share_root": folder.parent_id is None,
            "inheritance_disabled": bool(acl and acl.is_protected),
            "null_dacl": bool(acl and acl.is_null_dacl),
            "acl_error": folder.acl_error or (None if acl else "No ACL recorded"),
            "entries": entries,
        })
    return out


def permission_grid(db: Session, max_depth: int = 2, max_columns: int = 60) -> dict:
    """
    Users × folders. Columns are share roots plus folders (up to max_depth) whose
    permissions were set explicitly. Each cell is the user's effective access level.
    """
    principals = _principal_map(db)
    col_q = (
        select(Folder, Share.path)
        .join(Share, Folder.share_id == Share.id)
        .join(Acl, Folder.acl_id == Acl.id)
        .where(or_(Folder.parent_id.is_(None), and_(Folder.depth <= max_depth, or_(Acl.has_explicit, Acl.is_protected))))
        .order_by(Share.path, Folder.path)
        .limit(max_columns)
    )
    columns = []
    acl_by_col: dict[int, list[AclEntry]] = {}
    for folder, share_path in db.execute(col_q):
        columns.append({"folder_id": folder.id, "path": display_path(share_path, folder.path)})
        acl_by_col[folder.id] = [e for e in folder.acl.entries if not e.flags & INHERIT_ONLY_ACE]

    # Candidate rows: users named directly in an ACE, users in groups named in an ACE,
    # plus unresolved SIDs (shown as-is so they can be investigated).
    direct = {e.sid for entries in acl_by_col.values() for e in entries}
    group_sids = {s for s in direct if principals.get(s) and principals[s].kind == "group"}
    members: dict[str, set[str]] = defaultdict(set)
    if group_sids:
        for g, m in db.execute(select(GroupMember.group_sid, GroupMember.member_sid).where(
            GroupMember.group_sid.in_(group_sids)
        )):
            members[m].add(g)
    users = {s for s in direct if principals.get(s) and principals[s].kind == "user"} | set(members)
    unknown = {s for s in direct if s not in principals or principals[s].kind == "unknown"}

    rows = []
    # A generic domain user: what "everyone in the domain" can do.
    generic = set(BASELINE_SIDS) | set(settings.extra_baseline_sids) | {s for s in direct if s.endswith("-513")}
    rows.append({
        "sid": None, "name": "All domain users", "display_name": "Everyone with a domain account",
        "kind": "everyone",
        "cells": {c["folder_id"]: access_level(effective_mask(acl_by_col[c["folder_id"]], generic)) for c in columns},
    })
    for sid in sorted(users, key=lambda s: (_describe(s, principals)["display_name"] or _describe(s, principals)["name"]).lower()):
        token = token_sids(db, sid)
        rows.append({
            **_describe(sid, principals),
            "cells": {c["folder_id"]: access_level(effective_mask(acl_by_col[c["folder_id"]], token)) for c in columns},
        })
    for sid in sorted(unknown):
        rows.append({
            **_describe(sid, principals),
            "cells": {c["folder_id"]: access_level(effective_mask(acl_by_col[c["folder_id"]], {sid})) for c in columns},
        })
    return {"columns": columns, "rows": rows}
