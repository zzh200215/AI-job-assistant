# -*- coding: utf-8 -*-
"""
InterviewEngine - 模拟面试流程引擎

状态流转:
created -> ongoing -> completed

职责:
1. 加载面试会话与题目
2. 控制问答轮次与超时
3. 生成逐题评估
4. 汇总最终报告
"""
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agents.answer_evaluation_agent import AnswerEvaluationAgent, FinalReportAgent
from app.core.database import SessionLocal
from app.models.interview_session import InterviewSession
from app.orchestration.context import AgentContext
from app.utils.time_helper import utc_now


class InterviewEngine:
    """每场面试对应一个引擎实例。"""

    MAX_QUESTIONS = 10
    TIMEOUT_SECONDS = 30
    MAX_TIMEOUTS = 3

    def __init__(self, session_id: int):
        self.session_id = session_id
        self.db: Optional[Session] = None
        self.session: Optional[InterviewSession] = None

        self.current_index = -1
        self.question_count = 0
        self.start_time = 0.0
        self.timeout_count = 0
        self.evaluations: List[Dict[str, Any]] = []
        self._stopped = False

    def _load_session(self) -> InterviewSession:
        if self.db is None:
            self.db = SessionLocal()
        self.session = self.db.get(InterviewSession, self.session_id)
        if not self.session:
            raise ValueError(f"InterviewSession {self.session_id} not found")
        return self.session

    def init(self) -> Dict[str, Any]:
        self._load_session()
        self.question_count = len(self.session.questions or [])
        self.current_index = -1
        self.timeout_count = self.session.timeout_count or 0
        self.evaluations = []
        self._stopped = False
        return self._get_state()

    def _get_state(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.session.status if self.session else "unknown",
            "current_index": self.current_index,
            "total_questions": self.question_count,
            "answered_count": len(self.evaluations),
            "timeout_count": self.timeout_count,
            "max_timeouts": self.MAX_TIMEOUTS,
        }

    def start(self) -> Dict[str, Any]:
        self._load_session()
        self.session.status = "ongoing"
        self.session.answered_count = 0
        self.session.timeout_count = 0
        self.session.messages = self.session.messages or []
        self.db.commit()

        self.current_index = -1
        self.start_time = time.time()
        self.timeout_count = 0
        self.evaluations = []
        self._stopped = False

        return self.next_question()

    def resume(self) -> Optional[Dict[str, Any]]:
        self._load_session()
        self.question_count = len(self.session.questions or [])
        self.timeout_count = self.session.timeout_count or 0
        self.evaluations = self._rebuild_evaluations()
        self.current_index = self._infer_current_index()
        self.start_time = self._infer_start_time()
        self._stopped = self.session.status == "completed"

        current_question = self._get_latest_question_message()
        if current_question and self.session.status == "ongoing":
            return self._message_to_payload(current_question)
        return None

    def next_question(self) -> Dict[str, Any]:
        self.current_index += 1
        self._load_session()

        questions = self.session.questions or []
        if self.current_index >= len(questions) or self.current_index >= self.MAX_QUESTIONS:
            return self._finish()

        question = questions[self.current_index]
        question_text = question.get("question") or question.get("q") or ""
        category = question.get("category") or question.get("type") or "general"

        message = {
            "role": "ai",
            "type": "question",
            "content": question_text,
            "metadata": {
                "round": self.current_index + 1,
                "total": len(questions),
                "category": category,
                "question_id": question.get("id", self.current_index),
            },
            "timestamp": utc_now().isoformat(),
        }
        self.save_message(message)
        return self._message_to_payload(message)

    def handle_answer(self, user_answer: str) -> Dict[str, Any]:
        self._load_session()
        questions = self.session.questions or []
        if self.current_index < 0 or self.current_index >= len(questions):
            return self._finish()

        question = questions[self.current_index]
        question_text = question.get("question") or question.get("q") or ""
        ref_answer = question.get("ref_answer") or question.get("expected_answer") or ""
        category = question.get("category") or question.get("type") or "general"

        user_message = {
            "role": "user",
            "type": "answer",
            "content": user_answer,
            "metadata": {
                "round": self.current_index + 1,
                "category": category,
            },
            "timestamp": utc_now().isoformat(),
        }
        self.save_message(user_message)

        try:
            evaluation = self._evaluate_answer(question_text, ref_answer, user_answer)
        except Exception as exc:
            evaluation = {
                "completeness": 60,
                "accuracy": 60,
                "depth": 50,
                "expression": 60,
                "overall_score": 58,
                "feedback": f"评估过程异常: {str(exc)[:60]}，已给出参考评分。",
                "improvement": "请覆盖问题核心点，并用更清晰的结构表达。",
                "follow_up": False,
            }

        evaluation["question_index"] = self.current_index
        evaluation["question"] = question_text
        evaluation["category"] = category
        evaluation["user_answer"] = user_answer
        self.evaluations.append(evaluation)

        evaluation_message = {
            "role": "system",
            "type": "evaluation",
            "content": evaluation.get("feedback", ""),
            "metadata": {
                "round": self.current_index + 1,
                "score": evaluation.get("overall_score", 0),
                "completeness": evaluation.get("completeness", 0),
                "accuracy": evaluation.get("accuracy", 0),
                "depth": evaluation.get("depth", 0),
                "expression": evaluation.get("expression", 0),
                "improvement": evaluation.get("improvement", ""),
            },
            "timestamp": utc_now().isoformat(),
        }
        self.save_message(evaluation_message)
        self.session.answered_count = len(self.evaluations)
        self.db.commit()

        if evaluation.get("follow_up") and evaluation.get("overall_score", 0) < 70:
            follow_up_q = question.get(
                "follow_up_question",
                f"刚才的回答可以再深入一些吗？围绕“{question_text}”，请补一个更具体的例子或取舍说明。",
            )
            follow_up_message = {
                "role": "ai",
                "type": "question",
                "content": follow_up_q,
                "metadata": {
                    "round": self.current_index + 1,
                    "total": len(questions),
                    "category": category,
                    "question_id": question.get("id", self.current_index),
                    "is_follow_up": True,
                    "evaluation": {
                        "score": evaluation.get("overall_score", 0),
                        "feedback": evaluation.get("feedback", ""),
                    },
                },
                "timestamp": utc_now().isoformat(),
            }
            self.save_message(follow_up_message)
            return self._message_to_payload(follow_up_message)

        return self.next_question()

    def handle_timeout(self) -> Dict[str, Any]:
        self.timeout_count += 1
        self._load_session()
        self.session.timeout_count = self.timeout_count
        self.db.commit()

        questions = self.session.questions or []
        question = questions[self.current_index] if 0 <= self.current_index < len(questions) else {}
        question_text = question.get("question") or question.get("q") or ""
        category = question.get("category") or question.get("type") or "general"

        self.evaluations.append({
            "question_index": self.current_index,
            "question": question_text,
            "category": category,
            "completeness": 0,
            "accuracy": 0,
            "depth": 0,
            "expression": 0,
            "overall_score": 0,
            "feedback": "回答超时，未收到有效答案。",
            "improvement": "建议在 30 秒内先给结论，再展开细节。",
            "user_answer": "",
            "timed_out": True,
        })

        timeout_message = {
            "role": "system",
            "type": "system",
            "content": f"第 {self.current_index + 1} 题已超时（{self.timeout_count}/{self.MAX_TIMEOUTS}）",
            "metadata": {
                "timeout_count": self.timeout_count,
                "round": self.current_index + 1,
            },
            "timestamp": utc_now().isoformat(),
        }
        self.save_message(timeout_message)

        if self.timeout_count >= self.MAX_TIMEOUTS:
            return self._finish(reason="达到最大超时次数，面试结束")
        return self.next_question()

    def finish(self) -> Dict[str, Any]:
        return self._finish(reason="用户主动结束面试")

    def _finish(self, reason: str = "面试完成") -> Dict[str, Any]:
        self._load_session()
        self.session.status = "completed"
        self.session.completed_at = utc_now()
        self._stopped = True

        try:
            report = self._generate_report()
        except Exception:
            report = self._fallback_report()

        self.session.evaluation = report
        self.db.commit()

        end_message = {
            "role": "system",
            "type": "end",
            "content": reason,
            "metadata": report,
            "timestamp": utc_now().isoformat(),
        }
        self.save_message(end_message)
        return self._message_to_payload(end_message)

    def _evaluate_answer(self, question: str, ref_answer: str, user_answer: str) -> Dict[str, Any]:
        agent = AnswerEvaluationAgent()
        context = AgentContext()
        context.set_extra("question", question)
        context.set_extra("ref_answer", ref_answer)
        context.set_extra("user_answer", user_answer)
        return agent.run_impl(context)

    def _generate_report(self) -> Dict[str, Any]:
        valid_evals = [
            item for item in self.evaluations
            if not item.get("timed_out") and item.get("overall_score", 0) > 0
        ]
        if not valid_evals:
            return self._fallback_report()

        avg_completeness = sum(item["completeness"] for item in valid_evals) / len(valid_evals)
        avg_accuracy = sum(item["accuracy"] for item in valid_evals) / len(valid_evals)
        avg_depth = sum(item["depth"] for item in valid_evals) / len(valid_evals)
        avg_expression = sum(item["expression"] for item in valid_evals) / len(valid_evals)
        overall_score = round(
            avg_completeness * 0.30
            + avg_accuracy * 0.30
            + avg_depth * 0.25
            + avg_expression * 0.15
        )

        ai_report: Dict[str, Any] = {}
        try:
            lines = []
            for item in valid_evals:
                lines.append(
                    f"题目: {item.get('question', '')}\n"
                    f"评分: 完整性{item['completeness']} 准确性{item['accuracy']} 深度{item['depth']} 表达{item['expression']} 总分{item['overall_score']}\n"
                    f"反馈: {item.get('feedback', '')}\n"
                )
            agent = FinalReportAgent()
            context = AgentContext()
            context.set_extra("evaluation_summary", "\n".join(lines))
            context.set_extra("avg_completeness", round(avg_completeness, 1))
            context.set_extra("avg_accuracy", round(avg_accuracy, 1))
            context.set_extra("avg_depth", round(avg_depth, 1))
            context.set_extra("avg_expression", round(avg_expression, 1))
            context.set_extra("overall_score", overall_score)
            context.set_extra("interview_type", self.session.interview_type if self.session else "tech")
            ai_report = agent.run_impl(context) or {}
        except Exception:
            ai_report = {}

        report = {
            "overall_score": overall_score,
            "dimension_scores": {
                "completeness": round(avg_completeness, 1),
                "accuracy": round(avg_accuracy, 1),
                "depth": round(avg_depth, 1),
                "expression": round(avg_expression, 1),
            },
            "question_evaluations": self.evaluations,
            "total_questions": self.question_count,
            "answered_questions": len(valid_evals),
            "total_duration_seconds": int(time.time() - self.start_time) if self.start_time else 0,
            "interview_type": self.session.interview_type if self.session else "tech",
            "strengths": ai_report.get("strengths", []),
            "weaknesses": ai_report.get("weaknesses", []),
            "improvement_suggestions": ai_report.get("improvement_suggestions", []),
            "overall_evaluation": ai_report.get("overall_evaluation", ""),
            "dimensions": ai_report.get("dimensions", {}),
            "hiring_recommendation": ai_report.get("hiring_recommendation", ""),
        }
        return report

    def _fallback_report(self) -> Dict[str, Any]:
        return {
            "overall_score": 0,
            "dimension_scores": {
                "completeness": 0,
                "accuracy": 0,
                "depth": 0,
                "expression": 0,
            },
            "question_evaluations": self.evaluations,
            "total_questions": self.question_count,
            "answered_questions": 0,
            "total_duration_seconds": 0,
            "interview_type": self.session.interview_type if self.session else "tech",
            "strengths": [],
            "weaknesses": [],
            "improvement_suggestions": ["请至少完成一道题后再查看复盘报告。"],
            "overall_evaluation": "当前有效作答不足，暂时无法生成完整评估。",
            "dimensions": {},
            "hiring_recommendation": "待定",
        }

    def save_message(self, msg: Dict[str, Any]):
        self._load_session()
        messages = self.session.messages or []
        messages.append(msg)
        self.session.messages = messages
        self.db.commit()

    def get_current_question(self) -> Optional[Dict[str, Any]]:
        self._load_session()
        questions = self.session.questions or []
        if 0 <= self.current_index < len(questions):
            return questions[self.current_index]
        return None

    def is_finished(self) -> bool:
        return self._stopped

    def cleanup(self):
        if self.db:
            self.db.close()
            self.db = None

    def _get_latest_question_message(self) -> Optional[Dict[str, Any]]:
        self._load_session()
        for msg in reversed(self.session.messages or []):
            if msg.get("type") == "question":
                return msg
        return None

    def _infer_current_index(self) -> int:
        self._load_session()
        current_index = -1
        for msg in self.session.messages or []:
            if msg.get("type") != "question":
                continue
            meta = msg.get("metadata") or {}
            if meta.get("is_follow_up"):
                continue
            round_num = int(meta.get("round") or 0)
            if round_num > 0:
                current_index = max(current_index, round_num - 1)
        return current_index

    def _infer_start_time(self) -> float:
        self._load_session()
        for msg in self.session.messages or []:
            parsed = self._parse_timestamp(msg.get("timestamp"))
            if parsed is not None:
                return parsed
        if self.session.created_at:
            return self.session.created_at.timestamp()
        return time.time()

    def _rebuild_evaluations(self) -> List[Dict[str, Any]]:
        self._load_session()
        questions = self.session.questions or []
        evaluations: List[Dict[str, Any]] = []
        pending_answers: List[Dict[str, Any]] = []
        active_question: Optional[Dict[str, Any]] = None

        for msg in self.session.messages or []:
            msg_type = msg.get("type")
            meta = msg.get("metadata") or {}

            if msg_type == "question":
                active_question = msg
                continue

            if msg_type == "answer":
                pending_answers.append(msg)
                continue

            if msg_type == "evaluation":
                round_num = int(meta.get("round") or 0)
                question = self._resolve_question_snapshot(questions, active_question, round_num)
                answer_msg = pending_answers.pop(0) if pending_answers else None
                evaluations.append({
                    "question_index": max(round_num - 1, 0),
                    "question": question.get("question", ""),
                    "category": question.get("category", "general"),
                    "user_answer": answer_msg.get("content", "") if answer_msg else "",
                    "completeness": meta.get("completeness", 0),
                    "accuracy": meta.get("accuracy", 0),
                    "depth": meta.get("depth", 0),
                    "expression": meta.get("expression", 0),
                    "overall_score": meta.get("score", 0),
                    "feedback": msg.get("content", ""),
                    "improvement": meta.get("improvement", ""),
                    "follow_up": bool((active_question or {}).get("metadata", {}).get("is_follow_up")),
                })
                continue

            if msg_type == "system" and "timeout_count" in meta:
                round_num = int(meta.get("round") or 0)
                question = self._resolve_question_snapshot(questions, active_question, round_num)
                evaluations.append({
                    "question_index": max(round_num - 1, 0),
                    "question": question.get("question", ""),
                    "category": question.get("category", "general"),
                    "user_answer": "",
                    "completeness": 0,
                    "accuracy": 0,
                    "depth": 0,
                    "expression": 0,
                    "overall_score": 0,
                    "feedback": "回答超时，未收到有效答案。",
                    "improvement": "建议在 30 秒内先给结论，再展开细节。",
                    "timed_out": True,
                })

        return evaluations

    @staticmethod
    def _resolve_question_snapshot(
        questions: List[Dict[str, Any]],
        active_question: Optional[Dict[str, Any]],
        round_num: int,
    ) -> Dict[str, Any]:
        if active_question:
            meta = active_question.get("metadata") or {}
            return {
                "question": active_question.get("content", ""),
                "category": meta.get("category") or "general",
            }
        if 0 < round_num <= len(questions):
            item = questions[round_num - 1]
            return {
                "question": item.get("question") or item.get("q") or "",
                "category": item.get("category") or item.get("type") or "general",
            }
        return {"question": "", "category": "general"}

    @staticmethod
    def _parse_timestamp(timestamp: Optional[str]) -> Optional[float]:
        if not timestamp:
            return None
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _message_to_payload(message: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": message.get("type", ""),
            "content": message.get("content", ""),
            "metadata": message.get("metadata", {}),
        }
