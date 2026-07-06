# -*- coding: utf-8 -*-
"""Unified task and step protocol for analysis orchestration."""
from typing import Dict


TASK_STATUS_MAP: Dict[str, str] = {
    "pending": "pending",
    "running": "running",
    "completed": "completed",
    "failed": "failed",
    "partial": "partial",
    "cancelled": "cancelled",
}

STEP_STATUS_MAP: Dict[str, str] = {
    "pending": "pending",
    "running": "running",
    "completed": "completed",
    "failed": "failed",
    "skipped": "skipped",
    "success": "completed",
}

STEP_NAME_MAP: Dict[str, str] = {
    "IntentAgent": "intent_recognition",
    "intent_recognition": "intent_recognition",
    "ResumeParseAgent": "resume_parse",
    "ResumeAgent": "resume_parse",
    "resume_parse": "resume_parse",
    "JDParseAgent": "jd_parse",
    "JobAgent": "jd_parse",
    "jd_parse": "jd_parse",
    "task_planning": "task_planning",
    "knowledge_retrieval": "knowledge_retrieval",
    "MatchAnalysisAgent": "match_analysis",
    "MatchAgent": "match_analysis",
    "matching_analysis": "match_analysis",
    "ResumeOptimizeAgent": "resume_optimization",
    "resume_optimization": "resume_optimization",
    "InterviewQuestionAgent": "interview_questions",
    "InterviewAgent": "interview_questions",
    "interview_question_generation": "interview_questions",
    "CareerAgent": "career_planning",
    "career_planning": "career_planning",
    "self_check": "self_check",
    "SummaryAgent": "summary_report",
    "final_report": "summary_report",
    "summary_report": "summary_report",
}

STEP_LABELS: Dict[str, str] = {
    "intent_recognition": "意图识别",
    "resume_parse": "简历解析",
    "jd_parse": "JD 解析",
    "task_planning": "任务规划",
    "knowledge_retrieval": "知识检索",
    "match_analysis": "匹配分析",
    "resume_optimization": "简历优化",
    "interview_questions": "面试题生成",
    "career_planning": "职业规划",
    "self_check": "自我校验",
    "summary_report": "汇总报告",
}

STEP_OUTPUT_SCHEMAS: Dict[str, str] = {
    "intent_recognition": "intent_result",
    "resume_parse": "resume_profile",
    "jd_parse": "jd_profile",
    "task_planning": "task_plan",
    "knowledge_retrieval": "knowledge_references",
    "match_analysis": "match_report",
    "resume_optimization": "resume_optimization",
    "interview_questions": "interview_questions",
    "career_planning": "career_plan",
    "self_check": "self_check_report",
    "summary_report": "summary_report",
}


def normalize_task_status(status: str) -> str:
    return TASK_STATUS_MAP.get(status or "", status or "pending")


def normalize_step_status(status: str) -> str:
    return STEP_STATUS_MAP.get(status or "", status or "pending")


def normalize_step_name(step_name: str) -> str:
    return STEP_NAME_MAP.get(step_name or "", step_name or "unknown")


def get_step_label(step_name: str) -> str:
    return STEP_LABELS.get(normalize_step_name(step_name), step_name or "unknown")


def get_step_output_schema(step_name: str) -> str:
    return STEP_OUTPUT_SCHEMAS.get(normalize_step_name(step_name), "generic_object")
