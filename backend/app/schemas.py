from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    is_admin: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


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
    files_seen: int
    files_added: int
    files_updated: int
    files_removed: int
    error_count: int
    error_sample: Optional[str]

    model_config = {"from_attributes": True}
