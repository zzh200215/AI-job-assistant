"""D226: the durable row behind `POST /jobs/batch-import`, so an import reports progress instead of
hanging the request.

Why a table at all: importing a CSV/JSON file is "read up to 10MB, parse it, then one ORM object
per row plus a commit". Measured on this machine (D219): 50 rows = 20 ms, 300 rows = 99 ms,
2000 rows = **677 ms** of that handler holding a worker thread — and while it ran, every other
request that needed the event loop waited behind it. A 10MB file has no reason to be one request.

The row is also where a candidate can ask "how far did you get" and "stop". Counters live here, not
in the HTTP call.

Why not the two orphan tables that already sit in some databases: `job_import_batch` and
`job_sync_log` came with the enterprise-side code that left the tree, and **the migrations that
created them left with it** — D223 measured that a fresh `alembic upgrade head` produces neither.
Building on them would mean code whose tables the chain cannot create (works on an old dev DB, breaks
on any new one), which is the same price as a new table plus a name collision on the old databases.
"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, SmallInteger, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now


class JobImportTask(Base):
    """One background batch-import run for one uploaded file."""

    __tablename__ = "job_import_task"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True, comment="提交人")
    file_name = Column(String(200), nullable=False, comment="候选人给的文件名")
    source = Column(String(50), nullable=False, default="imported", comment="落库岗位行的 source")
    # pending = 投了还没起跑；running = 正在逐行入库；completed / failed / canceled = 终态。
    # 口径与 rewrite_suggestion_job / interview 那一族相同：前两个都算"还没出结果"。
    status = Column(String(20), nullable=False, default="pending", index=True)
    claimed_at = Column(DateTime, nullable=True, comment="领走这一行的时刻；租约让同一行只有一个赢家")
    finished_at = Column(DateTime, nullable=True, comment="进入终态的时刻，清理按它算保留期")

    total = Column(Integer, nullable=False, default=0, comment="解析出来的行数（分母）；0 = 还没解析")
    done = Column(Integer, nullable=False, default=0, comment="已经处理完的行数（含被跳过的）")
    created = Column(Integer, nullable=False, default=0, comment="真进了 job_description 的行数")
    skipped = Column(Integer, nullable=False, default=0, comment="缺必填字段而被跳过的行数")
    # 前若干条失败/跳过的原因，给排障看。整体失败的原因在 error_msg，不混在这里。
    problems = Column(JSON, comment="逐行问题的前 N 条：{row, reason}")

    error = Column(SmallInteger, nullable=False, default=0, comment="1 = 这一发失败了")
    error_msg = Column(Text, comment="失败原因；**不上客户端**，只对内可查")
    create_time = Column(DateTime, default=utc_now, nullable=False, index=True)
    update_time = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    def to_progress(self) -> dict:
        """给轮询端点的载荷。**没有 `error_msg`**：那句可能带上文件内容或库里的报错细节。"""
        return {
            "job_id": self.id,
            "file_name": self.file_name,
            "status": self.status,
            "total": self.total,
            "done": self.done,
            "created": self.created,
            "skipped": self.skipped,
            "problems": (self.problems or [])[:10],
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
