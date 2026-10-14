"""单项目分析的一行作业（`docs/project-report-spec.md` §8）。

为什么不复用 `resume_report_job`：那是**一份简历**一行的东西，这一张是**一个项目**一行，
复用键里多了 `project_index`；量程、租约内的调用次数（前三节两发 + 第四节一发）也不同。
压在同一张表上，等于让"整份简历的报告"与"单个项目的分析"共用一套状态机。

`stage` 那一列是这张表唯一的新概念，为的是把"20 题按按钮再跑"落成一行可轮询的作业：
* `report` —— 前三节那一份文档（两发模型调用）；
* `questions` —— 同一项目的第四节（一发），`parent_job_id` 指回上面那一行。
**文档本身只存在父行那一份**：子行只存它自己那一节，读与下载都走同一个装配函数。
"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, SmallInteger, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now

STAGE_REPORT = "report"
STAGE_QUESTIONS = "questions"


class ProjectReportJob(Base):
    """一次 (人, 简历, 第几个项目, 哪一节) 的生成。"""

    __tablename__ = "project_report_job"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True, comment="提交人")
    resume_id = Column(BigInteger, nullable=False, index=True, comment="简历ID")
    project_index = Column(Integer, nullable=False, comment="简历里第几个项目，从 0 起（位次与 D6 都由它算）")
    project_name = Column(String(200), comment="提交那一刻的项目名，改名不影响历史行")
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
    grade = Column(String(8), comment="标杆级/优秀/良好/需重构/暂不可投；出局时为 NULL")
    difficulty = Column(String(4), comment="L1..L5，由模型提名、服务端按白名单收")
    excluded = Column(SmallInteger, nullable=False, default=0, comment="1 = 命中一票否决，这一份不给总分与等级")
    report_json = Column(JSON, comment="report 行：候选人视图的三大节；questions 行：只有第四节")
    errors_json = Column(JSON, comment="阶段失败与拒因（可能带模型原文，上不了屏）")
    provenance_json = Column(JSON, comment="各阶段模型出处 real/fallback/mock")
    lint_failures = Column(SmallInteger, nullable=False, default=0, comment="1 = 渲染出来过但没通过交付前机检")
    error = Column(SmallInteger, nullable=False, default=0, comment="1 = 这一发失败")
    error_msg = Column(Text, comment="失败原因，可能带模型输出，所以上不了屏")
    create_time = Column(DateTime, default=utc_now, nullable=False, index=True)
    update_time = Column(DateTime, default=utc_now, onupdate=utc_now)
