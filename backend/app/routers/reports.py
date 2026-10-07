"""Discovery reports (admin only). Every list report also exports as CSV with ?format=csv."""

import csv
import io
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth.jwt import require_admin
from ..database import get_db
from ..services import reports

router = APIRouter(prefix="/admin/reports", tags=["reports"], dependencies=[Depends(require_admin)])

Format = Literal["json", "csv"]


def _csv(rows: list[dict], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    buf.write("﻿")  # BOM so Excel opens UTF-8 (accents) correctly
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: v.isoformat() if isinstance(v, datetime) else v for k, v in r.items()})
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
    share_id: Optional[int] = None, limit: int = Query(100, le=1000),
    format: Format = "json", db: Session = Depends(get_db),
):
    rows = reports.by_extension(db, share_id, limit)
    return _csv(rows, "extensions") if format == "csv" else rows


@router.get("/duplicates")
def duplicates(
    limit: int = Query(50, le=500), offset: int = 0, format: Format = "json", db: Session = Depends(get_db)
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
    years: int = Query(5, ge=1, le=50), share_id: Optional[int] = None, limit: int = Query(100, le=1000),
    format: Format = "json", db: Session = Depends(get_db),
):
    rows = reports.stale_folders(db, years, share_id, limit)
    return _csv(rows, f"stale-{years}y") if format == "csv" else rows


@router.get("/hygiene")
def hygiene(
    share_id: Optional[int] = None, limit: int = Query(200, le=2000),
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
