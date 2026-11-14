"""Shared runners for orchestration strategies and legacy wrappers."""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.llm_quota import set_billing_user
from app.models.agent import AgentStepLog, AgentTask
from app.models.agent_run import AgentMessage, AgentRun
from app.orchestration.registry import DEFAULT_REGISTRY
from app.orchestration.strategies import StrategyFactory
from app.services.orchestration_backend import (
    OrchestrationUnavailable,
    RedisQueueOrchestrationBackend,
    TaskPayload,
    get_orchestration_backend,
    health_snapshot,
)
from app.utils.time_helper import utc_now, utc_now_naive

logger = logging.getLogger(__name__)

_BACKEND = None


def _get_backend():
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = get_orchestration_backend()
    return _BACKEND


def _ensure_dispatchable(backend) -> None:
    """收单之前先确认"有人会跑它"。没有人就抛 `OrchestrationUnavailable`，由接口翻成 503。

    改前的形状是"照收不误"：`submit` 只往 list 里 LPUSH 一行，接口立刻回"智能分析已启动"。
    2026-11-14 的实测就是被这一条坑到 —— `.env` 写着 `ORCHESTRATION_BACKEND=redis_queue`
    而机器上没有任何 worker 进程，`/analysis/full` 回 200 + task_id，任务在队列里躺了 733 秒
    （`steps=0`、`prompt_trace=0`），候选人屏幕上只有一个永远转的圈。

    宁可当场拒绝并说清怎么修，也不要发一个没人会跑的任务号：拒绝是可恢复的，转圈不是。
    """
    if not isinstance(backend, RedisQueueOrchestrationBackend):
        # 线程后端的消费者就是本进程，进程活着就有人跑 —— 这里没有可判的东西。
        return
    health = backend.queue_health()
    if not health.get("ok", False):
        raise OrchestrationUnavailable(
            f"分析服务暂不可用：任务队列连不上（{health.get('error') or 'Redis 不可用'}），请稍后重试"
        )
    if not health.get("worker_alive", False):
        logger.error(
            "拒绝创建分析任务：redis_queue 后端没有活着的 worker（queue=%s length=%s）。"
            "启动：cd backend && ./.venv/Scripts/python.exe -m scripts.run_orchestration_worker",
            health.get("queue_name"),
            health.get("queue_length"),
        )
        raise OrchestrationUnavailable(
            "分析服务暂不可用：后台任务队列没有 worker 在消费，创建了也没人执行。"
            "请先启动编排 worker（`python -m scripts.run_orchestration_worker`）后重试"
        )


def _naive(value):
    """DB 读回的时间是 naive，与 `utc_now()` 的 aware 值相减会 TypeError。"""
    if value is None or value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)


def _run_task_payload(payload: TaskPayload) -> None:
    """唯一的任务执行入口：线程后端和 Redis worker 跑的是同一份代码。"""
    # 计费身份必须在这里显式设：`logging_utils` 那套上下文是 `threading.local`，
    # worker 线程里取不到请求上下文的 user，不设就等于编排的花费全员不扣。
    set_billing_user(payload.user_id)
    db = SessionLocal()
    try:
        strategy = StrategyFactory.create(payload.strategy_name, DEFAULT_REGISTRY)
        result = strategy.run(
            payload.task_id,
            payload.resume_id,
            payload.jd_id,
            payload.user_id,
            db,
            run_id=payload.run_id,
        )

        if result.get("status") == "failed":
            task = db.get(AgentTask, payload.task_id)
            if task and task.status == "running":
                task.status = "failed"
                task.error_msg = result.get("error", "orchestration failed")[:500]
                task.end_time = utc_now()
                db.add(task)
                db.commit()
    except Exception as exc:
        traceback.print_exc()
        try:
            task = db.get(AgentTask, payload.task_id)
            if task and task.status == "running":
                task.status = "failed"
                task.error_msg = str(exc)[:500]
                task.end_time = utc_now()
                db.add(task)
                db.commit()
            if payload.run_id:
                # 策略在跑到收尾之前炸了：run 不能永远停在 running
                run = db.get(AgentRun, payload.run_id)
                if run and run.status not in {"completed", "failed", "cancelled"}:
                    run.status = "failed"
                    run.error_msg = str(exc)[:500]
                    run.end_time = utc_now()
                    db.add(run)
                    db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def run_redis_worker(stop_event=None) -> None:
    """Run the Redis queue worker loop in a standalone process."""
    backend = get_orchestration_backend()
    if not isinstance(backend, RedisQueueOrchestrationBackend):
        raise RuntimeError("ORCHESTRATION_BACKEND is not redis_queue")
    backend.worker_loop(_run_task_payload, stop_event=stop_event)


def get_queue_health() -> dict:
    return health_snapshot()


def create_task(
    resume_id: int,
    jd_id: int,
    user_id: int | None = None,
    *,
    strategy_name: str | None = None,
    retry_of_task_id: int | None = None,
    db: Session | None = None,
) -> int:
    """Create an AgentTask row and return its id."""
    session = db or SessionLocal()
    owns_session = db is None
    try:
        task = AgentTask(
            user_id=user_id or 0,
            resume_id=resume_id,
            jd_id=jd_id,
            strategy_name=strategy_name,
            retry_of_task_id=retry_of_task_id,
            status="running",
            start_time=utc_now(),
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        return task.id
    finally:
        if owns_session:
            session.close()


def run_strategy_async(
    strategy_name: str,
    resume_id: int,
    jd_id: int,
    user_id: int | None = None,
    *,
    retry_of_task_id: int | None = None,
) -> int:
    """Create a task and execute the given strategy using the configured backend."""
    backend = _get_backend()
    _ensure_dispatchable(backend)
    task_id = create_task(
        resume_id,
        jd_id,
        user_id=user_id,
        strategy_name=strategy_name,
        retry_of_task_id=retry_of_task_id,
    )
    try:
        start_strategy_thread(strategy_name, task_id, resume_id, jd_id, user_id=user_id)
    except Exception as exc:
        # 投递这一步失败的话，行已经落库了：不收口就是一个新的"永远 running"。
        fail_task(task_id, f"任务投递失败：{exc}")
        raise OrchestrationUnavailable(f"任务投递失败：{exc}") from exc
    return task_id


def start_strategy_thread(
    strategy_name: str,
    task_id: int,
    resume_id: int,
    jd_id: int,
    user_id: int | None = None,
):
    """Run a strategy in the configured backend for an existing task."""
    payload = TaskPayload(
        strategy_name=strategy_name,
        task_id=task_id,
        resume_id=resume_id,
        jd_id=jd_id,
        user_id=user_id,
    )
    return _get_backend().submit(payload, _run_task_payload)


def fail_task(task_id: int, message: str, *, db: Session | None = None) -> None:
    """把一条还没收口的任务就地判失败。投递失败与"没人消费"都走这一个出口。"""
    session = db or SessionLocal()
    owns_session = db is None
    try:
        task = session.get(AgentTask, task_id)
        if not task or task.status != "running":
            return
        task.status = "failed"
        task.error_msg = message[:500]
        task.end_time = utc_now()
        session.add(task)
        session.commit()
    except Exception:  # noqa: BLE001 - 收口失败不能盖掉真正要抛给调用方的那个原因
        session.rollback()
        logger.warning("收口任务失败 task_id=%s", task_id, exc_info=True)
    finally:
        if owns_session:
            session.close()


def create_legacy_run(
    resume_id: int,
    jd_id: int,
    user_request: str,
    task_id: int | None = None,
) -> int:
    """Create the legacy AgentRun row and return its id."""
    db = SessionLocal()
    try:
        run = AgentRun(
            resume_id=resume_id or 0,
            jd_id=jd_id or 0,
            task_id=task_id,
            user_request=user_request,
            status="running",
            start_time=utc_now(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id
    finally:
        db.close()


def start_legacy_layered_thread(
    run_id: int,
    task_id: int,
    resume_id: int,
    jd_id: int,
    user_id: int | None = None,
):
    """Execute the layered strategy for a legacy AgentRun in background.

    run_id 放进 payload 而不是包进闭包：Redis 后端只搬运 payload，闭包会被丢弃，
    于是 worker 会为同一个任务另建一条 run —— 客户端轮询的那条永远停在 running、
    明细里一条消息都没有。
    """
    payload = TaskPayload(
        strategy_name="layered",
        task_id=task_id,
        resume_id=resume_id,
        jd_id=jd_id,
        user_id=user_id,
        run_id=run_id,
    )
    return _get_backend().submit(payload, _run_task_payload)


def _last_progress_times(session: Session, task_ids: list[int]) -> dict[int, datetime]:
    """每个任务"最后一次被人写过"的时间：步骤日志行 + 节点消息行（经 agent_run 关联）。

    取 coalesce(完成, 开始, 建行走) 是因为步骤跑完会回填 completed_at，而正在跑的步骤只有
    started_at/create_time——两种都要算成活动，否则一个刚开工的长步骤会被看成静止。
    """

    def _merge(rows: list[tuple[int, datetime | None]]) -> None:
        for task_id, when in rows:
            if task_id is None or when is None:
                continue
            prev = found.get(task_id)
            if prev is None or when > prev:
                found[task_id] = when

    found: dict[int, datetime] = {}
    _merge(
        session.query(
            AgentStepLog.task_id,
            func.max(func.coalesce(AgentStepLog.completed_at, AgentStepLog.started_at, AgentStepLog.create_time)),
        )
        .filter(AgentStepLog.task_id.in_(task_ids))
        .group_by(AgentStepLog.task_id)
        .all()
    )
    _merge(
        session.query(
            AgentRun.task_id,
            func.max(func.coalesce(AgentMessage.completed_at, AgentMessage.started_at, AgentMessage.create_time)),
        )
        .join(AgentMessage, AgentMessage.run_id == AgentRun.id)
        .filter(AgentRun.task_id.in_(task_ids))
        .group_by(AgentRun.task_id)
        .all()
    )
    return found


def mark_stale_running_tasks_failed(
    *,
    older_than_minutes: int | None = None,
    db: Session | None = None,
) -> int:
    """Fail running tasks that stopped making progress.

    判据是"最后一次活动"，不是"多久以前开始"。`AgentTask.start_time` 在建任务那一刻就写死了，
    而任务完全可能正在**另一个进程**里跑：`ORCHESTRATION_BACKEND=redis_queue` 时 worker 是独立
    进程，只重启 web（`--reload`、滚动发布、崩掉拉起）就会把 worker 手里跑了 30 分钟以上的任务
    一律判成 failed——前端 `agentTaskPolling` 一见 failed 就停止轮询并报错，于是候选人拿到一个
    "失败"，而分析在几秒后正常完成并落库。现在要求步骤日志与消息行也一起静默才收口。
    """
    minutes = older_than_minutes if older_than_minutes is not None else settings.ORCHESTRATION_STALE_TASK_MINUTES
    cutoff = utc_now_naive() - timedelta(minutes=max(1, int(minutes or 30)))
    session = db or SessionLocal()
    owns_session = db is None
    try:
        candidates = session.query(AgentTask).filter(AgentTask.status == "running", AgentTask.start_time < cutoff).all()
        if not candidates:
            return 0
        # cutoff 用 naive：DB 读回的 DateTime 是 naive，与 aware 值比较会 TypeError。
        last_progress = _last_progress_times(session, [task.id for task in candidates])
        stale: list[AgentTask] = []
        for task in candidates:
            activity = max(when for when in (task.start_time, last_progress.get(task.id)) if when is not None)
            if activity >= cutoff:
                continue
            task.status = "failed"
            task.error_msg = (
                f"任务超过 {minutes} 分钟没有新的步骤写入"
                f"（最后一次活动 {activity.isoformat(sep=' ', timespec='seconds')}），按中断收口"
            )
            task.end_time = utc_now()
            session.add(task)
            stale.append(task)
        if stale:
            session.commit()
            logger.warning("Marked %s stale running agent tasks as failed", len(stale))
        return len(stale)
    finally:
        if owns_session:
            session.close()


def _has_any_progress(db: Session, task_id: int) -> bool:
    """这条任务有没有"有人开始跑它"的痕迹：步骤行，或挂在它下面的节点消息。

    两条都要查：分层策略是先建 running 步骤再并发，legacy 路径可能先落节点消息。
    只在 "已经超过启动超时" 时才走到这里，所以这两次查询不落在热路径上。
    """
    if db.query(AgentStepLog.id).filter(AgentStepLog.task_id == task_id).first():
        return True
    return bool(
        db.query(AgentMessage.id)
        .join(AgentRun, AgentMessage.run_id == AgentRun.id)
        .filter(AgentRun.task_id == task_id)
        .first()
    )


def _consumer_state(backend) -> tuple[bool, str]:
    """(有没有活着的消费者, 给用户看的现场)。线程后端恒为"有"。

    线程后端的消费者就是本进程：任务投进本地线程池，进程活着就一定会有人跑它
    （哪怕要排队等 `ORCHESTRATION_MAX_WORKERS` 释放）。这一点很重要 —— 离线时
    它让"从没开始"这条判据对线程后端**完全不起作用**，否则一次并发排队就会被判死。
    """
    if not isinstance(backend, RedisQueueOrchestrationBackend):
        return True, ""
    health = backend.queue_health()
    if not health.get("ok", False):
        return False, f"任务队列连不上（{(health.get('error') or '')[:120]}）"
    if health.get("worker_alive", False):
        return True, ""
    queued = int(health.get("queue_length") or 0)
    return False, f"任务队列里没有活着的 worker（心跳键不存在，当前 {queued} 条任务在等它）"


def converge_running_task(
    task: AgentTask,
    db: Session | None = None,
    *,
    backend=None,
    now: datetime | None = None,
) -> str | None:
    """把"没有人会再推进"的 running 任务就地收口成 failed；返回收口原因（没动就是 None）。

    补的是 `mark_stale_running_tasks_failed` 管不到、而在 D6 实测里真把用户等了 733 秒的那个洞：
    它的判据是"最后一次活动超过 30 分钟"，可**从没开始过的任务根本没有活动行** ——
    只要进程不重启，它就永远停在 running，前端就永远转圈。

    判据刻意收得很窄，只收"确定没有人会跑它"的那种：
    1. 没有步骤行、也没有节点消息（worker 还没拿到它）；
    2. 已经过了 `ORCHESTRATION_START_TIMEOUT_MINUTES`；
    3. 并且确认当前**没有活着的消费者**（Redis 后端看 worker 心跳；线程后端恒有）。

    第 3 条不能省：worker 活着时它只是排在别人后面，判死会在几分钟后与真正的完成撞车
    —— 任务被标成 failed，随后又落了一条 AnalysisRecord，两处说法不一致。

    代价是每次调用只多一次 Redis 健康查询，且只在"已经超过启动超时、又没有任何进度行"
    时才发生 —— 正常态下这条路一次都不会走到。
    """
    if task is None or task.status != "running" or task.start_time is None:
        return None

    timeout = max(1, int(settings.ORCHESTRATION_START_TIMEOUT_MINUTES or 2))
    current = now or utc_now_naive()
    age = current - _naive(task.start_time)
    if age < timedelta(minutes=timeout):
        return None
    session = db or SessionLocal()
    owns_session = db is None
    try:
        if _has_any_progress(session, task.id):
            # 已经开始了：剩下的交给"开始后静默"那条判据（30 分钟、按最后一次活动）。
            return None
        alive, note = _consumer_state(backend or _get_backend())
        if alive:
            return None
        reason = f"排队 {timeout} 分钟仍未开始执行：{note}。任务没有跑过，按未启动收口"
        task.status = "failed"
        task.error_msg = reason[:500]
        task.end_time = utc_now()
        session.add(task)
        session.commit()
        logger.warning("converged never-started agent task id=%s: %s", task.id, reason)
        return reason
    except Exception:
        session.rollback()
        logger.warning("收口未启动任务失败 task_id=%s", getattr(task, "id", None), exc_info=True)
        return None
    finally:
        if owns_session:
            session.close()


def shutdown_orchestration_executor() -> None:
    """Stop accepting new background work during application shutdown."""
    backend = _get_backend()
    backend.shutdown()


def cancel_task(task_id: int, user_id: int, *, db: Session | None = None) -> AgentTask | None:
    """Mark a task as cancelled if it has not finished yet."""
    session = db or SessionLocal()
    owns_session = db is None
    try:
        task = session.get(AgentTask, task_id)
        if not task or task.user_id != user_id:
            return None
        if task.status in {"completed", "failed", "partial", "cancelled"}:
            return task

        task.status = "cancelled"
        task.error_msg = "Cancelled by user"
        task.end_time = utc_now()
        session.add(task)
        session.commit()
        session.refresh(task)
        return task
    finally:
        if owns_session:
            session.close()


def retry_task(
    task_id: int,
    user_id: int,
    fallback_strategy: str,
    *,
    db: Session | None = None,
) -> AgentTask | None:
    """Create a fresh retry task from an existing terminal task and start it."""
    session = db or SessionLocal()
    owns_session = db is None
    try:
        task = session.get(AgentTask, task_id)
        if not task or task.user_id != user_id:
            return None
        if task.status in {"pending", "running"}:
            return task

        backend = _get_backend()
        # 重试也是收单：没有消费者时同样不该发一个新的任务号。
        _ensure_dispatchable(backend)
        strategy_name = task.strategy_name or fallback_strategy
        new_task_id = create_task(
            task.resume_id,
            task.jd_id,
            user_id=user_id,
            strategy_name=strategy_name,
            retry_of_task_id=task.id,
            db=session,
        )
        try:
            start_strategy_thread(strategy_name, new_task_id, task.resume_id, task.jd_id, user_id=user_id)
        except Exception as exc:
            fail_task(new_task_id, f"任务投递失败：{exc}", db=session)
            raise OrchestrationUnavailable(f"任务投递失败：{exc}") from exc
        logger.info(
            "Task retried original_task_id=%s new_task_id=%s strategy=%s",
            task.id,
            new_task_id,
            strategy_name,
        )
        return session.get(AgentTask, new_task_id)
    finally:
        if owns_session:
            session.close()
