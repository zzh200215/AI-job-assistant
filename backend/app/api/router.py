"""API router aggregation."""

from fastapi import APIRouter, Depends

from app.api import (
    agent,
    analysis,
    analytics,
    auth,
    career_path,
    dashboard,
    evaluation,
    external,
    history,
    interview_rest,
    jd,
    job_journal,
    job_pipeline,
    job_recommend,
    job_search,
    job_target,
    knowledge,
    multi_agent,
    notification,
    organization,
    prompt_trace,
    reminder,
    resume,
    salary_insight,
    subscription,
    system,
    tenant,
    timeline,
    tracking,
    user_preferences,
)
from app.api.auth import get_current_user

api_router = APIRouter()

# 鉴权从"每个端点自己记得写 Depends(get_current_user)"变成"整段前缀默认要会话"。
# 只挂到改动前就 100% 已经带会话依赖的 22 段前缀上（量出来是 123 条操作），所以已有响应零改变；
# 变的是"以后新增一条忘了写凭据的端点"的命运——它出生就 401。
# 仍混着公开端点的前缀（auth / system / jobs / interview / organizations / subscription /
# tenant / v1 external，共 110 条操作）不在这张表里，它们的公开面由
# tests/test_public_api_surface.py 的 PUBLIC_OPERATIONS 逐条钉住——那张清单也保证不会有人顺手
# 把公开端点关进守护里。
SESSION_GUARD = [Depends(get_current_user)]

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    user_preferences.router, prefix="/user", tags=["user-preferences"], dependencies=SESSION_GUARD
)
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"], dependencies=SESSION_GUARD)
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(
    evaluation.router,
    prefix="/eval-reports",
    tags=["eval-reports"],
    dependencies=SESSION_GUARD,
)
api_router.include_router(resume.router, prefix="/resume", tags=["resume"], dependencies=SESSION_GUARD)
api_router.include_router(jd.router, prefix="/jd", tags=["jd"], dependencies=SESSION_GUARD)
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"], dependencies=SESSION_GUARD)
api_router.include_router(history.router, prefix="/history", tags=["history"], dependencies=SESSION_GUARD)
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"], dependencies=SESSION_GUARD)
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"], dependencies=SESSION_GUARD)
api_router.include_router(analytics.admin_router, prefix="/admin", tags=["analytics-admin"], dependencies=SESSION_GUARD)
api_router.include_router(agent.router, prefix="/agent", tags=["agent"], dependencies=SESSION_GUARD)
api_router.include_router(
    multi_agent.router,
    prefix="/multi-agent",
    tags=["multi-agent"],
    dependencies=SESSION_GUARD,
)
api_router.include_router(interview_rest.router, prefix="/interview", tags=["interview"])
api_router.include_router(job_search.router, prefix="/jobs", tags=["job-search"])
api_router.include_router(job_recommend.router, prefix="/jobs", tags=["job-recommend"])
api_router.include_router(job_pipeline.router, prefix="/jobs", tags=["job-pipeline"])
api_router.include_router(job_target.router, prefix="/targets", tags=["job-target"], dependencies=SESSION_GUARD)
api_router.include_router(job_journal.router, prefix="/journals", tags=["job-journal"], dependencies=SESSION_GUARD)
api_router.include_router(
    career_path.router,
    prefix="/career-path",
    tags=["career-path"],
    dependencies=SESSION_GUARD,
)
api_router.include_router(
    salary_insight.router,
    prefix="/salary",
    tags=["salary-insight"],
    dependencies=SESSION_GUARD,
)
api_router.include_router(timeline.router, prefix="/timeline", tags=["timeline"], dependencies=SESSION_GUARD)
# 前端 utils/tracker.js 一直在往 /api/tracking/events 发；这个 router 此前从未 include，
# 所以每一条埋点都是 404，而且失败被 fetch 当成成功丢掉（见 tracker 的 resp.ok）。
api_router.include_router(tracking.router, prefix="/tracking", tags=["tracking"], dependencies=SESSION_GUARD)
api_router.include_router(
    notification.router,
    prefix="/notifications",
    tags=["notifications"],
    dependencies=SESSION_GUARD,
)
api_router.include_router(organization.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(
    prompt_trace.router,
    prefix="/prompt-traces",
    tags=["prompt-traces"],
    dependencies=SESSION_GUARD,
)
api_router.include_router(reminder.router, prefix="/reminders", tags=["reminders"], dependencies=SESSION_GUARD)
api_router.include_router(subscription.router, prefix="/subscription", tags=["subscription"])
api_router.include_router(tenant.router, prefix="/tenant", tags=["tenant"])
api_router.include_router(
    tenant.admin_router,
    prefix="/admin/tenants",
    tags=["tenant-admin"],
    dependencies=SESSION_GUARD,
)
# 外部能力 API（M6）：主 app 挂载前缀 /api + 此处 /v1 → /api/v1/external/...
# 这一段走 X-API-Key（app/api/external/auth.py），不是会话，不能挂 SESSION_GUARD。
api_router.include_router(external.external_router, tags=["external-api"])
