from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.jwt import CurrentUser, get_current_user
from ..database import get_db
from ..models import Document
from ..schemas import DocumentDetail
from ..services.permissions import can_user_access_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.is_active == True)  # noqa: E712
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not can_user_access_document(doc, current_user):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to access this document",
        )

    tags = [t.strip() for t in doc.tags.split(",") if t.strip()] if doc.tags else []
    allowed_groups = [p.ad_group for p in doc.permissions]

    return DocumentDetail(
        id=doc.id,
        title=doc.title,
        description=doc.description,
        file_path=doc.file_path,
        file_name=doc.file_name,
        file_extension=doc.file_extension,
        file_size=doc.file_size,
        category_id=doc.category_id,
        category_name=doc.category.name if doc.category else None,
        category_path=doc.category.path if doc.category else None,
        last_modified=doc.last_modified,
        indexed_at=doc.indexed_at,
        tags=tags,
        is_active=doc.is_active,
        allowed_groups=allowed_groups,
    )
