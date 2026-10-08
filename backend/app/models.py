from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(200))
    sid: Mapped[Optional[str]] = mapped_column(String(184), index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Share(Base):
    """A top-level department share on the file server (or a local folder in dev)."""

    __tablename__ = "shares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    path: Mapped[str] = mapped_column(String(1024))  # \\server\share or a local path
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    share_id: Mapped[int] = mapped_column(ForeignKey("shares.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|success|partial|failed
    folders_seen: Mapped[int] = mapped_column(Integer, default=0)
    # Junctions, symlinks and DFS links: not followed (could loop or leave the share).
    folders_skipped: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    files_seen: Mapped[int] = mapped_column(Integer, default=0)
    files_added: Mapped[int] = mapped_column(Integer, default=0)
    files_updated: Mapped[int] = mapped_column(Integer, default=0)
    files_removed: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    error_sample: Mapped[Optional[str]] = mapped_column(Text)  # first few errors, for the admin UI


class Acl(Base):
    """A distinct DACL. Folders with identical permissions share one row."""

    __tablename__ = "acls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    is_protected: Mapped[bool] = mapped_column(Boolean, default=False)
    is_null_dacl: Mapped[bool] = mapped_column(Boolean, default=False)
    has_explicit: Mapped[bool] = mapped_column(Boolean, default=False)

    entries: Mapped[list["AclEntry"]] = relationship(
        back_populates="acl", order_by="AclEntry.position", cascade="all, delete-orphan"
    )


class AclEntry(Base):
    __tablename__ = "acl_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    acl_id: Mapped[int] = mapped_column(ForeignKey("acls.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    sid: Mapped[str] = mapped_column(String(184), index=True)
    ace_type: Mapped[str] = mapped_column(String(5))  # allow | deny
    mask: Mapped[int] = mapped_column(BigInteger)
    flags: Mapped[int] = mapped_column(Integer)

    acl: Mapped[Acl] = relationship(back_populates="entries")


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint("parent_id", "name", name="uq_folders_parent_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    share_id: Mapped[int] = mapped_column(ForeignKey("shares.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))  # "" for a share root
    path: Mapped[str] = mapped_column(Text)  # relative to the share, "/"-separated, "" for root
    depth: Mapped[int] = mapped_column(Integer, default=0)
    acl_id: Mapped[Optional[int]] = mapped_column(ForeignKey("acls.id"), index=True)
    owner_sid: Mapped[Optional[str]] = mapped_column(String(184))
    mtime: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acl_error: Mapped[Optional[str]] = mapped_column(String(500))
    # Set while the folder can't be listed: its contents are unknown, not empty.
    list_error: Mapped[Optional[str]] = mapped_column(String(500))

    acl: Mapped[Optional[Acl]] = relationship()


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("folder_id", "name", name="uq_files_folder_name"),
        Index("ix_files_size_hash", "size", "quick_hash"),
        # Few files have their own permissions; every permission check lists them.
        Index("ix_files_acl_id", "acl_id", postgresql_where=text("acl_id IS NOT NULL"),
              sqlite_where=text("acl_id IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    share_id: Mapped[int] = mapped_column(ForeignKey("shares.id", ondelete="CASCADE"), index=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    extension: Mapped[str] = mapped_column(String(32), default="", index=True)
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    mtime: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    ctime: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Duplicate detection. Cleared by the scanner whenever size or mtime change.
    quick_hash: Mapped[Optional[str]] = mapped_column(String(64))
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # The file's own permissions, when it has explicit ACEs or blocks inheritance
    # (BUG-023): its explicit ACEs only, plus `is_protected`; the folder's inheritable
    # ACEs still apply unless protected. Read when the content is extracted; NULL = the
    # file only inherits (or hasn't been read yet), so its folder decides.
    acl_id: Mapped[Optional[int]] = mapped_column(ForeignKey("acls.id"))

    folder: Mapped[Folder] = relationship()


class Principal(Base):
    """A user, group or well-known identity referenced by an ACL, resolved via LDAP."""

    __tablename__ = "principals"

    sid: Mapped[str] = mapped_column(String(184), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(300))  # DOMAIN\sam or well-known name
    display_name: Mapped[Optional[str]] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20), default="unknown")  # user|group|computer|wellknown|unknown
    dn: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class GroupMember(Base):
    """Transitive user membership of groups that appear in ACLs."""

    __tablename__ = "group_members"

    group_sid: Mapped[str] = mapped_column(String(184), primary_key=True)
    member_sid: Mapped[str] = mapped_column(String(184), primary_key=True, index=True)


class Job(Base):
    """Background work for the worker, claimed with SELECT … FOR UPDATE SKIP LOCKED."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_priority", "status", "priority", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(50))  # scan | resolve_principals | dedupe | index
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|done|failed
    priority: Mapped[int] = mapped_column(Integer, default=100)  # lower runs first
    requested_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error: Mapped[Optional[str]] = mapped_column(Text)


# ── Phase 1: sign-in, search, audit ──────────────────────────────────────────

class AuthSession(Base):
    """
    A signed-in browser. The cookie holds a random token; only its SHA-256 is
    stored, so a database dump can't be used to impersonate anyone.
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    method: Mapped[str] = mapped_column(String(10))  # sso | ldap | dev
    # The user's SID plus every group SID from AD (tokenGroups): what Windows
    # would put in their access token. Permission checks use exactly this.
    token_sids: Mapped[list[str]] = mapped_column(JSON, default=list)
    groups_resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    client_ip: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(300))

    user: Mapped[User] = relationship()


# PostgreSQL full-text vector; plain text on SQLite, which only the tests use.
SearchVector = TSVECTOR().with_variant(Text(), "sqlite")


class Document(Base):
    """
    What search looks at for one file: its name and path, plus its text when it
    could be extracted. Created for every file by the `index` job.
    """

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_documents_title_vector", "title_vector", postgresql_using="gin"),
    )

    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), primary_key=True)
    # pending | text | ocr | empty | metadata | too_large | ocr_unavailable | error
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    content: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(String(500))
    extracted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    search_vector: Mapped[Optional[str]] = mapped_column(SearchVector)
    # Name and path only (weights A and B): small, so search can find name matches
    # among many content matches without reading every document's vector (BUG-027).
    title_vector: Mapped[Optional[str]] = mapped_column(SearchVector)

    file: Mapped[File] = relationship()


# ── Phase 2: the folder plan ─────────────────────────────────────────────────

class PlanFolder(Base):
    """
    One folder of the agreed structure: what it is for and what goes in it.

    Matched to the scanned folders by path (case-insensitive, as Windows), not by
    a foreign key: a planned folder may not exist yet, and a rescan or a refactor
    may recreate the real one. A share's plan starts with its root (path ""), and
    every other entry's parent is in the plan too.
    """

    __tablename__ = "plan_folders"
    __table_args__ = (UniqueConstraint("share_id", "path_key", name="uq_plan_folders_share_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    share_id: Mapped[int] = mapped_column(ForeignKey("shares.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)  # relative to the share, "/"-separated, "" for the root
    # Lower-cased path: what matching uses. Windows ignores case but not accents.
    path_key: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text, default="")
    belongs: Mapped[str] = mapped_column(Text, default="")  # what goes here
    not_belongs: Mapped[str] = mapped_column(Text, default="")  # what doesn't, and where it goes instead
    owner: Mapped[str] = mapped_column(String(200), default="")
    naming: Mapped[str] = mapped_column(Text, default="")  # the convention, for people
    # The convention, for the compliance report: see services/plan.py (e.g. "{YYYY}-{MM}-{DD} *").
    naming_pattern: Mapped[Optional[str]] = mapped_column(String(300))
    examples: Mapped[list[str]] = mapped_column(JSON, default=list)  # file names
    extensions: Mapped[list[str]] = mapped_column(JSON, default=list)  # expected types; empty = any
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)  # English and Spanish
    # Files may be saved directly in this folder (False for folders that only group others).
    allow_files: Mapped[bool] = mapped_column(Boolean, default=True)
    # Subfolders that aren't in the plan are fine here (one per project, year, ...);
    # they follow this entry's rules.
    allow_subfolders: Mapped[bool] = mapped_column(Boolean, default=False)
    max_files: Mapped[Optional[int]] = mapped_column(Integer)  # "overgrown" above this; NULL = default
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))


class PlanSnapshot(Base):
    """How far one share's refactor has come on one day: the compliance report's totals."""

    __tablename__ = "plan_snapshots"
    __table_args__ = (UniqueConstraint("share_id", "day", name="uq_plan_snapshots_share_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    share_id: Mapped[int] = mapped_column(ForeignKey("shares.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    files_total: Mapped[int] = mapped_column(Integer, default=0)
    files_in_plan: Mapped[int] = mapped_column(Integer, default=0)
    files_checked: Mapped[int] = mapped_column(Integer, default=0)  # in the plan, under a naming pattern
    files_misnamed: Mapped[int] = mapped_column(Integer, default=0)
    files_wrong_type: Mapped[int] = mapped_column(Integer, default=0)
    folders_planned: Mapped[int] = mapped_column(Integer, default=0)
    folders_missing: Mapped[int] = mapped_column(Integer, default=0)
    folders_empty: Mapped[int] = mapped_column(Integer, default=0)
    folders_overgrown: Mapped[int] = mapped_column(Integer, default=0)


class AuditEvent(Base):
    """
    Who searched, viewed or downloaded what. Kept for AUDIT_RETENTION_DAYS. No
    foreign key to files: the record must survive the file being deleted.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    # sign_in | sign_in_failed | sign_out | search | view | preview | download | denied
    action: Mapped[str] = mapped_column(String(20), index=True)
    file_id: Mapped[Optional[int]] = mapped_column(Integer)
    path: Mapped[Optional[str]] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    client_ip: Mapped[Optional[str]] = mapped_column(String(64))
