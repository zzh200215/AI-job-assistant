"""AnswerEvaluationAgent — 回答评估智能体

功能：对候选人的每道题回答进行多维评分，输出量化评估
输入：问题内容 + 参考答案思路 + 用户回答
输出：completeness/accuracy/depth/expression/overall_score + 反馈
"""

from typing import Any

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.prompts.answer_evaluation import ANSWER_EVALUATION_PROMPT, FINAL_REPORT_PROMPT
from app.prompts.rendering import render_prompt
from app.services.llm_service import chat_json, set_llm_trace_context


class AnswerEvaluationAgent(BaseAgent):
    """逐题回答评估"""

    name = "AnswerEvaluationAgent"
    description = "回答评估智能体 — 逐题评估候选人回答质量"
    depends_on: list[str] = []
    result_type = "answer_evaluation"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        question = context.get("question", "")
        ref_answer = context.get("ref_answer", "")
        user_answer = context.get("user_answer", "")

        prompt = render_prompt(
            ANSWER_EVALUATION_PROMPT,
            question=question,
            ref_answer=ref_answer,
            user_answer=user_answer,
        )
        set_llm_trace_context(
            {
                "source": "AnswerEvaluationAgent.run_impl",
                "prompt_version": "answer-evaluation-v1",
                "prompt_name": "answer-evaluation",
                "prompt_family": "interview",
                "prompt_metadata": {
                    "prompt_version": "answer-evaluation-v1",
                    "prompt_name": "answer-evaluation",
                    "prompt_family": "interview",
                },
            }
        )
        result: dict[str, Any] = chat_json(prompt)
        return result

    def _make_summary(self, result: dict[str, Any]) -> str:
        score = result.get("overall_score", 0)
        return f"回答评分: {score}/100 | 完整性{result.get('completeness', 0)} 准确性{result.get('accuracy', 0)}"


class FinalReportAgent(BaseAgent):
    """综合报告生成 — 汇总所有题目评分生成最终报告"""

    name = "FinalReportAgent"
    description = "综合报告智能体 — 汇总面试评分生成最终报告"
    depends_on: list[str] = ["AnswerEvaluationAgent"]
    result_type = "final_report"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        evaluation_summary = context.get("evaluation_summary", "")
        avg_completeness = context.get("avg_completeness", 0)
        avg_accuracy = context.get("avg_accuracy", 0)
        avg_depth = context.get("avg_depth", 0)
        avg_expression = context.get("avg_expression", 0)
        overall_score = context.get("overall_score", 0)
        interview_type = context.get("interview_type", "tech")

        prompt = render_prompt(
            FINAL_REPORT_PROMPT,
            evaluation_summary=evaluation_summary,
            avg_completeness=avg_completeness,
            avg_accuracy=avg_accuracy,
            avg_depth=avg_depth,
            avg_expression=avg_expression,
            overall_score=overall_score,
            interview_type=interview_type,
        )
        set_llm_trace_context(
            {
                "source": "FinalReportAgent.run_impl",
                "prompt_version": "final-report-v1",
                "prompt_name": "final-report",
                "prompt_family": "interview",
                "prompt_metadata": {
                    "prompt_version": "final-report-v1",
                    "prompt_name": "final-report",
                    "prompt_family": "interview",
                },
            }
        )
        result: dict[str, Any] = chat_json(prompt)
        return result

    def _make_summary(self, result: dict[str, Any]) -> str:
        score = result.get("overall_score", 0)
        return f"面试报告: {score}/100 | 推荐: {result.get('hiring_recommendation', '')}"
