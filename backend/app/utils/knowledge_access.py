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
) -> set[str] | None:
    """当前用户可检索的知识文档 id 集合：本人 + 平台共享（无主）。管理员返回 None（全量）。

    这一支在 D135/D136 之前有三级：本人 + 当前租户 + 组织工作区（外加一条"迁移前用 tenant_id 当
    组织 id"的兼容读法）。租户级实测匹配 0 行所以先删；组织那一级随 `X-Organization-ID` 一起删。
    **"平台共享"的定义改回它本来想说的那句话：`user_id IS NULL`（无主即共享）**，不再同时要求
    `tenant_id / organization_id` 为空。两种读法在这份数据上逐字等价——现取分布是 22 行三键皆空
    + 6 行有 owner，`user_id IS NULL 且 tenant_id 非空` 的行数是 **0**，所以可见集合仍是 22 / 28。
    """
    if is_admin_user(user):
        return None

    platform_scope = KnowledgeDocument.user_id.is_(None)
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
