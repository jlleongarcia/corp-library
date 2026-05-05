from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    is_admin: bool = False
    ad_groups: List[str] = []

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ── Category ──────────────────────────────────────────────────────────────────

class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    icon: str = "folder"
    color: str = "#2563eb"
    parent_id: Optional[int] = None
    sort_order: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(CategoryBase):
    pass


class CategoryPublic(CategoryBase):
    id: int
    path: Optional[str] = None
    auto_generated: bool = False
    document_count: int = 0
    children_count: int = 0

    model_config = {"from_attributes": True}


class CategoryTree(CategoryPublic):
    children: List["CategoryTree"] = []


# ── Document ──────────────────────────────────────────────────────────────────

class DocumentPublic(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    file_path: str
    file_name: str
    file_extension: Optional[str] = None
    file_size: Optional[int] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    category_path: Optional[str] = None
    last_modified: Optional[datetime] = None
    indexed_at: datetime
    tags: List[str] = []
    is_active: bool = True

    model_config = {"from_attributes": True}


class DocumentDetail(DocumentPublic):
    allowed_groups: List[str] = []


# ── Search ────────────────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    file_path: str
    file_name: str
    file_extension: Optional[str] = None
    category_name: Optional[str] = None
    category_id: Optional[int] = None
    tags: List[str] = []
    last_modified: Optional[datetime] = None
    indexed_at: datetime
    highlight_title: Optional[str] = None
    highlight_description: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: List[SearchResult]
    page: int
    page_size: int


# ── Scan Config ───────────────────────────────────────────────────────────────

class ScanConfigBase(BaseModel):
    name: str
    root_path: str
    root_category_id: Optional[int] = None
    allowed_groups: List[str] = []
    max_depth: int = 5
    file_extensions: Optional[List[str]] = None
    is_active: bool = True
    create_subcategories: bool = True


class ScanConfigCreate(ScanConfigBase):
    pass


class ScanConfigUpdate(ScanConfigBase):
    pass


class ScanConfigPublic(ScanConfigBase):
    id: int
    last_scan: Optional[datetime] = None
    scan_status: str = "never"
    scan_error: Optional[str] = None
    documents_found: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Admin ─────────────────────────────────────────────────────────────────────

class SystemStats(BaseModel):
    total_documents: int
    total_categories: int
    total_scan_configs: int
    total_users: int
    last_scan: Optional[datetime] = None


CategoryTree.model_rebuild()
