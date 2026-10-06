"""Knowledge document visibility helpers."""

from __future__ import annotations

from typing import Any

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
    """当前用户可检索的知识文档 id 集合。

    2026-10-06 真删企业侧（D135）之前这里有三类：本人 + 当前租户 + 平台共享。中间那一类
    （`tenant_id == 当前租户` 且无 owner）随多租户一起删掉——**删之前实测它匹配 0 行**
    （`kb_document` 是 22 行 `tenant_id IS NULL` 的平台共享 + 6 行有 owner 的个人文档），
    所以可见集合不变。管理员仍返回 None（全量）。
    """
    if is_admin_user(user):
        return None

    # 平台共享文档：tenant_id / user_id / organization_id 均为空（T3-3 迁移后平台文档三者皆空）
    platform_scope = (
        KnowledgeDocument.tenant_id.is_(None)
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
        visibility = platform_scope if owner_id is None else or_(KnowledgeDocument.user_id == owner_id, platform_scope)

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
