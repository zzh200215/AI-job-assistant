"""多项目组合分析的一行作业（`docs/portfolio-report-spec.md` §7）。

为什么不复用 `project_report_job`：那一行是**一个项目**，这一行是**一组项目**——
键从 `project_index` 换成 `combo_key`（"选中了简历里哪几个项目"的规范化键，顺序无关）。
把一组压在一个 `project_index` 上，等于让"位次那一维"这一件事出现两个出处。

`stage` 沿用单项目那一族的两个值：`report`（前三节，三发模型调用）与
`questions`（第四节跨项目 12 题，一发，按按钮才跑）。
**文档只存父行那一份**：子行只存它自己那一节，读与下载都走同一个装配函数。
"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, SmallInteger, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now

STAGE_REPORT = "report"
STAGE_QUESTIONS = "questions"


class PortfolioReportJob(Base):
    """一次 (人, 简历, 选中了哪几个项目, 哪一节) 的生成。"""

    __tablename__ = "portfolio_report_job"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True, comment="提交人")
    resume_id = Column(BigInteger, nullable=False, index=True, comment="简历ID")
    combo_key = Column(String(64), nullable=False, index=True, comment="选中项目的规范化键，如 0,1,2")
    project_indices = Column(JSON, nullable=False, comment="按简历顺序排好的项目序号")
    project_count = Column(Integer, nullable=False, comment="这一组是几个项目（至少两个）")
    project_names = Column(JSON, comment="提交那一刻各项目的名字，改名不影响历史行")
    stage = Column(String(16), nullable=False, default=STAGE_REPORT, index=True, comment="report / questions")
    parent_job_id = Column(BigInteger, index=True, comment="questions 行指回它续跑的那一份 report 行")
    jd_id = Column(BigInteger, comment="目标岗位ID，可空")
    target_position = Column(String(200), comment="打分用的岗位名，可空")
    status = Column(
        String(20), nullable=False, default="pending", index=True, comment="pending/running/completed/failed"
    )
    claimed_at = Column(DateTime, nullable=True, comment="领走时刻；租约让同一行只有一个赢家")
    finished_at = Column(DateTime, nullable=True, comment="进终态的时刻，清理按它算")
    total_score = Column(Integer, comment="六维之和；命中红线或没读全就是 NULL，不是 0")
    grade = Column(String(8), comment="标杆级/优秀/良好/需重组/暂不可投；出局时为 NULL")
    difficulty = Column(String(4), comment="L1..L5，由模型提名、服务端按白名单收（组合不新造档位）")
    excluded = Column(SmallInteger, nullable=False, default=0, comment="1 = 命中一票否决，这一份不给总分与等级")
    report_json = Column(JSON, comment="report 行：候选人视图的三大节；questions 行：只有第四节")
    errors_json = Column(JSON, comment="阶段失败与拒因（可能带模型原文，上不了屏）")
    provenance_json = Column(JSON, comment="各阶段模型出处 real/fallback/mock")
    lint_failures = Column(SmallInteger, nullable=False, default=0, comment="1 = 渲染出来过但没通过交付前机检")
    error = Column(SmallInteger, nullable=False, default=0, comment="1 = 这一发失败")
    error_msg = Column(Text, comment="失败原因，可能带模型输出，所以上不了屏")
    create_time = Column(DateTime, default=utc_now, nullable=False, index=True)
    update_time = Column(DateTime, default=utc_now, onupdate=utc_now)


__all__ = ["STAGE_QUESTIONS", "STAGE_REPORT", "PortfolioReportJob"]
