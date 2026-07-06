# -*- coding: utf-8 -*-
"""API router aggregation."""

from fastapi import APIRouter

from app.api import (
    agent,
    analysis,
    auth,
    career_path,
    evaluation,
    history,
    interview_rest,
    jd,
    job_data_source,
    job_pipeline,
    job_recommend,
    job_search,
    knowledge,
    multi_agent,
    prompt_trace,
    resume,
    system,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(evaluation.router, prefix="/eval-reports", tags=["eval-reports"])
api_router.include_router(resume.router, prefix="/resume", tags=["resume"])
api_router.include_router(jd.router, prefix="/jd", tags=["jd"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(history.router, prefix="/history", tags=["history"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(multi_agent.router, prefix="/multi-agent", tags=["multi-agent"])
api_router.include_router(interview_rest.router, prefix="/interview", tags=["interview"])
api_router.include_router(job_search.router, prefix="/jobs", tags=["job-search"])
api_router.include_router(job_recommend.router, prefix="/jobs", tags=["job-recommend"])
api_router.include_router(job_pipeline.router, prefix="/jobs", tags=["job-pipeline"])
api_router.include_router(job_data_source.router, prefix="/datasource", tags=["datasource"])
api_router.include_router(career_path.router, prefix="/career-path", tags=["career-path"])
api_router.include_router(prompt_trace.router, prefix="/prompt-traces", tags=["prompt-traces"])
