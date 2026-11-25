"""今日待办要吃得下 MySQL/SQLite 读回的 naive datetime。

`utc_now()` 带 tzinfo，直接和 ORM 读回的 `update_time` 相减会抛
`can't subtract offset-naive and offset-aware datetimes`，首页整块「今日任务」
变成 500（浏览器还可能把它报成 CORS）。
"""

from datetime import timedelta

from app.api.dashboard import today_tasks
from app.models.job_pipeline import STAGE_APPLIED, JobApplicationPipeline
from app.utils.time_helper import utc_now_naive


def test_today_tasks_handles_db_naive_datetimes(db_session, normal_user):
    db_session.add(
        JobApplicationPipeline(
            user_id=normal_user.id,
            title="Python 后端开发工程师",
            company="示例公司",
            stage=STAGE_APPLIED,
            update_time=utc_now_naive() - timedelta(days=10),
        )
    )
    db_session.commit()

    response = today_tasks(db=db_session, current_user=normal_user)

    tasks = response["data"]["tasks"]
    assert any(task["type"] == "follow_up" for task in tasks)
