"""
定时任务调度器

基于 APScheduler 实现，在 FastAPI 启动时自动注册定时任务：
- 提醒检查（面试/Offer/投递跟进）: 每小时
- 新JD推送: 每天早上9点
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        # 所有任务都是同步 DB 操作，用线程池调度器而非 AsyncIOScheduler：
        # 避免长任务（提醒扫描/JD 推送/月度结算）阻塞 FastAPI 事件循环。
        _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    return _scheduler


def start_scheduler() -> None:
    """启动调度器并注册定时任务"""
    if not settings.RUN_SCHEDULER:
        logger.info("RUN_SCHEDULER=false，跳过启动定时任务调度器")
        return

    scheduler = get_scheduler()

    # ---- 提醒检查任务：每小时执行一次 ----
    scheduler.add_job(
        _run_reminder_check,
        trigger=IntervalTrigger(hours=1),
        id="reminder_check",
        name="面试/Offer/投递跟进提醒",
        replace_existing=True,
    )

    # ---- 新JD推送任务：每天早上9点 ----
    scheduler.add_job(
        _run_new_jd_push,
        trigger=CronTrigger(hour=9, minute=0),
        id="new_jd_push",
        name="新JD推送",
        replace_existing=True,
    )

    # ---- 目标统计刷新：每天凌晨3点 ----
    scheduler.add_job(
        _run_target_stats_refresh,
        trigger=CronTrigger(hour=3, minute=0),
        id="target_stats_refresh",
        name="求职目标统计刷新",
        replace_existing=True,
    )

    # ---- 运维告警评估：每 5 分钟更新一次，供管理员跟进与审计 ----
    scheduler.add_job(
        _run_operational_alert_evaluation,
        trigger=IntervalTrigger(minutes=5),
        id="operational_alert_evaluation",
        name="运维告警评估",
        replace_existing=True,
    )

    # ---- 租户计费扫描：每小时一次（T4-3） ----
    scheduler.add_job(
        _run_tenant_billing_check,
        trigger=IntervalTrigger(hours=1),
        id="tenant_billing_check",
        name="租户到期停用/恢复",
        replace_existing=True,
    )

    # ---- 外部 API 月度结算：每月 1 日 02:30（T6-2） ----
    scheduler.add_job(
        _run_external_api_monthly_billing,
        trigger=CronTrigger(hour=2, minute=30, day=1),
        id="external_api_monthly_billing",
        name="外部 API 月度账单生成",
        replace_existing=True,
    )

    # ---- 岗位向量补齐：每 30 分钟一次，让候选人那次请求不必为全库付 embedding ----
    scheduler.add_job(
        _run_job_embedding_sync,
        trigger=IntervalTrigger(minutes=30),
        id="job_embedding_sync",
        name="岗位向量增量同步",
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


def _run_tenant_billing_check():
    """租户计费扫描（T4-3）：每小时执行一次。"""
    from app.core.database import SessionLocal
    from app.services.subscription_service import run_tenant_billing_check

    db = SessionLocal()
    try:
        stats = run_tenant_billing_check(db)
        logger.info("Tenant billing check completed: %s", stats)
    except Exception as exc:
        db.rollback()
        logger.error("Tenant billing check failed: %s", exc)
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
