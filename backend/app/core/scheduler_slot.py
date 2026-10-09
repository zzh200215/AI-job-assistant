"""跨副本的定时任务槽位（D175）：同一拍只让一个副本跑，抢不到就跳过。

为什么要它：`app/core/scheduler.py` 那 7 条任务是每个进程各排一遍的，副本数一旦 >1，
提醒会重发、月度账单会重复生成。今天两份 compose 都只有 1 个 backend，所以这条是**提前装**
的预防，不是放行扩副本——扩副本仍被 `backend/chroma_db` 那份嵌入式向量库拦住（一容器一进程
一份 Chroma，见 `tests/test_single_process_shape_is_pinned.py`）。

两条刻意的取舍，都有反面证据钉着：

1. **抢到的那一发不释放锁**。释放等于把"同一拍"的窗口重新打开给晚到的副本；代价是领到槽位
   的副本如果中途崩了，这一拍没人补——下一次触发自然换人领，最坏少跑一拍。
2. **Redis 不可用就 fail-open（各自都跑）**。单副本是今天签进树的形状，一次 Redis 抖动如果把
   判据写成 fail-closed，7 条任务会集体停摆，那比重复跑更糟。fail-open 的最坏结果就是回到
   "本条装上之前"的样子。

`slot_ttl_seconds` 不给每条任务手写数，而是从它自己的触发器算：写死的两个数迟早和触发器分叉
（本仓撞过好几轮的那件事）。窗口必须**严格小于**间隔，否则一个锁会把下一拍一起挡掉。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings

logger = logging.getLogger(__name__)

SLOT_KEY_PREFIX = "sched-slot"
MIN_SLOT_SECONDS = 30
MAX_SLOT_SECONDS = 900
SLOT_FRACTION = 0.2

_UNSET = object()

_client = None


def get_slot_client():
    """惰性建一条 redis 连接；没配 `REDIS_URL` 就返回 None（单副本形态下这是正常态，不是错误）。

    `from_url` 不立刻连，真正的失败落在 `claim_slot` 的那次 `SET` 上，所以 Redis 恢复后下一拍就能
    重新用上槽位——这里不缓存失败。
    """
    global _client
    if _client is None:
        url = (settings.REDIS_URL or "").strip()
        if not url:
            return None
        import redis

        _client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2.0, socket_connect_timeout=2.0)
    return _client


def reset_slot_client() -> None:
    """测试用：换掉 `REDIS_URL` 之后进程内那份客户端要能重来。"""
    global _client
    _client = None


def trigger_gap_seconds(trigger, *, now: datetime | None = None) -> float:
    """这条触发器相邻两拍之间隔多少秒。"""
    if isinstance(trigger, IntervalTrigger):
        return trigger.interval.total_seconds()
    if isinstance(trigger, CronTrigger):
        base = now or datetime.now(trigger.timezone)
        first = trigger.get_next_fire_time(None, base)
        second = trigger.get_next_fire_time(first, first)
        return (second - first).total_seconds()
    raise TypeError(f"未知的触发器类型，槽位窗口算不出来：{type(trigger)}")


def slot_ttl_seconds(trigger, *, now: datetime | None = None) -> int:
    """去重窗口：间隔的 `SLOT_FRACTION`，夹在 [30, 900] 秒之间。

    取间隔的一部分而不是全部，是因为多副本的同一拍只相差毫秒级——真要"锁满一个间隔"，
    那条锁就会自己去挡下一拍。
    """
    gap = trigger_gap_seconds(trigger, now=now)
    return int(max(MIN_SLOT_SECONDS, min(MAX_SLOT_SECONDS, gap * SLOT_FRACTION)))


def slot_violations(job_id: str, trigger, *, ttl_seconds: int | None = None) -> list[str]:
    """形状判据：窗口必须存在、为正、且严格小于这一条任务自己的间隔。"""
    ttl = slot_ttl_seconds(trigger) if ttl_seconds is None else ttl_seconds
    gap = trigger_gap_seconds(trigger)
    bad: list[str] = []
    if ttl <= 0:
        bad.append(f"{job_id}: 槽位窗口 {ttl}s 不是正数")
    elif ttl >= gap:
        bad.append(f"{job_id}: 槽位窗口 {ttl}s 不小于间隔 {gap}s，一把锁会把下一拍一起挡掉")
    return bad


def claim_slot(client, job_id: str, ttl_seconds: int) -> bool:
    """`SET NX EX`：领到槽位返回 True。

    `token` 只是让这把锁的值有辨识度（将来要换"只有持有者能释放"的语义时不必改键形状），
    今天没有任何路径释放它——这是上面第 1 条取舍。
    """
    if client is None:
        return True
    try:
        return bool(client.set(f"{SLOT_KEY_PREFIX}:{job_id}", uuid.uuid4().hex, nx=True, ex=ttl_seconds))
    except Exception as exc:
        logger.warning("槽位 %s 读写失败，按 fail-open 照跑：%s", job_id, exc)
        return True


def run_exclusive(job_id: str, ttl_seconds: int, fn: Callable[[], None], *, client: object = _UNSET) -> bool:
    """领到槽位才跑 `fn`。返回是否真的跑了（跳过也是一种正常结局，不是错误）。

    `client` 用哨兵而不是 `None`：`None` 表示"这台机器没有 redis"（fail-open 照跑），
    **不传**才去取进程内那一条连接。写成 `client is not None else get_slot_client()` 的话，
    显式传 `None` 的用例会被解析回活体 Redis —— D175 就是这么在开发机 Redis 里留下过键的。
    """
    resolved = get_slot_client() if client is _UNSET else client
    if not claim_slot(resolved, job_id, ttl_seconds):
        logger.info("槽位已被别的副本领走，本轮跳过：%s", job_id)
        return False
    fn()
    return True
