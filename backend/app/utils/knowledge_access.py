"""Knowledge document visibility helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tenant_context import current_tenant_id
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
    tenant_id: int | None = None,
) -> set[str] | None:
    """当前用户可检索的知识文档 id 集合。

    T3-3 租户隔离：文档可见性 = 本人 + 当前租户 + 平台共享（tenant_id 与
    user_id/organization_id 均为空）。管理员返回 None（全量可见）。
    tenant_id 未显式传入时取租户上下文（未注入回落默认租户 1）。
    """
    if is_admin_user(user):
        return None

    tid = tenant_id if tenant_id is not None else current_tenant_id()
    # 平台共享文档：tenant_id / user_id / organization_id 均为空（T3-3 迁移后平台文档三者皆空）
    platform_scope = (
        KnowledgeDocument.tenant_id.is_(None)
        & KnowledgeDocument.user_id.is_(None)
        & KnowledgeDocument.organization_id.is_(None)
    )
    # 租户级文档：仅 tenant_id 标记，且非个人 / 非组织（T3-3 迁移后租户知识 user_id/organization_id 为空）。
    # 个人文档也会盖 tenant_id，必须限定 user_id/organization_id 为空，
    # 否则同租户用户之间会互相看到彼此的个人知识文档。
    tenant_level = (
        (KnowledgeDocument.tenant_id == tid)
        & KnowledgeDocument.user_id.is_(None)
        & KnowledgeDocument.organization_id.is_(None)
    )

    if organization_id is not None:
        # 组织工作区：该组织文档（兼容迁移前后 organization_id / tenant_id 两种标记）+ 平台共享
        legacy_org = (
            (KnowledgeDocument.tenant_id == organization_id)
            & KnowledgeDocument.user_id.is_(None)
            & KnowledgeDocument.organization_id.is_(None)
        )
        visibility = or_(
            KnowledgeDocument.organization_id == organization_id,
            legacy_org,
            platform_scope,
        )
    else:
        owner_id = user.id if user is not None else user_id
        if owner_id is None:
            visibility = or_(
                tenant_level,
                platform_scope,
            )
        else:
            visibility = or_(
                KnowledgeDocument.user_id == owner_id,
                tenant_level,
                platform_scope,
            )

    rows = db.query(KnowledgeDocument.id).filter(visibility).all()
    return {str(row[0]) for row in rows}


# 可见集合下推进向量检索时，`$in` 会展开成同样多的查询参数；超过这个数就退回
# "取回后再过滤"（本机/CI 的知识库都远在此之下：28 篇 / 91 切片）。
VISIBLE_PUSHDOWN_LIMIT = 2048


def knowledge_where_filter(
    *,
    doc_type: str | None = None,
    visible_doc_ids: set[str] | None,
) -> dict[str, Any] | None:
    """把可见范围翻成 Chroma 的 `where` 条件，和 doc_type 一起返回。

    必须下推：`n_results` 是**候选槽位数**，"先取 top-N 再按可见性过滤"会让一个明明
    看得到文档的用户拿到 0 条。实测 16 篇 / 91 切片的语料上，只见 2 篇（11 个切片可查）
    的用户 7 条查询里有 3 条召回为 0、7 条全部少于下推能给出的数量。

    返回 None = 不需要下推（管理员全量可见），或可见集合大到不值得展开成 `$in`；
    两种情况下调用方仍会做取回后过滤，行为与下推前一致，不会更差。
    """
    conditions: list[dict[str, Any]] = []
    if doc_type:
        conditions.append({"doc_type": doc_type})
    if visible_doc_ids and len(visible_doc_ids) <= VISIBLE_PUSHDOWN_LIMIT:
        conditions.append({"doc_id": {"$in": sorted(visible_doc_ids)}})
    # 空集合不下推：Chroma 0.5.0 对 `$in: []` 是直接抛错（"non-empty list"），不是匹配空集。
    # 空可见集由调用方的提前返回 + 取回后过滤兜住，方向仍是 fail-closed，不会漏出内容。

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    # Chroma 0.5.0 的 where 只接受"恰好一个操作符"，裸多键会抛
    # `Expected where to have exactly one operator`；多条件必须包进 $and。
    # 这条形状约束是拿真实 collection 试出来的，mock 出来的 collection 不会报。
    return {"$and": conditions}
