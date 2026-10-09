"""
定时任务调度器

基于 APScheduler 实现，在 FastAPI 启动时自动注册定时任务：
- 提醒检查（面试/Offer/投递跟进）: 每小时
- 新JD推送: 每天早上9点

任务清单集中在 `scheduled_job_specs()` 一个表里（D175）：`start_scheduler` 与守卫测试读同一份，
每条的跨副本去重窗口由它自己的触发器算出来（`app/core/scheduler_slot.py`），不手写第二个数。
"""

import logging
from collections.abc import Callable
from functools import partial
from typing import NamedTuple

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.scheduler_slot import run_exclusive, slot_ttl_seconds

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


class JobSpec(NamedTuple):
    job_id: str
    name: str
    trigger: CronTrigger | IntervalTrigger
    fn: Callable[[], None]


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        # 所有任务都是同步 DB 操作，用线程池调度器而非 AsyncIOScheduler：
        # 避免长任务（提醒扫描/JD 推送/月度结算）阻塞 FastAPI 事件循环。
        _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    return _scheduler


def scheduled_job_specs() -> list[JobSpec]:
    """7 条定时任务的唯一清单。加一条就改这里，别在 `start_scheduler` 里另写一次 add_job。"""
    return [
        # ---- 提醒检查任务：每小时执行一次 ----
        JobSpec("reminder_check", "面试/Offer/投递跟进提醒", IntervalTrigger(hours=1), _run_reminder_check),
        # ---- 新JD推送任务：每天早上9点 ----
        JobSpec("new_jd_push", "新JD推送", CronTrigger(hour=9, minute=0), _run_new_jd_push),
        # ---- 目标统计刷新：每天凌晨3点 ----
        JobSpec("target_stats_refresh", "求职目标统计刷新", CronTrigger(hour=3, minute=0), _run_target_stats_refresh),
        # ---- 运维告警评估：每 5 分钟一次，供管理员跟进与审计 ----
        JobSpec(
            "operational_alert_evaluation",
            "运维告警评估",
            IntervalTrigger(minutes=5),
            _run_operational_alert_evaluation,
        ),
        # ---- 外部 API 月度结算：每月 1 日 02:30（T6-2） ----
        # 2026-10-06 真删企业侧第六增量（D136）：这里原来还挂着一小时一次的
        # `_run_tenant_billing_check`（遍历 `organization` 做到期停用/续费恢复）。organization 0 行，
        # 所以那个循环从来没进过循环体；候选人那侧的订阅它也不碰（它按 `tenant_id == org.id` 收窄）。
        JobSpec(
            "external_api_monthly_billing",
            "外部 API 月度账单生成",
            CronTrigger(hour=2, minute=30, day=1),
            _run_external_api_monthly_billing,
        ),
        # ---- 岗位向量补齐：每 30 分钟一次，让候选人那次请求不必为全库付 embedding ----
        JobSpec("job_embedding_sync", "岗位向量增量同步", IntervalTrigger(minutes=30), _run_job_embedding_sync),
        # ---- 滞留逐题评分重投：每 10 分钟一次（D163） ----
        JobSpec(
            "interview_evaluation_requeue",
            "滞留逐题评分重投",
            IntervalTrigger(minutes=10),
            _run_interview_evaluation_requeue,
        ),
    ]


def start_scheduler() -> None:
    """启动调度器并注册定时任务"""
    if not settings.RUN_SCHEDULER:
        logger.info("RUN_SCHEDULER=false，跳过启动定时任务调度器")
        return

    scheduler = get_scheduler()
    for spec in scheduled_job_specs():
        scheduler.add_job(
            partial(run_exclusive, spec.job_id, slot_ttl_seconds(spec.trigger), spec.fn),
            trigger=spec.trigger,
            id=spec.job_id,
            name=spec.name,
            replace_existing=True,
        )

    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))


def shutdown_scheduler() -> None:
    """关闭调度器"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")


# ============================================================
# 定时任务实现
# ============================================================


def _run_reminder_check():
    """执行提醒检查（面试/Offer/投递跟进）"""
    from app.core.database import SessionLocal
    from app.services.reminder_service import check_and_send_reminders

    db = SessionLocal()
    try:
        stats = check_and_send_reminders(db)
        logger.info("Reminder check completed: %s", stats)
    except Exception as e:
        logger.error("Reminder check failed: %s", e)
    finally:
        db.close()


def _run_new_jd_push():
    """为所有活跃用户推送新JD"""
    from app.core.database import SessionLocal
    from app.models.job_target import JobTarget
    from app.services.reminder_service import send_new_jd_notifications

    db = SessionLocal()
    try:
        # 获取有活跃目标的用户
        user_ids = {row[0] for row in db.query(JobTarget.user_id).filter(JobTarget.status == "active").distinct().all()}

        total_notifications = 0
        for uid in user_ids:
            try:
                count = send_new_jd_notifications(db, uid)
                total_notifications += count
            except Exception as e:
                logger.error("JD push failed for user %s: %s", uid, e)

        logger.info("JD push completed: %d users, %d notifications", len(user_ids), total_notifications)
    except Exception as e:
        logger.error("JD push job failed: %s", e)
    finally:
        db.close()


def _run_target_stats_refresh():
    """刷新所有求职目标的冗余统计字段"""
    from app.core.database import SessionLocal
    from app.models.job_target import JobTarget

    db = SessionLocal()
    try:
        targets = db.query(JobTarget).filter(JobTarget.status == "active").all()
        from app.api.job_target import _refresh_target_stats

        for target in targets:
            try:
                _refresh_target_stats(target, db)
            except Exception as e:
                logger.error("Target stats refresh failed for target %s: %s", target.id, e)

        logger.info("Target stats refresh completed: %d targets", len(targets))
    except Exception as e:
        logger.error("Target stats refresh job failed: %s", e)
    finally:
        db.close()


def _run_job_embedding_sync():
    """Embed new or edited postings ahead of any candidate asking for them."""
    from app.core.database import SessionLocal
    from app.services.jd_embedding_service import sync_active_job_embeddings

    db = SessionLocal()
    try:
        stats = sync_active_job_embeddings(db)
        if stats["embedded"] or stats["failed"]:
            logger.info(
                "Job embedding sync: scanned=%d reused=%d embedded=%d failed=%d",
                stats["scanned"],
                stats["reused"],
                stats["embedded"],
                stats["failed"],
            )
    except Exception as e:
        logger.error("Job embedding sync failed: %s", e)
    finally:
        db.close()


def _run_operational_alert_evaluation():
    """Persist current platform risks without making external provider calls."""
    from app.api.system import build_operational_alert_snapshot
    from app.core.database import SessionLocal
    from app.services.operational_alert_service import evaluate_operational_alerts

    db = SessionLocal()
    try:
        alerts = evaluate_operational_alerts(db, **build_operational_alert_snapshot())
        logger.info("Operational alert evaluation completed: %d active alerts", len(alerts))
    except Exception as exc:
        logger.error("Operational alert evaluation failed: %s", exc)
        db.rollback()
    finally:
        db.close()


def _run_interview_evaluation_requeue():
    """捡回"提交它的进程已经没了"的逐题评分。

    D175 之后这条与其余 6 条一样先领跨副本槽位，正常态下每拍只有一个副本在扫。但认领仍然必须
    能抗并发：槽位是 fail-open 的（`REDIS_URL` 没配或 Redis 抖动时大家各自扫），所以 `_claim_status`
    用一次必然改变 status 的条件 UPDATE 当凭证，rowcount=0 的一方就知道别人抢到了，
    同一道题不会付两遍模型钱。
    """
    from app.core.database import SessionLocal
    from app.services.interview_evaluation_service import requeue_stale_turn_evaluations

    db = SessionLocal()
    try:
        count = requeue_stale_turn_evaluations(db=db)
        if count:
            logger.info("Interview evaluation requeue: %d stale turns resubmitted", count)
    except Exception as e:
        logger.error("Interview evaluation requeue failed: %s", e)
        db.rollback()
    finally:
        db.close()


def _run_external_api_monthly_billing():
    """外部 API 月度结算（T6-2）：每月 1 日对上月用量聚合出账。"""
    from datetime import datetime

    from app.core.database import SessionLocal
    from app.services.api_key_service import run_monthly_billing

    now = datetime.now()
    year, month = now.year, now.month - 1
    if month == 0:
        year, month = year - 1, 12

    db = SessionLocal()
    try:
        bill_ids = run_monthly_billing(db, year, month)
        logger.info("External API monthly billing completed: %d bills for %04d-%02d", len(bill_ids), year, month)
    except Exception as exc:
        db.rollback()
        logger.error("External API monthly billing failed: %s", exc)
    finally:
        db.close()
