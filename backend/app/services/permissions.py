from sqlalchemy import exists, or_
from sqlalchemy.orm import Query

from ..auth.jwt import CurrentUser
from ..models import Document, DocumentPermission


def can_user_access_document(document: Document, current_user: CurrentUser) -> bool:
    """Return True if the user may view the given document."""
    if current_user.is_admin:
        return True
    if not document.permissions:
        return True  # No restrictions → public
    allowed = {p.ad_group for p in document.permissions}
    return bool(set(current_user.groups) & allowed)


def filter_documents_query(query: Query, current_user: CurrentUser) -> Query:
    """
    Narrow a Document SQLAlchemy query to only rows the current user can access.
    Admins see everything; regular users see:
      - documents with no permission entries (public), OR
      - documents where at least one of their AD groups is listed.
    """
    if current_user.is_admin:
        return query

    no_perms = ~exists().where(DocumentPermission.document_id == Document.id)

    if not current_user.groups:
        return query.filter(no_perms)

    has_matching_perm = exists().where(
        DocumentPermission.document_id == Document.id,
        DocumentPermission.ad_group.in_(current_user.groups),
    )
    return query.filter(or_(no_perms, has_matching_perm))
