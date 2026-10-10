"""D200: durable row behind the rewrite-suggestion call, so the HTTP request no longer waits on the LLM.

Why a table at all: `build_rewrite_suggestions` is one ~10s (measured, thinking disabled) to
~90s (measured, thinking enabled) provider call. As a synchronous endpoint it held one of the 20
anyio worker threads for that whole time (`core/threadpool.py` pins the ceiling to the DB pool),
and its answer had nowhere to go. The invariant this endpoint sells to the candidate is
"suggestions never touch your resume" — that is about `parsed_json`, not about storing nothing,
so the payload lives here instead. Nothing in this table is read back into a resume.
"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, SmallInteger, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now


class RewriteSuggestionJob(Base):
    """One background rewrite-suggestion run for one (resume, optional JD) pair."""

    __tablename__ = "rewrite_suggestion_job"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True, comment="提交人")
    resume_id = Column(BigInteger, nullable=False, index=True, comment="简历ID")
    jd_id = Column(BigInteger, comment="目标岗位ID，可空（这一发的 jd_id 本来就是可选）")
    # pending = 投了还没起跑；running = 起了跑；completed / failed = 终态。
    # 只有这四态，`pending` 与 `running` 都算"还没出结果"（口径与 interview 那一族一致）。
    status = Column(String(20), nullable=False, default="pending", index=True)
    claimed_at = Column(DateTime, nullable=True, comment="谁在什么时候领走这一行；租约让同一行只有一个赢家")
    finished_at = Column(DateTime, nullable=True, comment="进入终态的时刻，清理按它算保留期")
    block_total = Column(Integer, nullable=False, default=0, comment="可供改写的文本块数")
    suggestions = Column(JSON, comment="通过校验的建议；未落库的文本只活在这里")
    rejected = Column(JSON, comment="被逐块校验拒掉的条目与理由，内可查")
    note = Column(String(200), comment="没有可改写块时给候选人的一句话")
    # 降级对候选人静默、对内可查：这一列存的正是"这条答复是谁给的"（real / fallback_model / mock）。
    provenance = Column(JSON, comment="LLM 出处；候选人不看，内部与排障看")
    error = Column(SmallInteger, nullable=False, default=0, comment="1 = 这一发失败了")
    error_msg = Column(Text, comment="失败原因")
    create_time = Column(DateTime, default=utc_now, nullable=False, index=True)
    update_time = Column(
        DateTime, default=utc_now, onupdate=utc_now, comment="带 onupdate，快照/还原类脚本必须把它算进去"
    )
