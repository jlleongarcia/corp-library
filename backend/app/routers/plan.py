"""
The folder plan: the read-only guide for everyone, and the admin editor.
The compliance report and its history live with the other reports (routers/reports.py).
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.sessions import CurrentUser, get_current_user, require_admin
from ..database import get_db
from ..models import PlanFolder, Share
from ..schemas import PlanEntryAdmin, PlanFolderCreate, PlanFolderUpdate, PlanGuideShare, PlanImport
from ..services import plan

router = APIRouter(tags=["plan"])
admin = APIRouter(prefix="/admin/plan", tags=["plan"], dependencies=[Depends(require_admin)])


@router.get("/plan", response_model=list[PlanGuideShare])
def folder_guide(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    """The plan of every share, limited to the folders this user can see in Explorer."""
    return plan.guide(db, user.token_sids)


def _share(db: Session, share_id: int) -> Share:
    share = db.get(Share, share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return share


def _entry(db: Session, entry_id: int) -> PlanFolder:
    entry = db.get(PlanFolder, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Plan entry not found")
    return entry


def _admin_entry(db: Session, entry: PlanFolder) -> dict:
    return next(e for e in plan.admin_view(db, entry.share_id) if e["id"] == entry.id)


def _fail(exc: plan.PlanError):
    raise HTTPException(status_code=409 if isinstance(exc, plan.PlanConflict) else 422, detail=str(exc))


@admin.get("", response_model=list[PlanEntryAdmin])
def list_entries(share_id: Optional[int] = None, db: Session = Depends(get_db)):
    return plan.admin_view(db, share_id)


@admin.post("", response_model=PlanEntryAdmin, status_code=201)
def create_entry(body: PlanFolderCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    share = _share(db, body.share_id)
    fields = body.model_dump(exclude_unset=True, exclude={"share_id", "path"})
    try:
        entry = plan.create_entry(db, share, body.path, fields, user.username)
    except plan.PlanError as exc:
        db.rollback()
        _fail(exc)
    return _admin_entry(db, entry)


@admin.put("/{entry_id}", response_model=PlanEntryAdmin)
def update_entry(entry_id: int, body: PlanFolderUpdate, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(require_admin)):
    entry = _entry(db, entry_id)
    try:
        plan.update_entry(db, entry, body.model_dump(exclude_unset=True), user.username)
    except plan.PlanError as exc:
        db.rollback()
        _fail(exc)
    return _admin_entry(db, entry)


@admin.delete("/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    """Removes the entry and everything planned below it (the root: the whole plan). Folders are untouched."""
    return {"deleted": plan.delete_entry(db, _entry(db, entry_id))}


@admin.post("/import", status_code=201)
def import_folders(body: PlanImport, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    """Add the share's existing folders, down to `depth` levels, to its plan."""
    return {"added": plan.import_folders(db, _share(db, body.share_id), body.depth, user.username)}
