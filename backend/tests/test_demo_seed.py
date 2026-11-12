"""首次体验的演示数据：一次写完简历 / 岗位 / 投递记录，且可重复点。

判据分三层：

1. **形状**：一次调用之后三张表都有东西，投递记录覆盖多个阶段（否则看板五列里四列是空的）；
2. **口径**：两个岗位 seed 入口灌的是**同一份清单**——这是本轮真正修的东西，
   原先 `api/job_search.py` 是 5 条中文、`api/job_recommend.py` 是 10 条英文标题，
   于是"点哪个按钮"决定了屏幕上是中国岗位还是英文岗位；
3. **幂等**：第二次调用不新增任何行（这颗按钮会留在首页上，重复点不能灌重复数据）。
"""

from __future__ import annotations

from app.models.history import JobDescription, Resume
from app.models.job_pipeline import ACTIVE_STAGES, JobApplicationPipeline
from app.services.demo_seed_service import DEMO_RESUME, SEED_JDS, seed_demo_dataset, seed_jobs


class TestDemoSeed:
    def test_seed_creates_resume_jobs_and_applications(self, db_session, normal_user):
        data = seed_demo_dataset(db_session, normal_user.id)

        assert data["resume_created"] is True
        assert data["jobs_inserted"] == len(SEED_JDS)
        assert data["applications_inserted"] == len(SEED_JDS)

        assert db_session.query(Resume).filter(Resume.user_id == normal_user.id).count() == 1
        assert db_session.query(JobDescription).filter(JobDescription.user_id == normal_user.id).count() == len(
            SEED_JDS
        )
        assert db_session.query(JobApplicationPipeline).filter(
            JobApplicationPipeline.user_id == normal_user.id
        ).count() == len(SEED_JDS)

    def test_applications_spread_across_stages(self, db_session, normal_user):
        """看板要有东西看：至少两个不同阶段，且有一条落在活跃阶段里。"""
        seed_demo_dataset(db_session, normal_user.id)

        stages = {
            row.stage
            for row in db_session.query(JobApplicationPipeline)
            .filter(JobApplicationPipeline.user_id == normal_user.id)
            .all()
        }
        assert len(stages) >= 2
        assert stages & set(ACTIVE_STAGES)

    def test_second_call_adds_nothing(self, db_session, normal_user):
        first = seed_demo_dataset(db_session, normal_user.id)
        second = seed_demo_dataset(db_session, normal_user.id)

        assert first["jobs_inserted"] == len(SEED_JDS)
        assert second["jobs_inserted"] == 0
        assert second["applications_inserted"] == 0
        assert second["resume_created"] is False
        # 简历按姓名幂等，所以 resume_id 两次都指同一行
        assert second["resume_id"] == first["resume_id"]

    def test_jobs_come_from_the_single_list(self, db_session, normal_user):
        """这条钉的是"只剩一套口径"：两个入口取的是同一个 SEED_JDS。"""
        seed_demo_dataset(db_session, normal_user.id)

        titles = [
            row.title
            for row in db_session.query(JobDescription)
            .filter(JobDescription.user_id == normal_user.id)
            .order_by(JobDescription.id.asc())
            .all()
        ]
        assert titles == [item["title"] for item in SEED_JDS]

    def test_job_market_seed_and_dataset_share_the_pool(self, db_session, normal_user):
        """岗位市场那颗按钮先点，再点首次体验，不该出现第二批同义不同名的岗位。"""
        inserted, _skipped = seed_jobs(db_session, normal_user.id)
        assert inserted == len(SEED_JDS)

        data = seed_demo_dataset(db_session, normal_user.id)
        assert data["jobs_inserted"] == 0
        assert data["jobs_skipped"] == len(SEED_JDS)

    def test_resume_carries_expected_direction_for_career_planning(self, db_session, normal_user):
        """演示简历要带求职方向，否则职业规划与匹配两页没有可比的东西。"""
        seed_demo_dataset(db_session, normal_user.id)

        resume = db_session.query(Resume).filter(Resume.user_id == normal_user.id).one()
        parsed = resume.parsed_json
        assert parsed["expected_position"] == DEMO_RESUME["parsed_json"]["expected_position"]
        assert parsed.get("skills")
        assert parsed.get("work_experience")
