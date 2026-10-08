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
    plan: Optional["FolderPlacement"] = None  # None: the share has no folder plan


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


# ── Folder plan ───────────────────────────────────────────────────────────────

LONG_TEXT = 10_000


class PlanFolderFields(BaseModel):
    """What an admin can set on a plan entry. On update, only the fields sent change."""

    purpose: Optional[str] = Field(default=None, max_length=LONG_TEXT)
    belongs: Optional[str] = Field(default=None, max_length=LONG_TEXT)
    not_belongs: Optional[str] = Field(default=None, max_length=LONG_TEXT)
    owner: Optional[str] = Field(default=None, max_length=200)
    naming: Optional[str] = Field(default=None, max_length=LONG_TEXT)
    naming_pattern: Optional[str] = Field(default=None, max_length=300)
    examples: Optional[list[str]] = Field(default=None, max_length=50)
    extensions: Optional[list[str]] = Field(default=None, max_length=50)
    keywords: Optional[list[str]] = Field(default=None, max_length=100)
    allow_files: Optional[bool] = None
    allow_subfolders: Optional[bool] = None
    max_files: Optional[int] = Field(default=None, ge=1, le=1_000_000)


class PlanFolderCreate(PlanFolderFields):
    share_id: int
    path: str = Field(max_length=2000, description='Relative to the share, "" for its root')


class PlanFolderUpdate(PlanFolderFields):
    path: Optional[str] = Field(default=None, max_length=2000, description="Moves or renames the entry")


class PlanImport(BaseModel):
    share_id: int
    depth: int = Field(default=2, ge=1, le=6)


class PlanGuideEntry(BaseModel):
    id: int
    share_id: int
    share: str
    path: str
    name: str
    depth: int
    network_path: str
    purpose: str
    belongs: str
    not_belongs: str
    owner: str
    naming: str
    naming_pattern: Optional[str]
    examples: list[str]
    extensions: list[str]
    keywords: list[str]
    allow_files: bool
    allow_subfolders: bool
    folder_id: Optional[int]  # its folder, when it exists and the user can browse it


class PlanEntryAdmin(PlanGuideEntry):
    max_files: Optional[int]
    exists: bool  # the folder is on the share (as of the last scan)
    example_problems: list[str]  # examples its own rules would reject
    updated_at: datetime
    updated_by: Optional[str]


class PlanGuideShare(BaseModel):
    share_id: int
    share: str
    path: str
    entries: list[PlanGuideEntry]


class FolderPlacement(BaseModel):
    """Where a browsed folder stands in its share's plan."""

    status: str  # planned | free (an unlisted subfolder its plan allows) | outside
    entry: Optional[PlanGuideEntry]  # its entry, the one whose rules it follows, or where its files could go


# ── Privacy notice ────────────────────────────────────────────────────────────

class PrivacyInfo(BaseModel):
    controller: str
    controller_id: str
    controller_address: str
    contact: str
    dpo: str
    record_url: str  # entry in the public record of processing activities
    authority_name: str  # supervisory authority for complaints
    authority_url: str
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


BrowseResponse.model_rebuild()  # its `plan` refers to FolderPlacement, defined below it
