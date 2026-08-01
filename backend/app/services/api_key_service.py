"""External API key + usage + billing service layer（T6-1 / T6-2）。

- Key 只存 sha256 哈希，明文创建时返回一次；
- 每次外部调用写 api_usage（限流 + 计费数据源）；
- 月度结算：聚合 api_usage → api_bill（幂等 upsert，同周期重跑覆盖）。
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.api_bill import ApiBill
from app.models.api_key import ApiKey
from app.models.api_pricing import ApiPricing
from app.models.api_usage import ApiUsage
from app.utils.time_helper import utc_now_naive

# 端点 → 默认单价（分/次），与 docs/定价表.md §7 API 定价框架对齐；
# 迁移时写入 api_pricing 表，运营可改表覆盖。
DEFAULT_API_PRICING: dict[str, int] = {
    "resume.parse": 30,  # ¥0.30 / 次
    "match.evaluate": 30,  # ¥0.30 / 次
    "interview.simulate": 80,  # ¥0.80 / 次
}


# ===== Key 管理 =====


def generate_api_key() -> str:
    """生成明文 Key（sk- 前缀 + 128bit 随机）。"""
    return "sk-" + secrets.token_urlsafe(24)


def hash_api_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def create_api_key(
    db: Session,
    *,
    name: str,
    tenant_id: int,
    daily_quota: int = 1000,
    expires_at: datetime | None = None,
) -> tuple[ApiKey, str]:
    plain = generate_api_key()
    key = ApiKey(
        name=name,
        key_hash=hash_api_key(plain),
        tenant_id=tenant_id,
        daily_quota=daily_quota,
        expires_at=expires_at,
        status="active",
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return key, plain


def get_api_key_by_token(db: Session, plain: str) -> ApiKey | None:
    return db.query(ApiKey).filter(ApiKey.key_hash == hash_api_key(plain)).first()


def is_key_valid(key: ApiKey) -> tuple[bool, str | None]:
    """返回 (是否可用, 不可用原因)。"""
    if key.status != "active":
        return False, "API Key 已停用"
    if key.expires_at is not None and key.expires_at < utc_now_naive():
        return False, "API Key 已过期"
    return True, None


# ===== 限流（按日） =====


def count_usage_since(
    db: Session, key_id: int, since: datetime, status: str | None = None
) -> int:
    """统计某 Key 自 since 起的调用数；status 给定时仅统计该状态。"""
    query = db.query(func.count(ApiUsage.id)).filter(
        ApiUsage.api_key_id == key_id,
        ApiUsage.created_at >= since,
    )
    if status is not None:
        query = query.filter(ApiUsage.status == status)
    return query.scalar() or 0


def check_daily_quota(db: Session, key: ApiKey) -> bool:
    """当日调用数（含失败）< daily_quota 才放行；达到上限 → 429。

    失败调用同样消耗了平台资源（LLM 已执行），必须计入配额，
    否则攻击者可借「必失败的请求」无限消耗免费 LLM 额度。
    """
    now = utc_now_naive()
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return count_usage_since(db, key.id, since) < key.daily_quota


# ===== 调用记录与计费 =====


def get_unit_price(db: Session, endpoint: str) -> int:
    row = (
        db.query(ApiPricing)
        .filter(ApiPricing.endpoint == endpoint, ApiPricing.is_active == 1)
        .first()
    )
    if row is not None:
        return int(row.unit_price)
    return int(DEFAULT_API_PRICING.get(endpoint, 0))


def record_usage(
    db: Session,
    *,
    key: ApiKey,
    endpoint: str,
    status: str = "success",
    request_id: str = "",
) -> ApiUsage:
    """记录一次调用。成功按 api_pricing 计费，失败不计费。"""
    amount = get_unit_price(db, endpoint) if status == "success" else 0
    row = ApiUsage(
        api_key_id=key.id,
        tenant_id=key.tenant_id,
        endpoint=endpoint,
        status=status,
        amount=amount,
        request_id=request_id,
    )
    db.add(row)
    key.last_used_at = utc_now_naive()
    db.add(key)
    db.commit()
    db.refresh(row)
    return row


# ===== 月度结算（T6-2） =====


def _month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """返回 (period_start, period_end) 半开区间 [start, end)。"""
    if month == 12:
        return datetime(year, 12, 1), datetime(year + 1, 1, 1)
    return datetime(year, month, 1), datetime(year, month + 1, 1)


def compute_monthly_bill(
    db: Session, *, api_key_id: int, year: int, month: int
) -> ApiBill | None:
    """聚合某个 Key 在指定月份的成功调用，生成/更新账单。无调用返回 None。"""
    start, end = _month_range(year, month)
    rows = (
        db.query(ApiUsage)
        .filter(
            ApiUsage.api_key_id == api_key_id,
            ApiUsage.status == "success",
            ApiUsage.created_at >= start,
            ApiUsage.created_at < end,
        )
        .all()
    )
    if not rows:
        return None

    line_items: dict[str, dict] = {}
    total = 0
    for r in rows:
        item = line_items.setdefault(r.endpoint, {"count": 0, "amount": 0})
        item["count"] += 1
        amount = int(r.amount)
        item["amount"] += amount
        total += amount

    key = db.get(ApiKey, api_key_id)
    bill = (
        db.query(ApiBill)
        .filter(
            ApiBill.api_key_id == api_key_id,
            ApiBill.period_start == start,
            ApiBill.period_end == end,
        )
        .first()
    )
    if bill is not None and bill.status == "paid":
        # 已出账/已支付账单不因重跑被覆盖（幂等出账，防止改坏已结算金额）
        return bill
    if bill is None:
        bill = ApiBill(
            api_key_id=api_key_id,
            tenant_id=key.tenant_id if key else 1,
            period_start=start,
            period_end=end,
            status="pending",
        )
        db.add(bill)
    bill.usage_count = len(rows)
    bill.total_amount = total
    bill.line_items = line_items
    db.commit()
    db.refresh(bill)
    return bill


def run_monthly_billing(db: Session, year: int, month: int) -> list[int]:
    """对当月有调用的全部 Key（含已停用/过期）生成账单。

    之前只结算 active Key：停用 Key 的未出账用量会被漏掉，导致应收流失；
    改为按当月有调用的 Key 出账，返回生成的 bill id 列表（空月份跳过）。
    """
    start, end = _month_range(year, month)
    key_ids = [
        row[0]
        for row in db.query(ApiUsage.api_key_id)
        .filter(ApiUsage.created_at >= start, ApiUsage.created_at < end)
        .distinct()
        .all()
    ]
    bill_ids: list[int] = []
    for key_id in key_ids:
        bill = compute_monthly_bill(db, api_key_id=key_id, year=year, month=month)
        if bill is not None:
            bill_ids.append(bill.id)
    return bill_ids
