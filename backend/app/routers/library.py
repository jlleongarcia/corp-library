"""
What every signed-in user gets: search, browse, document page, open/download.

Every query is filtered by the user's groups (see services/access.py). Admins
get no extra visibility here: the app never grants access Windows doesn't.
"""

import mimetypes
from datetime import date
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth.sessions import CurrentUser, get_current_user
from ..database import get_db
from ..schemas import BrowseResponse, BrowseShare, DocumentDetail, SearchFilters, SearchResponse
from ..services import audit, library
from ..services.search import SearchParams, Sort, file_types, search, visible_shares

router = APIRouter(tags=["library"])

EXCERPT_CHARS = 5000
# Shown inline in the browser. Never HTML or SVG: they could run scripts on our origin.
INLINE_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
    "bmp": "image/bmp", "webp": "image/webp",
}
NOT_FOUND = HTTPException(status_code=404, detail="Document not found")


@router.get("/search", response_model=SearchResponse)
def search_documents(
    request: Request,
    q: str = Query("", max_length=500),
    share_id: Optional[int] = None,
    type: Optional[str] = Query(None, max_length=20),
    modified_from: Optional[date] = None,
    modified_to: Optional[date] = None,
    sort: Sort = "relevance",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    params = SearchParams(q.strip(), share_id, type, modified_from, modified_to, sort, limit, offset)
    result = search(db, user.token_sids, params)
    filters = {k: v for k, v in {
        "share_id": share_id, "type": type, "modified_from": str(modified_from) if modified_from else None,
        "modified_to": str(modified_to) if modified_to else None,
    }.items() if v is not None}
    # One record per search, not per page; the home page's "recently modified" list isn't a search.
    if offset == 0 and (params.q or filters):
        audit.record(db, "search", user.username, request, q=params.q, results=result["total"], **filters)
    return result


@router.get("/search/filters", response_model=SearchFilters)
def search_filters(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return {
        "shares": [{"key": str(s.id), "label": s.name} for s in visible_shares(db, user.token_sids)],
        "types": file_types(),
    }


@router.get("/browse/shares", response_model=list[BrowseShare])
def browse_shares(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return library.browsable_shares(db, user.token_sids)


@router.get("/browse/folders/{folder_id}", response_model=BrowseResponse)
def browse_folder(folder_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    try:
        return library.browse(db, user.token_sids, folder_id)
    except library.NotFound:
        raise HTTPException(status_code=404, detail="Folder not found")


@router.get("/documents/{file_id}", response_model=DocumentDetail)
def document(file_id: int, request: Request, db: Session = Depends(get_db),
             user: CurrentUser = Depends(get_current_user)):
    try:
        ref = library.get_document(db, user.token_sids, file_id)
    except library.NotFound:
        raise NOT_FOUND
    audit.record(db, "view", user.username, request, file_id=file_id, path=ref.path)
    content = ref.document.content if ref.document else None
    return DocumentDetail(
        file_id=ref.file.id, name=ref.file.name, extension=ref.file.extension, size=ref.file.size,
        mtime=ref.file.mtime, ctime=ref.file.ctime, share_id=ref.share.id, share=ref.share.name,
        folder_id=ref.folder.id, folder_path=ref.folder.path, path=ref.path,
        index_status=ref.document.status if ref.document else None,
        preview=("pdf" if ref.file.extension == "pdf" else "image") if ref.file.extension in INLINE_TYPES else None,
        text_excerpt=content[:EXCERPT_CHARS] if content else None,
        text_truncated=bool(content and len(content) > EXCERPT_CHARS),
    )


def _open(file_id: int, request: Request, db: Session, user: CurrentUser, inline: bool) -> StreamingResponse:
    action = "preview" if inline else "download"
    try:
        ref = library.get_document(db, user.token_sids, file_id)
    except library.NotFound:
        raise NOT_FOUND
    if inline and ref.file.extension not in INLINE_TYPES:
        raise HTTPException(status_code=415, detail="No preview for this file type")
    try:
        source = library.check_live_access(ref, user.token_sids)
        chunks = library.open_stream(source, ref.relpath)
    except library.AccessDenied:
        audit.record(db, "denied", user.username, request, file_id=file_id, path=ref.path, attempted=action)
        raise HTTPException(status_code=403, detail="The file server doesn't allow you to open this file")
    except library.CheckUnavailable:
        raise HTTPException(status_code=503, detail="The file server can't be reached to check your access")
    except OSError:
        raise HTTPException(status_code=404, detail="The file is no longer on the file server")
    audit.record(db, action, user.username, request, file_id=file_id, path=ref.path)

    if inline:
        media_type = INLINE_TYPES[ref.file.extension]
        disposition = "inline"
    else:
        media_type = mimetypes.guess_type(ref.file.name)[0] or "application/octet-stream"
        disposition = "attachment"
    # RFC 6266: an ASCII fallback plus the real (UTF-8) name for accents.
    ascii_name = ref.file.name.encode("ascii", "replace").decode().replace('"', "'")
    headers = {
        "Content-Disposition": f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(ref.file.name)}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }
    return StreamingResponse(chunks, media_type=media_type, headers=headers)


@router.get("/documents/{file_id}/download")
def download(file_id: int, request: Request, db: Session = Depends(get_db),
             user: CurrentUser = Depends(get_current_user)):
    return _open(file_id, request, db, user, inline=False)


@router.get("/documents/{file_id}/preview")
def preview(file_id: int, request: Request, db: Session = Depends(get_db),
            user: CurrentUser = Depends(get_current_user)):
    return _open(file_id, request, db, user, inline=True)
