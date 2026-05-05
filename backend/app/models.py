from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    display_name = Column(String(200), nullable=True)
    email = Column(String(200), nullable=True)
    hashed_password = Column(String(255), nullable=True)  # dev-mode only
    ad_groups = Column(Text, nullable=True)               # JSON list
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), default="folder")
    color = Column(String(7), default="#2563eb")
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    path = Column(String(2000), nullable=True)   # materialised breadcrumb
    sort_order = Column(Integer, default=0)
    auto_generated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    parent = relationship(
        "Category", back_populates="children", remote_side="Category.id"
    )
    children = relationship("Category", back_populates="parent", lazy="select")
    documents = relationship("Document", back_populates="category")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    file_path = Column(String(2000), nullable=False, unique=True)
    file_name = Column(String(255), nullable=False)
    file_extension = Column(String(20), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    scan_config_id = Column(Integer, ForeignKey("scan_configs.id"), nullable=True)
    last_modified = Column(DateTime, nullable=True)
    indexed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    tags = Column(Text, nullable=True)      # comma-separated
    is_active = Column(Boolean, default=True, nullable=False)

    category = relationship("Category", back_populates="documents")
    permissions = relationship(
        "DocumentPermission",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="select",
    )
    scan_config = relationship("ScanConfig", back_populates="documents")


class DocumentPermission(Base):
    __tablename__ = "document_permissions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer, ForeignKey("documents.id"), nullable=False, index=True
    )
    ad_group = Column(String(300), nullable=False)

    document = relationship("Document", back_populates="permissions")


class ScanConfig(Base):
    __tablename__ = "scan_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    root_path = Column(String(2000), nullable=False)
    root_category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    allowed_groups = Column(Text, nullable=True)     # JSON list of AD group names
    max_depth = Column(Integer, default=5)
    file_extensions = Column(Text, nullable=True)   # JSON list; NULL = all types
    is_active = Column(Boolean, default=True)
    create_subcategories = Column(Boolean, default=True)
    last_scan = Column(DateTime, nullable=True)
    scan_status = Column(String(20), default="never")  # never | running | success | error
    scan_error = Column(Text, nullable=True)
    documents_found = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    root_category = relationship("Category")
    documents = relationship("Document", back_populates="scan_config")
