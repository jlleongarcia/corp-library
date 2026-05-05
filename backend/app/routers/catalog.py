from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth.jwt import CurrentUser, get_current_user
from ..database import get_db
from ..models import Category, Document
from ..schemas import CategoryPublic, CategoryTree, DocumentPublic
from ..services.permissions import filter_documents_query

router = APIRouter(prefix="/catalog", tags=["catalog"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _doc_to_public(doc: Document) -> DocumentPublic:
    tags = [t.strip() for t in doc.tags.split(",") if t.strip()] if doc.tags else []
    return DocumentPublic(
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
    )


def _build_tree(
    categories: list[Category], parent_id: Optional[int] = None
) -> list[CategoryTree]:
    result = []
    for cat in categories:
        if cat.parent_id == parent_id:
            children = _build_tree(categories, cat.id)
            node = CategoryTree(
                id=cat.id,
                name=cat.name,
                description=cat.description,
                icon=cat.icon,
                color=cat.color,
                parent_id=cat.parent_id,
                sort_order=cat.sort_order,
                path=cat.path,
                auto_generated=cat.auto_generated,
                document_count=0,
                children_count=len(children),
                children=children,
            )
            result.append(node)
    result.sort(key=lambda c: (c.sort_order, c.name.lower()))
    return result


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/tree", response_model=List[CategoryTree])
def get_category_tree(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    categories = db.query(Category).all()
    return _build_tree(categories)


@router.get("/categories", response_model=List[CategoryPublic])
def list_categories(
    parent_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    cats = (
        db.query(Category)
        .filter(Category.parent_id == parent_id)
        .order_by(Category.sort_order, Category.name)
        .all()
    )
    result = []
    for cat in cats:
        doc_count = (
            db.query(func.count(Document.id))
            .filter(Document.category_id == cat.id, Document.is_active == True)  # noqa: E712
            .scalar()
        )
        child_count = (
            db.query(func.count(Category.id))
            .filter(Category.parent_id == cat.id)
            .scalar()
        )
        result.append(
            CategoryPublic(
                id=cat.id,
                name=cat.name,
                description=cat.description,
                icon=cat.icon,
                color=cat.color,
                parent_id=cat.parent_id,
                sort_order=cat.sort_order,
                path=cat.path,
                auto_generated=cat.auto_generated,
                document_count=doc_count or 0,
                children_count=child_count or 0,
            )
        )
    return result


@router.get("/categories/{category_id}", response_model=CategoryPublic)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    doc_count = (
        db.query(func.count(Document.id))
        .filter(Document.category_id == cat.id, Document.is_active == True)  # noqa: E712
        .scalar()
    )
    child_count = (
        db.query(func.count(Category.id)).filter(Category.parent_id == cat.id).scalar()
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
        document_count=doc_count or 0,
        children_count=child_count or 0,
    )


@router.get("/categories/{category_id}/documents", response_model=List[DocumentPublic])
def get_category_documents(
    category_id: int,
    page: int = 1,
    page_size: int = 30,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    query = db.query(Document).filter(
        Document.category_id == category_id, Document.is_active == True  # noqa: E712
    )
    query = filter_documents_query(query, current_user)
    docs = query.order_by(Document.title).offset((page - 1) * page_size).limit(page_size).all()
    return [_doc_to_public(doc) for doc in docs]
