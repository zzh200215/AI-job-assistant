"""API router aggregation."""

from fastapi import APIRouter

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
    user_preferences,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(user_preferences.router, prefix="/user", tags=["user-preferences"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(evaluation.router, prefix="/eval-reports", tags=["eval-reports"])
api_router.include_router(resume.router, prefix="/resume", tags=["resume"])
api_router.include_router(jd.router, prefix="/jd", tags=["jd"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(history.router, prefix="/history", tags=["history"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(analytics.admin_router, prefix="/admin", tags=["analytics-admin"])
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(multi_agent.router, prefix="/multi-agent", tags=["multi-agent"])
api_router.include_router(interview_rest.router, prefix="/interview", tags=["interview"])
api_router.include_router(job_search.router, prefix="/jobs", tags=["job-search"])
api_router.include_router(job_recommend.router, prefix="/jobs", tags=["job-recommend"])
api_router.include_router(job_pipeline.router, prefix="/jobs", tags=["job-pipeline"])
api_router.include_router(job_target.router, prefix="/targets", tags=["job-target"])
api_router.include_router(job_journal.router, prefix="/journals", tags=["job-journal"])
api_router.include_router(career_path.router, prefix="/career-path", tags=["career-path"])
api_router.include_router(salary_insight.router, prefix="/salary", tags=["salary-insight"])
api_router.include_router(timeline.router, prefix="/timeline", tags=["timeline"])
api_router.include_router(notification.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(organization.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(prompt_trace.router, prefix="/prompt-traces", tags=["prompt-traces"])
api_router.include_router(reminder.router, prefix="/reminders", tags=["reminders"])
api_router.include_router(subscription.router, prefix="/subscription", tags=["subscription"])
api_router.include_router(tenant.router, prefix="/tenant", tags=["tenant"])
api_router.include_router(tenant.admin_router, prefix="/admin/tenants", tags=["tenant-admin"])
# 外部能力 API（M6）：主 app 挂载前缀 /api + 此处 /v1 → /api/v1/external/...
api_router.include_router(external.external_router, tags=["external-api"])
