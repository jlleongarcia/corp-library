from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
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

    acl: Mapped[Optional[Acl]] = relationship()


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("folder_id", "name", name="uq_files_folder_name"),
        Index("ix_files_size_hash", "size", "quick_hash"),
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
    kind: Mapped[str] = mapped_column(String(50))  # scan | resolve_principals | dedupe
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|done|failed
    priority: Mapped[int] = mapped_column(Integer, default=100)  # lower runs first
    requested_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error: Mapped[Optional[str]] = mapped_column(Text)
