from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(default="", max_length=512)  # ignored in DEV_MODE


class UserPublic(BaseModel):
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    is_admin: bool = False


class AuthConfig(BaseModel):
    app_name: str
    sso_enabled: bool  # try Kerberos before showing the form
    dev_mode: bool  # the form needs no password


# ── Shares ────────────────────────────────────────────────────────────────────

class ShareCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1, max_length=1024, description=r"\\server\share or a local path (dev)")
    enabled: bool = True


class ShareUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    path: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    enabled: Optional[bool] = None


class SharePublic(BaseModel):
    id: int
    name: str
    path: str
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Jobs and scans ────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    share_id: Optional[int] = None  # None = all enabled shares


class JobPublic(BaseModel):
    id: int
    kind: str
    payload: dict[str, Any]
    status: str
    requested_by: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error: Optional[str]

    model_config = {"from_attributes": True}


class ScanRunPublic(BaseModel):
    id: int
    share_id: int
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    folders_seen: int
    folders_skipped: int
    files_seen: int
    files_added: int
    files_updated: int
    files_removed: int
    error_count: int
    error_sample: Optional[str]

    model_config = {"from_attributes": True}


# ── Search, browse, documents ─────────────────────────────────────────────────

class SnippetSegment(BaseModel):
    text: str
    hit: bool


class SearchResult(BaseModel):
    file_id: int
    name: str
    extension: str
    size: int
    mtime: Optional[datetime]
    share_id: int
    share: str
    folder_id: int
    folder_path: str
    path: str  # \\server\share\folder\file, for "copy network path"
    snippet: list[SnippetSegment]


class SearchResponse(BaseModel):
    total: Optional[int]  # None when not asked for (count=false)
    total_capped: bool = False  # more than `total` matches (search.COUNT_CAP)
    results: list[SearchResult]


class Option(BaseModel):
    key: str
    label: str


class SearchFilters(BaseModel):
    shares: list[Option]
    types: list[Option]


class BrowseShare(BaseModel):
    id: int
    name: str
    path: str
    root_folder_id: int


class Breadcrumb(BaseModel):
    folder_id: Optional[int]  # None: the user can't list that ancestor
    name: str


class BrowseFolderRef(BaseModel):
    id: int
    name: str
    mtime: Optional[datetime]


class BrowseFile(BaseModel):
    file_id: int
    name: str
    extension: str
    size: int
    mtime: Optional[datetime]


class BrowseFolderInfo(BaseModel):
    id: int
    name: str
    share_id: int
    share: str
    path: str


class BrowseResponse(BaseModel):
    folder: BrowseFolderInfo
    breadcrumbs: list[Breadcrumb]
    folders: list[BrowseFolderRef]
    files: list[BrowseFile]
    files_hidden: bool
    files_truncated: bool


class DocumentDetail(BaseModel):
    file_id: int
    name: str
    extension: str
    size: int
    mtime: Optional[datetime]
    ctime: Optional[datetime]
    share_id: int
    share: str
    folder_id: int
    folder_path: str
    path: str
    # pending | text | ocr | empty | metadata | too_large | ocr_unavailable | error | null (not indexed yet)
    index_status: Optional[str]
    preview: Optional[str]  # pdf | image: can be shown inline
    text_excerpt: Optional[str]
    text_truncated: bool


# ── Privacy notice ────────────────────────────────────────────────────────────

class PrivacyInfo(BaseModel):
    controller: str
    controller_id: str
    controller_address: str
    contact: str
    dpo: str
    audit_retention_days: int
    backup_keep_days: int
    session_days: int
    groups_refresh_hours: int
    missing: list[str]  # settings still to fill in before going live


# ── Audit ─────────────────────────────────────────────────────────────────────

class AuditEventPublic(BaseModel):
    id: int
    at: datetime
    username: Optional[str]
    action: str
    file_id: Optional[int]
    path: Optional[str]
    detail: dict[str, Any]
    client_ip: Optional[str]

    model_config = {"from_attributes": True}
