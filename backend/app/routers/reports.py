"""Discovery reports and the audit log (admin only). Every list also exports as CSV with ?format=csv."""

import csv
import io
import json
from datetime import date, datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth.sessions import CurrentUser, require_admin
from ..database import get_db
from ..models import Share
from ..schemas import AuditEventPublic
from ..services import audit, plan, reports

router = APIRouter(prefix="/admin/reports", tags=["reports"], dependencies=[Depends(require_admin)])

Format = Literal["json", "csv"]

# Excel runs a cell starting with these as a formula: a file named
# "=HYPERLINK(...).docx", or a search typed by a user, must stay text (BUG-012).
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def _csv(rows: list[dict], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    buf.write("﻿")  # BOM so Excel opens UTF-8 (accents) correctly
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: _cell(v) for k, v in r.items()})
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    return {
        "shares": reports.summary(db),
        "by_extension": reports.by_extension(db),
        "by_age": reports.by_age(db),
    }


@router.get("/extensions")
def extensions(
    share_id: Optional[int] = None, limit: int = Query(100, ge=1, le=1000),
    format: Format = "json", db: Session = Depends(get_db),
):
    rows = reports.by_extension(db, share_id, limit)
    return _csv(rows, "extensions") if format == "csv" else rows


@router.get("/duplicates")
def duplicates(
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), format: Format = "json", db: Session = Depends(get_db)
):
    data = reports.duplicates(db, limit, offset)
    if format == "csv":
        rows = [
            {"group": i + offset + 1, "confidence": g["confidence"], "size": g["size"],
             "copies": g["copies"], "wasted_bytes": g["wasted_bytes"], "path": f["path"], "modified": f["mtime"]}
            for i, g in enumerate(data["groups"]) for f in g["files"]
        ]
        return _csv(rows, "duplicates")
    return data


@router.get("/stale")
def stale(
    years: int = Query(5, ge=1, le=50), share_id: Optional[int] = None, limit: int = Query(100, ge=1, le=1000),
    format: Format = "json", db: Session = Depends(get_db),
):
    rows = reports.stale_folders(db, years, share_id, limit)
    return _csv(rows, f"stale-{years}y") if format == "csv" else rows


@router.get("/hygiene")
def hygiene(
    share_id: Optional[int] = None, limit: int = Query(200, ge=1, le=2000),
    format: Format = "json", db: Session = Depends(get_db),
):
    data = reports.hygiene(db, share_id, limit)
    if format == "csv":
        rows = (
            [{"issue": "long path", "path": i["path"], "detail": i["length"]} for i in data["long_paths"]["items"]]
            + [{"issue": "deep folder", "path": i["path"], "detail": i["depth"]} for i in data["deep_folders"]["items"]]
            + [{"issue": "empty folder", "path": i["path"], "detail": ""} for i in data["empty_folders"]["items"]]
            + [{"issue": "could not list", "path": i["path"], "detail": i["error"]}
               for i in data["unlisted_folders"]["items"]]
        )
        return _csv(rows, "hygiene")
    return data


@router.get("/acl-exceptions")
def acl_exceptions(share_id: Optional[int] = None, format: Format = "json", db: Session = Depends(get_db)):
    data = reports.acl_exceptions(db, share_id)
    if format == "csv":
        rows = [
            {"folder": f["path"], "inheritance_disabled": f["inheritance_disabled"],
             "acl_error": f["acl_error"] or "", "principal": e["display_name"] or e["name"],
             "kind": e["kind"], "type": e["type"], "level": e["level"], "inherited": e["inherited"]}
            for f in data for e in (f["entries"] or [{"display_name": "", "name": "", "kind": "",
                                                      "type": "", "level": "", "inherited": ""}])
        ]
        return _csv(rows, "acl-exceptions")
    return data


@router.get("/permissions")
def permissions(max_depth: int = Query(2, ge=0, le=10), format: Format = "json", db: Session = Depends(get_db)):
    data = reports.permission_grid(db, max_depth)
    if format == "csv":
        rows = [
            {"user": r["display_name"] or r["name"], "account": r["name"], "kind": r["kind"],
             **{c["path"]: r["cells"][c["folder_id"]] for c in data["columns"]}}
            for r in data["rows"]
        ]
        return _csv(rows, "permissions")
    return data


@router.get("/audit")
def audit_log(
    request: Request,
    username: Optional[str] = Query(None, max_length=100), action: Optional[str] = None,
    since: Optional[date] = None, until: Optional[date] = None,
    limit: int = Query(200, ge=1, le=10_000), offset: int = Query(0, ge=0),
    format: Format = "json", db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin),
):
    data = audit.query(db, username, action, since, until, limit, offset)
    if offset == 0:  # one record per query, not per page
        filters = {k: str(v) for k, v in {"about_user": username, "about_action": action, "since": since,
                                          "until": until, "format": format}.items() if v}
        audit.record(db, "audit_read", user.username, request, **filters)
    if format == "csv":
        rows = [
            {"at": e.at, "user": e.username or "", "action": e.action, "path": e.path or "",
             "query": e.detail.get("q", ""), "results": e.detail.get("results", ""),
             "ip": e.client_ip or "", "detail": json.dumps(e.detail, ensure_ascii=False)}
            for e in data["events"]
        ]
        return _csv(rows, "audit")
    return {"total": data["total"], "events": [AuditEventPublic.model_validate(e) for e in data["events"]]}


# ── Folder plan (phase 2) ─────────────────────────────────────────────────────

@router.get("/plan")
def plan_export(share_id: Optional[int] = None, format: Format = "csv", db: Session = Depends(get_db)):
    """The plan itself, for the folder-plan meeting or a printout."""
    rows = [
        {"share": e["share"], "folder": e["network_path"], "purpose": e["purpose"], "belongs": e["belongs"],
         "does_not_belong": e["not_belongs"], "owner": e["owner"], "naming": e["naming"],
         "naming_pattern": e["naming_pattern"] or "", "examples": " | ".join(e["examples"]),
         "file_types": ", ".join(e["extensions"]), "keywords": ", ".join(e["keywords"]),
         "files_here": "yes" if e["allow_files"] else "no",
         "other_subfolders": "yes" if e["allow_subfolders"] else "no",
         "max_files": e["max_files"] or "", "exists": "yes" if e["exists"] else "not yet"}
        for e in plan.admin_view(db, share_id)
    ]
    return _csv(rows, "folder-plan") if format == "csv" else rows


@router.get("/compliance")
def compliance(
    share_id: int, limit: int = Query(200, ge=1, le=5000), format: Format = "json", db: Session = Depends(get_db),
):
    """How one share follows its plan, computed now from the last scan."""
    share = db.get(Share, share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    data = plan.evaluate(db, share, limit)
    if data is None:
        raise HTTPException(status_code=404, detail="This share has no folder plan yet")
    if format == "csv":
        rows = (
            [{"issue": "outside the plan" if i["reason"] == "not_in_plan" else "files not allowed here",
              "path": i["path"], "detail": f"{i['files']} files", "plan_folder": i["plan_path"] or ""}
             for i in data["outside"]["items"]]
            + [{"issue": "naming", "path": i["path"], "detail": i["pattern"], "plan_folder": i["plan_path"]}
               for i in data["misnamed"]["items"]]
            + [{"issue": "file type", "path": i["path"], "detail": f".{i['extension']} (expected {', '.join(i['allowed'])})",
                "plan_folder": i["plan_path"]} for i in data["wrong_type"]["items"]]
            + [{"issue": "planned folder missing", "path": i["path"], "detail": "", "plan_folder": i["path"]}
               for i in data["missing"]["items"]]
            + [{"issue": "planned folder empty", "path": i["path"], "detail": "", "plan_folder": i["path"]}
               for i in data["empty"]["items"]]
            + [{"issue": "overgrown", "path": i["path"], "detail": f"{i['files']} files (limit {i['limit']})",
                "plan_folder": ""} for i in data["overgrown"]["items"]]
        )
        return _csv(rows, f"compliance-{share.name}")
    return data


@router.get("/compliance/progress")
def compliance_progress(days: int = Query(plan.HISTORY_DAYS, ge=1, le=3650), format: Format = "json",
                        db: Session = Depends(get_db)):
    """The daily snapshots per share (taken after each nightly scan, or on request)."""
    data = plan.progress(db, days)
    if format == "csv":
        return _csv([{"share": s["share"], **snap} for s in data for snap in s["snapshots"]], "plan-progress")
    return data
