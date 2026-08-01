"""外部 API 鉴权依赖（T6-1）：`X-API-Key` 头 → ApiKey。

独立于平台 JWT 体系。校验顺序：缺 Key → 401；Key 无效 → 401；
已停用/过期 → 403；当日调用超额 → 429。
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_key import ApiKey
from app.services.api_key_service import check_daily_quota, get_api_key_by_token, is_key_valid


def require_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> ApiKey:
    if not x_api_key or not x_api_key.strip():
        raise HTTPException(status_code=401, detail="缺少 X-API-Key 请求头")
    key = get_api_key_by_token(db, x_api_key.strip())
    if key is None:
        raise HTTPException(status_code=401, detail="API Key 无效")
    # 行锁：阻止同 Key 并发请求在「配额 check」与「usage 记账」之间插入（TOCTOU）。
    # 锁持有到 _run 内 record_usage 提交事务，同一 Key 的并发请求串行化后配额计数准确。
    key = db.query(ApiKey).filter(ApiKey.id == key.id).with_for_update().first()
    valid, reason = is_key_valid(key)
    if not valid:
        raise HTTPException(status_code=403, detail=reason)
    if not check_daily_quota(db, key):
        raise HTTPException(status_code=429, detail="今日调用额度已用尽，请升级配额或明日再试")
    return key
