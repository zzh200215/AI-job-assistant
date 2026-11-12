"""演示数据：一颗按钮把空库变成"能走完主链"的样子。

**为什么要有这个模块**：功能都实现了，但一个新库进来是 6 块空态——上传简历、选目标、
等分析、看推荐、进看板、开面试，每一步都要求人先有数据，而"先有数据"这件事原先要人
自己点四五次不同的按钮（而且那些按钮还灌不同的数据）。

**为什么只能有一个出处**：岗位清单原先同时住在 `api/job_search.py`（5 条中文）与
`api/job_recommend.py`（10 条英文标题、`25k-45k` 那种写法）。两个 seed 端点灌出来的
东西口径不同，于是"这是同一个产品还是两个"取决于你点了哪颗按钮——所以那份清单搬到这里，
两个入口都从它取。

**为什么不用 `resume.seed-demo`**：那一支灌的是 6 份**别人的**简历（"用于企业筛选功能体验"），
是已经出树的企业侧遗留。把别人的简历灌进自己的账号，既不解决首次体验，也解释不清。
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.history import JobDescription, Resume
from app.models.job_pipeline import (
    STAGE_APPLIED,
    STAGE_INTERVIEW,
    STAGE_REJECTED,
    STAGE_TODO,
    STAGE_WRITTEN_TEST,
    JobApplicationPipeline,
)
from app.models.job_target import JobTarget

# 演示岗位清单：中文岗位、真实公司名、带技能标签与硬性要求。
# 这批数据同时服务两个入口（岗位市场的"一键导入演示岗位"与首页的"用示例数据体验"）。
SEED_JDS = [
    {
        "title": "Python 后端开发工程师",
        "company": "字节跳动",
        "location": "杭州",
        "salary_range": "25-40K·16薪",
        "experience": "3-5年",
        "education": "本科",
        "skill_tags": ["Python", "Django", "MySQL", "Redis", "Docker", "Kafka"],
        "industry": "互联网科技",
        "raw_text": "负责电商后端服务开发，使用 Python/Django 构建高并发订单系统。",
    },
    {
        "title": "AI 大模型算法工程师",
        "company": "阿里巴巴",
        "location": "杭州",
        "salary_range": "35-60K·16薪",
        "experience": "3-5年",
        "education": "硕士",
        "skill_tags": ["Python", "PyTorch", "LLM", "RAG", "LangChain", "Transformer"],
        "industry": "人工智能",
        "raw_text": "负责大模型训练、微调与 RAG 应用落地，参与 Agent 框架设计。",
    },
    {
        "title": "前端开发工程师",
        "company": "腾讯",
        "location": "深圳",
        "salary_range": "20-35K·15薪",
        "experience": "2-4年",
        "education": "本科",
        "skill_tags": ["Vue3", "React", "TypeScript", "Vite", "Node.js"],
        "industry": "互联网科技",
        "raw_text": "负责管理后台和业务中台前端开发，推进组件化和工程化建设。",
    },
    {
        "title": "数据分析师",
        "company": "美团",
        "location": "北京",
        "salary_range": "18-30K·15薪",
        "experience": "2-4年",
        "education": "本科",
        "skill_tags": ["SQL", "Python", "Tableau", "Hive", "Spark"],
        "industry": "互联网科技",
        "raw_text": "负责业务数据分析、指标体系建设与实验效果评估。",
    },
    {
        "title": "DevOps 工程师",
        "company": "京东",
        "location": "北京",
        "salary_range": "22-38K·14薪",
        "experience": "3-5年",
        "education": "本科",
        "skill_tags": ["Docker", "Kubernetes", "Jenkins", "Linux", "Prometheus"],
        "industry": "电商",
        "raw_text": "负责 CI/CD 流水线与容器集群运维，保障核心系统稳定交付。",
    },
]


# 演示简历：一个做了三年后端、正在往 AI 应用方向走的求职者。
# 刻意让它与 demo 岗位有真实的重合与真实的缺口——匹配度、技能差距、职业规划三处都要有东西可看：
# 会 Python/Docker/MySQL（对上岗位），缺 LLM/RAG/LangChain（对不上 AI 岗），这正是"缺口图"该显示的东西。
DEMO_RESUME = {
    "name": "林知遥",
    "phone": "13800000000",
    "email": "demo@example.com",
    "years_exp": 3,
    "file_name": "林知遥_后端转AI_简历.pdf",
    "parsed_json": {
        "name": "林知遥",
        "phone": "13800000000",
        "email": "demo@example.com",
        "years_exp": 3,
        "education": "本科",
        "major": "软件工程",
        "school": "华南理工大学",
        "current_title": "后端开发工程师",
        "expected_position": "AI 应用开发工程师",
        "expected_city": "杭州",
        "expected_salary_min": 25,
        "expected_salary_max": 40,
        "skills": ["Python", "FastAPI", "MySQL", "Redis", "Docker", "Celery", "Git"],
        "work_experience": [
            {
                "company": "某电商科技公司",
                "title": "后端开发工程师",
                "desc": "负责订单与库存服务的接口开发，用 FastAPI + MySQL 承载日均百万级请求；"
                "把三个核心接口的 P99 从 480ms 压到 120ms，主要手段是缓存分层与慢查询治理。",
            },
            {
                "company": "某 SaaS 初创公司",
                "title": "后端开发实习生",
                "desc": "参与权限模块从零搭建，独立完成 RBAC 表设计与接口实现。",
            },
        ],
        "project_experience": [
            {
                "name": "订单履约服务拆分",
                "desc": "把一个单体模块拆成三个独立服务，用 Celery 承接异步任务，"
                "上线后超时订单下降 62%；拆分过程中补了 40 多条回归用例。",
                "tech": ["Python", "FastAPI", "Celery", "MySQL", "Redis"],
            },
            {
                "name": "内部知识检索工具",
                "desc": "用向量检索给团队做了一份文档搜索，验证了 RAG 的基本链路（切片、embedding、召回）。",
                "tech": ["Python", "向量检索", "RAG"],
            },
        ],
        "self_evaluation": "三年后端经验，熟 Python 服务端；最近半年在自学 LLM 应用与 RAG，"
        "做过一个小规模的检索原型，希望把工程能力和模型能力接到一起。",
    },
}


# 演示求职目标：与简历里的期望方向**逐字一致**（AI 应用开发工程师 / 杭州 / 25-40K）。
# 为什么要有它：`/targets`（求职目标）是主链上"我要去哪"那一步，也是那一页唯一的数据源。
# 只灌简历与投递时不灌目标，导航上有这一项、点进去是"还没有求职目标"，而首页的下一步检查
# 同时写着"设定目标岗位 已完成"——两屏互相矛盾，比空态更难解释。
DEMO_TARGET = {
    "name": "AI 应用开发方向",
    "position": "AI 应用开发工程师",
    "industry": "人工智能",
    "cities": ["杭州"],
    "salary_min": 25,
    "salary_max": 40,
    "skills": ["Python", "FastAPI", "RAG", "LLM"],
    "priority": "high",
    "notes": "演示数据：三年后端经验，往大模型应用方向转。",
}


def seed_target(db: Session, user_id: int) -> bool:
    """灌一个主求职目标，按名称幂等。返回是否新增。

    `is_primary=1`：页面上的"主目标"是推荐链路的默认方向，没有主目标时那一屏
    只能显示"还没有求职目标"——所以幂等键选名称而不是"有没有任何目标"，
    重跑不会把一个已经被用户改成别的名字的目标又灌回来。
    """
    existing = db.query(JobTarget).filter(JobTarget.user_id == user_id, JobTarget.name == DEMO_TARGET["name"]).first()
    if existing:
        return False

    db.add(JobTarget(user_id=user_id, status="active", is_primary=1, **DEMO_TARGET))
    db.flush()
    return True


def seed_jobs(db: Session, user_id: int) -> tuple[int, int]:
    """灌演示岗位，按 (title, company) 幂等。返回 (新增, 跳过)。"""
    inserted = 0
    skipped = 0

    for item in SEED_JDS:
        existing = (
            db.query(JobDescription)
            .filter(
                JobDescription.user_id == user_id,
                JobDescription.title == item["title"],
                JobDescription.company == item["company"],
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        db.add(
            JobDescription(
                user_id=user_id,
                source="imported",
                is_active=1,
                title=item["title"],
                company=item["company"],
                location=item["location"],
                salary_range=item["salary_range"],
                raw_text=item["raw_text"],
                education_requirement=item["education"],
                experience_requirement=item["experience"],
                industry=item["industry"],
                skill_tags=item["skill_tags"],
                parsed_json={
                    "experience_requirement": item["experience"],
                    "education_requirement": item["education"],
                    "industry": item["industry"],
                    "required_skills": item["skill_tags"],
                    "jd_summary": item["raw_text"][:200],
                },
            )
        )
        inserted += 1

    db.flush()
    return inserted, skipped


def seed_resume(db: Session, user_id: int) -> bool:
    """灌一份自己的演示简历，按姓名幂等。返回是否新增。"""
    existing = (
        db.query(Resume)
        .filter(
            Resume.user_id == user_id,
            Resume.name == DEMO_RESUME["name"],
        )
        .first()
    )
    if existing:
        return False

    db.add(
        Resume(
            user_id=user_id,
            file_name=DEMO_RESUME["file_name"],
            file_path="",
            file_type="pdf",
            file_size=0,
            name=DEMO_RESUME["name"],
            phone=DEMO_RESUME["phone"],
            email=DEMO_RESUME["email"],
            years_exp=DEMO_RESUME["years_exp"],
            parsed_json=DEMO_RESUME["parsed_json"],
            raw_text=json.dumps(DEMO_RESUME["parsed_json"], ensure_ascii=False),
        )
    )
    db.flush()
    return True


def seed_pipeline(db: Session, user_id: int, resume_id: int | None) -> tuple[int, int]:
    """按演示岗位造几条不同阶段的投递记录，按 jd_id 幂等。

    为什么要有它：投递看板是主链里"投递之后去哪"的那一步。空库进去只有五列空列，
    而看板的价值全在"不同阶段各有多少、接下来该推进哪一条"。
    """
    stages = [STAGE_TODO, STAGE_APPLIED, STAGE_WRITTEN_TEST, STAGE_INTERVIEW, STAGE_REJECTED]
    jobs = (
        db.query(JobDescription)
        .filter(JobDescription.user_id == user_id, JobDescription.title.isnot(None))
        .order_by(JobDescription.id.asc())
        .limit(len(stages))
        .all()
    )

    inserted = 0
    skipped = 0
    # jobs 可能少于 stages（库里的岗位被删过一半也不会炸），所以有意取较短的那一侧。
    for job, stage in zip(jobs, stages, strict=False):
        existing = (
            db.query(JobApplicationPipeline)
            .filter(
                JobApplicationPipeline.user_id == user_id,
                JobApplicationPipeline.jd_id == job.id,
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        db.add(
            JobApplicationPipeline(
                user_id=user_id,
                jd_id=job.id,
                resume_id=resume_id,
                title=job.title,
                company=job.company or "",
                location=job.location or "",
                salary_range=job.salary_range or "",
                industry=job.industry or "",
                source="demo",
                stage=stage,
                note="演示数据：这一条是用来说明看板各阶段长什么样的。",
            )
        )
        inserted += 1

    db.flush()
    return inserted, skipped


def seed_demo_dataset(db: Session, user_id: int) -> dict:
    """一次写完演示数据。四步各自幂等，重复点只会跳过，不会灌重复。"""
    target_created = seed_target(db, user_id)
    resume_created = seed_resume(db, user_id)
    jobs_inserted, jobs_skipped = seed_jobs(db, user_id)

    resume = db.query(Resume).filter(Resume.user_id == user_id, Resume.name == DEMO_RESUME["name"]).first()
    pipeline_inserted, pipeline_skipped = seed_pipeline(db, user_id, resume.id if resume else None)

    db.commit()

    return {
        "target_created": target_created,
        "resume_created": resume_created,
        "jobs_inserted": jobs_inserted,
        "jobs_skipped": jobs_skipped,
        "applications_inserted": pipeline_inserted,
        "applications_skipped": pipeline_skipped,
        "resume_id": resume.id if resume else None,
    }
