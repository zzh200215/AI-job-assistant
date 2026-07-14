"""Knowledge document visibility helpers."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.knowledge import KnowledgeDocument
from app.models.user import User


def is_admin_user(user: User | None) -> bool:
    return bool(user and user.username in settings.admin_usernames_list)


def visible_knowledge_filter(user: User | None = None, user_id: int | None = None):
    if is_admin_user(user):
        return None

    owner_id = user.id if user is not None else user_id
    if owner_id is None:
        return KnowledgeDocument.user_id.is_(None)
    return or_(KnowledgeDocument.user_id == owner_id, KnowledgeDocument.user_id.is_(None))


def get_visible_knowledge_doc_ids(
    db: Session,
    *,
    user: User | None = None,
    user_id: int | None = None,
    organization_id: int | None = None,
) -> set[str] | None:
    if organization_id is not None:
        visibility = or_(
            KnowledgeDocument.organization_id == organization_id,
            (KnowledgeDocument.organization_id.is_(None) & KnowledgeDocument.user_id.is_(None)),
        )
    else:
        visibility = visible_knowledge_filter(user=user, user_id=user_id)
    if visibility is None:
        return None

    rows = db.query(KnowledgeDocument.id).filter(visibility).all()
    return {str(row[0]) for row in rows}
