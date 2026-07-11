# -*- coding: utf-8 -*-
"""
定时任务调度器

基于 APScheduler 实现，在 FastAPI 启动时自动注册定时任务：
- 提醒检查（面试/Offer/投递跟进）: 每小时
- 新JD推送: 每天早上9点
"""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

# 同步锁超时：超过此时间未释放视为死锁，可强制重新执行
_SYNC_LOCK_TIMEOUT_MINUTES = 30


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

    # ---- 岗位数据源同步：每小时执行一次 ----
    scheduler.add_job(
        _run_job_data_source_sync,
        trigger=IntervalTrigger(hours=1),
        id="job_data_source_sync",
        name="岗位数据源自动同步",
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


def _calculate_backoff_minutes(fail_count: int, base_interval: int) -> int:
    """计算指数退避延迟（分钟）

    失败次数越多，下次同步延迟越长，避免频繁重试失败的数据源。
    最大延迟不超过 24 小时（1440 分钟）。
    """
    if fail_count <= 0:
        return base_interval

    # 指数退避：base_interval * 2^(fail_count-1)，上限 1440 分钟
    backoff = min(base_interval * (2 ** (fail_count - 1)), 1440)
    return backoff


def _run_job_data_source_sync():
    """自动同步到期的岗位数据源。"""
    from app.core.database import SessionLocal
    from app.models.job_data_source import JobDataSource
    from app.services.job_data_source.sync_service import SyncService

    db = SessionLocal()
    now = datetime.now(timezone.utc)
    lock_timeout = now - timedelta(minutes=_SYNC_LOCK_TIMEOUT_MINUTES)
    try:
        sources = (
            db.query(JobDataSource)
            .filter(
                JobDataSource.status == 1,
                JobDataSource.sync_interval > 0,
                (JobDataSource.next_sync_at <= now) | (JobDataSource.next_sync_at.is_(None)),
                (JobDataSource.sync_lock_at <= lock_timeout) | (JobDataSource.sync_lock_at.is_(None)),
            )
            .all()
        )

        total = len(sources)
        success = 0
        failed = 0
        for source in sources:
            try:
                source.sync_lock_at = datetime.now(timezone.utc)
                db.commit()
                service = SyncService(db, user_id=source.user_id)
                log = service.sync(source)
                if log.status in ("success", "partial"):
                    success += 1
                    # 成功后重置失败计数
                    source.fail_count = 0
                    # 按原始间隔计算下次同步时间
                    if source.sync_interval and source.sync_interval > 0:
                        source.next_sync_at = now + timedelta(minutes=source.sync_interval)
                else:
                    failed += 1
                    # 失败后使用指数退避
                    source.fail_count = (source.fail_count or 0) + 1
                    backoff_minutes = _calculate_backoff_minutes(source.fail_count, source.sync_interval)
                    source.next_sync_at = now + timedelta(minutes=backoff_minutes)
                    logger.warning(
                        "Sync failed for source %s (fail_count=%d), next sync in %d minutes",
                        source.id, source.fail_count, backoff_minutes
                    )
            except Exception as e:
                failed += 1
                source.fail_count = (source.fail_count or 0) + 1
                source.last_error_msg = str(e)[:500]
                source.sync_lock_at = None
                # 失败后使用指数退避
                backoff_minutes = _calculate_backoff_minutes(source.fail_count, source.sync_interval)
                source.next_sync_at = now + timedelta(minutes=backoff_minutes)
                db.commit()
                logger.error(
                    "Job data source sync failed for source %s (fail_count=%d): %s, next sync in %d minutes",
                    source.id, source.fail_count, e, backoff_minutes
                )

        logger.info("Job data source sync completed: %d sources, %d success, %d failed", total, success, failed)
    except Exception as e:
        logger.error("Job data source sync job failed: %s", e)
    finally:
        db.close()
