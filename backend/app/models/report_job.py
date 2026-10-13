"""D229：一份简历评估报告背后的一行作业。

为什么又是一张表而不是复用 `rewrite_suggestion_job`：报告最多跑三发模型调用（概览、批改稿、
面试预演），产出的是整份六模块文档而不是几条建议，两者的生命周期、租约上界与保留期都不同
（报告 45 分钟 / 3 天，改写 15 分钟 / 7 天）。压在同一张表上，等于让两个不同的东西共用一套
状态机与清理规则。

这一张表存的是**报告本身**，不写回 `tb_resume`：候选人点"采纳"走的是既有的
`POST /resume/{id}/apply-rewrites`，快照、撤销、重算匹配分都还在那一条路上。
"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, SmallInteger, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now


class ResumeReportJob(Base):
    """一次 (人, 简历, 目标岗位) 的报告生成。"""

    __tablename__ = "resume_report_job"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True, comment="提交人")
    resume_id = Column(BigInteger, nullable=False, index=True, comment="简历ID")
    jd_id = Column(BigInteger, comment="目标岗位ID，可空")
    target_position = Column(String(200), comment="打分用的岗位名，可空（没选岗位时按简历识别方向）")
    status = Column(
        String(20), nullable=False, default="pending", index=True, comment="pending/running/completed/failed"
    )
    claimed_at = Column(DateTime, nullable=True, comment="领走时刻；租约让同一行只有一个赢家")
    finished_at = Column(DateTime, nullable=True, comment="进终态的时刻，清理按它算")
    total_score = Column(Integer, comment="七维之和；模型没给全就是 NULL，不是 0")
    grade = Column(String(4), comment="A/B/C/D，由总分映射")
    report_json = Column(JSON, comment="候选人视图的六模块；批改稿的原文也在里面")
    # 对内：阶段失败原因、被复核拒掉的条目、模型出处。轮询载荷不带这几列。
    errors_json = Column(JSON, comment="阶段失败与拒因")
    provenance_json = Column(JSON, comment="各阶段模型出处 real/fallback/mock")
    lint_failures = Column(SmallInteger, nullable=False, default=0, comment="1 = 渲染出来过但没通过交付前机检")
    error = Column(SmallInteger, nullable=False, default=0, comment="1 = 这一发失败")
    error_msg = Column(Text, comment="失败原因，可能带模型输出，所以上不了屏")
    create_time = Column(DateTime, default=utc_now, nullable=False, index=True)
    update_time = Column(DateTime, default=utc_now, onupdate=utc_now)
