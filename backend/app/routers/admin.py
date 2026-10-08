from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.sessions import CurrentUser, require_admin
from ..database import get_db
from ..models import Job, ScanRun, Share
from ..schemas import (
    JobPublic, ScanRequest, ScanRunPublic, ShareCreate, SharePublic, ShareUpdate,
)
from ..services import indexer, jobs
from ..services.extract import tesseract_available

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ── Shares ────────────────────────────────────────────────────────────────────

@router.get("/shares", response_model=list[SharePublic])
def list_shares(db: Session = Depends(get_db)):
    return db.scalars(select(Share).order_by(Share.name)).all()


@router.post("/shares", response_model=SharePublic, status_code=201)
def create_share(body: ShareCreate, db: Session = Depends(get_db)):
    share = Share(name=body.name.strip(), path=body.path.strip(), enabled=body.enabled)
    db.add(share)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A share with that name already exists")
    return share


@router.put("/shares/{share_id}", response_model=SharePublic)
def update_share(share_id: int, body: ShareUpdate, db: Session = Depends(get_db)):
    share = db.get(Share, share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(share, field, value.strip() if isinstance(value, str) else value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A share with that name already exists")
    return share


@router.delete("/shares/{share_id}", status_code=204)
def delete_share(share_id: int, db: Session = Depends(get_db)):
    """Removes the share and everything indexed from it. Files on the server are untouched."""
    share = db.get(Share, share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    db.delete(share)
    db.commit()


# ── Jobs ──────────────────────────────────────────────────────────────────────

@router.post("/scans", response_model=list[JobPublic], status_code=202)
def request_scan(
    body: ScanRequest, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)
):
    if body.share_id is None:
        return jobs.enqueue_full_pipeline(db, requested_by=user.username)
    share = db.get(Share, body.share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return [jobs.enqueue(db, jobs.SCAN, {"share_id": share.id}, requested_by=user.username)]


@router.post("/jobs/{kind}", response_model=JobPublic, status_code=202)
def request_job(
    kind: str, retry: bool = False, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)
):
    """resolve_principals (forced refresh), dedupe, or index (`retry=true` re-reads failed files)."""
    if kind not in (jobs.RESOLVE, jobs.DEDUPE, jobs.INDEX):
        raise HTTPException(status_code=400, detail=f"Unknown job kind: {kind}")
    payload = {"force": True} if kind == jobs.RESOLVE else {"retry": True} if kind == jobs.INDEX and retry else {}
    return jobs.enqueue(db, kind, payload, requested_by=user.username)


@router.get("/index-status")
def index_status(db: Session = Depends(get_db)):
    """Files per extraction status: how much of the content is searchable."""
    return {"counts": indexer.status_counts(db), "ocr_available": tesseract_available()}


@router.get("/jobs", response_model=list[JobPublic])
def list_jobs(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    return db.scalars(select(Job).order_by(Job.id.desc()).limit(limit)).all()


@router.get("/scan-runs", response_model=list[ScanRunPublic])
def list_scan_runs(
    share_id: Optional[int] = None, limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)
):
    stmt = select(ScanRun).order_by(ScanRun.id.desc()).limit(limit)
    if share_id:
        stmt = stmt.where(ScanRun.share_id == share_id)
    return db.scalars(stmt).all()
