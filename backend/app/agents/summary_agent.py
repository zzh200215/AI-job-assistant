"""SummaryAgent — 汇总报告 Agent

汇总所有 Agent 的输出，生成最终综合分析报告。
复用 agent_report prompt
"""

import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.prompts.agent_report import AGENT_REPORT_PROMPT
from app.prompts.agent_report import PROMPT_VERSION as _PROMPT_VERSION
from app.prompts.rendering import render_prompt
from app.services.analysis_summaries import jd_digest, resume_digest
from app.services.llm_service import chat_json


class SummaryAgent(BaseAgent):
    # 与 app.prompts.agent_report 那份 prompt 同源，别在这儿再抄一遍字面量。
    prompt_version = _PROMPT_VERSION

    name = "SummaryAgent"
    description = "汇总报告 Agent — 整合所有分析结果，生成最终报告"
    depends_on: list[str] = ["MatchAnalysisAgent", "ResumeOptimizeAgent", "InterviewQuestionAgent"]
    result_type = "final_report"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        db = context.db
        resume_id = context.resume_id
        jd_id = context.jd_id

        from app.models.history import JobDescription, Resume

        resume: Resume = db.get(Resume, resume_id)
        jd: JobDescription = db.get(JobDescription, jd_id)

        prompt = render_prompt(
            AGENT_REPORT_PROMPT,
            resume_summary=resume_digest(resume),
            jd_summary=jd_digest(jd),
            match_result=json.dumps(context.match_result or {}, ensure_ascii=False, indent=2),
            optimize_result=json.dumps(context.optimize_result or {}, ensure_ascii=False, indent=2),
            interview_result=json.dumps(context.interview_result or {}, ensure_ascii=False, indent=2),
            career_result=json.dumps(context.career_result or {}, ensure_ascii=False, indent=2),
            self_check_result=json.dumps([], ensure_ascii=False, indent=2),
        )
        result: dict[str, Any] = chat_json(prompt)
        # 「简历诊断」那一格原来读的是 `resume_diagnosis.score`，而 `AGENT_REPORT_PROMPT`
        # 从没要求过这个键——真 provider 下它永远是空白，只有 mock 载荷里写着 78。
        # 现在这一格由服务端从 `ResumeAgent` 的七维结果拼出来（§10.41 他点的 ③）：
        # 综合报告与评估报告同一张表、同一个合计规则，模型自报的总数一律不进。
        diagnosis = resume_diagnosis_from(context.agent_outputs.get("ResumeAgent"))
        if diagnosis is None:
            result.pop("resume_diagnosis", None)
        else:
            result["resume_diagnosis"] = diagnosis
        return result

    def _make_summary(self, result: dict[str, Any]) -> str:
        score = result.get("summary", {}).get("match_score", 0)
        rec = result.get("summary", {}).get("recommendation", "")
        return f"汇总报告: 综合匹配 {score}/100 | {rec}"


def resume_diagnosis_from(resume_result: Any) -> dict[str, Any] | None:
    """把 `ResumeAgent` 的七维结果折成汇总报告里那一格；这一发没跑就返回 None。

    `key_findings` 只收**没到该维满分六成**的那些维度，且逐条带上维度名——
    一堆"都挺好"的 note 排在屏上等于没有信息。
    """
    if not isinstance(resume_result, dict):
        return None
    dimensions = resume_result.get("dimensions")
    if not isinstance(dimensions, list):
        return None

    findings = [
        f"{row['label']}：{row['note']}"
        for row in dimensions
        if isinstance(row, dict)
        and row.get("score") is not None
        and row.get("note")
        and row["score"] < row.get("full", 0) * 0.6
    ]
    total = resume_result.get("total_score")
    return {
        "total_score": total,
        "grade": resume_result.get("grade"),
        "dimensions": dimensions,
        "key_findings": findings,
        "scale_note": "与简历评估报告同一张七维表：总分是七维相加，不是模型自己报的那一个。",
    }
