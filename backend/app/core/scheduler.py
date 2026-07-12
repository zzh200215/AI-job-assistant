# -*- coding: utf-8 -*-
"""
定时任务调度器

基于 APScheduler 实现，在 FastAPI 启动时自动注册定时任务：
- 提醒检查（面试/Offer/投递跟进）: 每小时
- 新JD推送: 每天早上9点
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
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
    from app.models.user import User
    from app.services.reminder_service import send_new_jd_notifications

    db = SessionLocal()
    try:
        # 获取有活跃目标的用户
        user_ids = {
            row[0] for row in
            db.query(JobTarget.user_id)
            .filter(JobTarget.status == "active")
            .distinct()
            .all()
        }

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
