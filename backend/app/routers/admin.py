import json
import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth.jwt import CurrentUser, require_admin
from ..database import get_db
from ..models import Category, Document, ScanConfig, User
from ..schemas import (
    CategoryCreate,
    CategoryPublic,
    CategoryUpdate,
    ScanConfigCreate,
    ScanConfigPublic,
    ScanConfigUpdate,
    SystemStats,
)
from ..services.indexer import rebuild_fts_index
from ..services.scanner import run_scan

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cat_public(cat: Category, db: Session) -> CategoryPublic:
    doc_count = (
        db.query(func.count(Document.id)).filter(Document.category_id == cat.id).scalar() or 0
    )
    child_count = (
        db.query(func.count(Category.id)).filter(Category.parent_id == cat.id).scalar() or 0
    )
    return CategoryPublic(
        id=cat.id,
        name=cat.name,
        description=cat.description,
        icon=cat.icon,
        color=cat.color,
        parent_id=cat.parent_id,
        sort_order=cat.sort_order,
        path=cat.path,
        auto_generated=cat.auto_generated,
        document_count=doc_count,
        children_count=child_count,
    )


def _cfg_public(cfg: ScanConfig) -> ScanConfigPublic:
    return ScanConfigPublic(
        id=cfg.id,
        name=cfg.name,
        root_path=cfg.root_path,
        root_category_id=cfg.root_category_id,
        allowed_groups=json.loads(cfg.allowed_groups or "[]"),
        max_depth=cfg.max_depth,
        file_extensions=json.loads(cfg.file_extensions) if cfg.file_extensions else None,
        is_active=cfg.is_active,
        create_subcategories=cfg.create_subcategories,
        last_scan=cfg.last_scan,
        scan_status=cfg.scan_status,
        scan_error=cfg.scan_error,
        documents_found=cfg.documents_found or 0,
        created_at=cfg.created_at,
    )


# ── Categories ─────────────────────────────────────────────────────────────────

@router.get("/categories", response_model=List[CategoryPublic])
def list_categories(
    db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)
):
    cats = db.query(Category).order_by(Category.sort_order, Category.name).all()
    return [_cat_public(c, db) for c in cats]


@router.post("/categories", response_model=CategoryPublic, status_code=201)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
):
    cat = Category(**payload.model_dump())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return _cat_public(cat, db)


@router.put("/categories/{category_id}", response_model=CategoryPublic)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    for field, value in payload.model_dump().items():
        setattr(cat, field, value)
    db.commit()
    db.refresh(cat)
    return _cat_public(cat, db)


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    db.delete(cat)
    db.commit()


# ── Scan Configurations ────────────────────────────────────────────────────────

@router.get("/scan-configs", response_model=List[ScanConfigPublic])
def list_scan_configs(
    db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)
):
    configs = db.query(ScanConfig).order_by(ScanConfig.name).all()
    return [_cfg_public(c) for c in configs]


@router.post("/scan-configs", response_model=ScanConfigPublic, status_code=201)
def create_scan_config(
    payload: ScanConfigCreate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
):
    cfg = ScanConfig(
        name=payload.name,
        root_path=payload.root_path,
        root_category_id=payload.root_category_id,
        allowed_groups=json.dumps(payload.allowed_groups),
        max_depth=payload.max_depth,
        file_extensions=json.dumps(payload.file_extensions) if payload.file_extensions else None,
        is_active=payload.is_active,
        create_subcategories=payload.create_subcategories,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return _cfg_public(cfg)


@router.put("/scan-configs/{config_id}", response_model=ScanConfigPublic)
def update_scan_config(
    config_id: int,
    payload: ScanConfigUpdate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
):
    cfg = db.query(ScanConfig).filter(ScanConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Scan config not found")
    cfg.name = payload.name
    cfg.root_path = payload.root_path
    cfg.root_category_id = payload.root_category_id
    cfg.allowed_groups = json.dumps(payload.allowed_groups)
    cfg.max_depth = payload.max_depth
    cfg.file_extensions = (
        json.dumps(payload.file_extensions) if payload.file_extensions else None
    )
    cfg.is_active = payload.is_active
    cfg.create_subcategories = payload.create_subcategories
    db.commit()
    db.refresh(cfg)
    return _cfg_public(cfg)


@router.delete("/scan-configs/{config_id}", status_code=204)
def delete_scan_config(
    config_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
):
    cfg = db.query(ScanConfig).filter(ScanConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Scan config not found")
    db.delete(cfg)
    db.commit()


@router.post("/scan-configs/{config_id}/trigger")
def trigger_scan(
    config_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
):
    cfg = db.query(ScanConfig).filter(ScanConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Scan config not found")
    if cfg.scan_status == "running":
        raise HTTPException(status_code=409, detail="A scan is already running for this config")
    background_tasks.add_task(run_scan, config_id)
    return {"message": f"Scan triggered for '{cfg.name}'"}


# ── System ────────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=SystemStats)
def get_stats(db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)):
    total_docs = (
        db.query(func.count(Document.id))
        .filter(Document.is_active == True)  # noqa: E712
        .scalar()
    )
    total_cats = db.query(func.count(Category.id)).scalar()
    total_scans = db.query(func.count(ScanConfig.id)).scalar()
    total_users = db.query(func.count(User.id)).scalar()
    last_cfg = (
        db.query(ScanConfig)
        .filter(ScanConfig.last_scan.isnot(None))
        .order_by(ScanConfig.last_scan.desc())
        .first()
    )
    return SystemStats(
        total_documents=total_docs or 0,
        total_categories=total_cats or 0,
        total_scan_configs=total_scans or 0,
        total_users=total_users or 0,
        last_scan=last_cfg.last_scan if last_cfg else None,
    )


@router.post("/rebuild-index")
def rebuild_index(
    background_tasks: BackgroundTasks, _: CurrentUser = Depends(require_admin)
):
    background_tasks.add_task(rebuild_fts_index)
    return {"message": "FTS index rebuild started in the background"}
