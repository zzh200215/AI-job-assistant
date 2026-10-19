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
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.agents.answer_evaluation_agent import AnswerEvaluationAgent, FinalReportAgent
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.interview_session import InterviewSession
from app.orchestration.context import AgentContext
from app.services.interview_config_service import QUESTION_TYPE_LABELS, timeout_for_type
from app.services.interview_evaluation_service import (
    build_memory_snapshot,
    complete_turn_evaluation,
    completed_evaluation_payloads,
    create_pending_turn_evaluation,
    pending_evaluation_count,
    session_write_lock,
    submit_turn_evaluation,
)
from app.services.interviewer_decision import decide_next
from app.utils.time_helper import utc_now

# 标签 → 题型键，`QUESTION_TYPE_LABELS` 的逆。两边同一出处，所以出题侧写的标签和读题侧回推的
# 标签不可能漂开（这张表以前在 api 层内联写了一遍，那是"两处权威"的老形状）。
_LABEL_TO_TYPE: dict[str, str] = {label: qtype for qtype, label in QUESTION_TYPE_LABELS.items()}


def resolve_question_type(question: dict[str, Any]) -> str:
    """认出一道题的**题型键**（basic / tech / project / scenario），拿它去查这一题的作答预算。

    为什么要一个解析器而不是直接读字段：`category` 这一个字段装着**两种域**——
    starter 那条路塞进来的是 `_map_category()` 的中文标签（"技术基础"…），而既有夹具与
    模型生成的题把英文题型键写在同一个字段里（"tech"…）。只认其中一种，另一整族题就会
    静默拿下限 45 秒，而屏幕上什么都不会说。
    优先级：`type` → `category` 本身就是题型键 → `category` 是中文标签则回推 → 都不认得才 general。
    """
    if question.get("type"):
        return str(question["type"])
    category = str(question.get("category") or "")
    if category in QUESTION_TYPE_LABELS:
        return category
    if category in _LABEL_TO_TYPE:
        return _LABEL_TO_TYPE[category]
    return "general"


class InterviewEngine:
    """每场面试对应一个引擎实例。"""

    MAX_QUESTIONS = 10
    # 每题的作答秒数不再是类常量：它按题型取（`interview_config_service.timeout_for_type`），
    # 并随问题消息一起下发（`metadata.timeout_seconds`）。留着它就等于留一条退路——任何一处
    # 再引用 `InterviewEngine.TIMEOUT_SECONDS`，全场就又回到 30 秒，所以护栏直接断言这个属性不在。
    MAX_TIMEOUTS = 3

    def __init__(self, session_id: int):
        self.session_id = session_id
        self.db: Session | None = None
        self.session: InterviewSession | None = None

        self.current_index = -1
        self.question_count = 0
        self.start_time = 0.0
        self.timeout_count = 0
        self.evaluations: list[dict[str, Any]] = []
        self._stopped = False

    def _load_session(self) -> InterviewSession:
        if self.db is None:
            self.db = SessionLocal()
        self.session = self.db.get(InterviewSession, self.session_id)
        if not self.session:
            raise ValueError(f"InterviewSession {self.session_id} not found")
        return self.session

    def init(self) -> dict[str, Any]:
        self._load_session()
        self.question_count = len(self.session.questions or [])
        self.current_index = -1
        self.timeout_count = self.session.timeout_count or 0
        self.evaluations = []
        self._stopped = False
        return self._get_state()

    def _get_state(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.session.status if self.session else "unknown",
            "current_index": self.current_index,
            "total_questions": self.question_count,
            "answered_count": self.session.answered_count if self.session else len(self.evaluations),
            "timeout_count": self.timeout_count,
            "max_timeouts": self.MAX_TIMEOUTS,
        }

    def start(self) -> dict[str, Any]:
        self._load_session()
        self.session.status = "ongoing"
        self.session.answered_count = 0
        self.session.timeout_count = 0
        self.session.messages = self.session.messages or []
        self.session.evaluation_status = "idle"
        self.session.memory_snapshot = {}
        self.db.commit()

        self.current_index = -1
        self.start_time = time.time()
        self.timeout_count = 0
        self.evaluations = []
        self._stopped = False

        return self.next_question()

    def resume(self) -> dict[str, Any] | None:
        self._load_session()
        self.question_count = len(self.session.questions or [])
        self.timeout_count = self.session.timeout_count or 0
        self.evaluations = self._rebuild_evaluations()
        self.current_index = self._infer_current_index()
        self.start_time = self._infer_start_time()
        self._stopped = self.session.status == "completed"

        current_question = self._get_latest_question_message()
        if current_question and self.session.status == "ongoing":
            # 断线若发生在「已作答、下一题还没推」的间隙，重连时不应重复推送已作答的题目
            # （否则客户端会再答一次，撞 (session_id, turn_id) 唯一约束）。返回 None 交给
            # 上层调用 next_question() 推进到下一题。
            if self._question_answered(current_question):
                return None
            return self._message_to_payload(current_question)
        return None

    def next_question(self) -> dict[str, Any]:
        followup = self._maybe_followup()
        if followup is not None:
            return followup

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
                # 这一题的作答预算随消息一起下去：前端自己那份 30 是个平行真相，
                # 它同时是三处倒计时的起点**和**进度条的分母，不跟着走就会显示成 120 秒的场次里
                # 一根 4 秒就到底的进度条。WS 那侧的 `asyncio.sleep` 也只读这一个数。
                "timeout_seconds": timeout_for_type(self.db, resolve_question_type(question)),
                "question_id": question.get("id", self.current_index),
                "turn_id": f"q-{self.current_index + 1}",
            },
            "timestamp": utc_now().isoformat(),
        }
        self.save_message(message)
        return self._message_to_payload(message)

    @staticmethod
    def _bounded_chat(chat):
        """给决策那一档的 LLM 调用加硬截止时间：慢就算了，候选人不能为一句追问等两分钟。

        截止用 `future.result(timeout=...)` 判；底层请求可能还在跑，这里只是不再等它（线程池
        不等待关闭）。代价是极少数慢请求会白花一次 token，换来的是面试节奏不被拖住。
        """

        def call(prompt: str):
            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(chat, prompt)
            try:
                return future.result(timeout=settings.INTERVIEW_DECISION_TIMEOUT_SECONDS)
            except FuturesTimeout as exc:
                raise TimeoutError("决策 LLM 超时") from exc
            finally:
                pool.shutdown(wait=False)

        return call

    def _decision_chat(self):
        """决策那一档的 LLM 入口。测试里替换这一个方法就能完全断开真 provider。"""
        from app.services.llm_service import chat_json

        return self._bounded_chat(chat_json)

    def _decision_state(self, questions: list[dict[str, Any]], evaluations: list[dict[str, Any]]) -> dict[str, Any]:
        """决策器的输入一律由引擎拼好传进去——决策器自己不取库（那会变成第二条会话链）。

        候选池取的是**还没出过的题**（`current_index + 1` 往后），不是整份列表：否则 advance 会
        把已经答过的题再问一遍。
        """
        return {
            "round_index": len(evaluations),
            "scores": [int(item.get("overall_score") or 0) for item in evaluations],
            "evidence": [str(item.get("evidence") or "") for item in evaluations],
            "asked_followup": bool(evaluations[-1].get("follow_up")) if evaluations else False,
            # 弱点池：建会话时落的 JD 必考技能（还没考到的那些）。`weaknesses` 是给兼容留的旧键，
            # 今天没有任何写入端——别只读它，否则追问的弱点分支是死代码。
            "weaknesses": (self.session.memory_snapshot or {}).get("jd_required_skills")
            or (self.session.memory_snapshot or {}).get("weaknesses")
            or [],
            "candidate_pool": questions[self.current_index + 1 :],
        }

    def _maybe_followup(self) -> dict[str, Any] | None:
        """答了、分低、有内容、且这题还没追问过 ⇒ 出一条单点追问；其余一律返回 None 走原来那条链。

        追问**不推进 `current_index`**：它不是新的一题。所以 `round` 报的是被追问那一题的轮次，
        `total` 仍是题目总数——前端的进度条分母就是 total，这里动一下就会画歪。
        """
        if not settings.INTERVIEW_USE_DECIDER:
            return None

        self._load_session()
        questions = self.session.questions or []
        evaluations = self._rebuild_evaluations()
        if not evaluations:
            return None

        last = evaluations[-1]
        if last.get("follow_up"):
            return None
        # 超时那一题在 `_rebuild_evaluations()` 里是 overall_score=0 且 timed_out=True。决策器只看
        # 分数就会判深挖，于是面试官去追问一段从来没出现过的回答——那是幻觉，不是追问。
        if last.get("timed_out") or not str(last.get("user_answer") or "").strip():
            return None

        decision = decide_next(self._decision_state(questions, evaluations), chat=self._decision_chat())
        if decision.get("action") != "deepen":
            return None

        question = decision["question"]
        round_num = len(evaluations)
        # metadata 一律**内联**在消息字面量里，不拆成变量：那条静态守卫（P1.2 落的花括号配对）是按
        # `"type": "question"` 之后紧跟的 `"metadata": {` 取字典体的，拆出去它就看不到这枚章。
        message = {
            "role": "ai",
            "type": "question",
            "content": question.get("question") or question.get("q") or "",
            "metadata": {
                "round": round_num,
                "total": len(questions),
                "category": question.get("category") or "general",
                "timeout_seconds": timeout_for_type(self.db, resolve_question_type(question)),
                "question_id": question.get("id", round_num),
                "turn_id": f"q-{round_num}-followup",
                "is_follow_up": True,
                "decision": {
                    "action": decision["action"],
                    "source": decision.get("source", "heuristic"),
                    "degraded": bool(decision.get("degraded")),
                },
            },
            "timestamp": utc_now().isoformat(),
        }
        self.save_message(message)
        return self._message_to_payload(message)

    def handle_answer(self, user_answer: str, *, defer_evaluation: bool = False) -> dict[str, Any]:
        """Persist an answer and either evaluate inline or schedule the P1 background evaluation path."""
        self._load_session()
        questions = self.session.questions or []
        if self.current_index < 0 or self.current_index >= len(questions):
            return self._finish()

        question = questions[self.current_index]
        question_text = question.get("question") or question.get("q") or ""
        ref_answer = question.get("ref_answer") or question.get("expected_answer") or ""
        category = question.get("category") or question.get("type") or "general"
        active_question = self._get_latest_question_message() or {}
        active_meta = active_question.get("metadata") or {}
        is_follow_up = bool(active_meta.get("is_follow_up")) and int(active_meta.get("round") or 0) == (
            self.current_index + 1
        )
        # Main turns are derived from the engine index. JSON message persistence can be stale within one ORM session.
        turn_id = str(active_meta.get("turn_id")) if is_follow_up else f"q-{self.current_index + 1}"

        user_message = {
            "role": "user",
            "type": "answer",
            "content": user_answer,
            "metadata": {
                "round": self.current_index + 1,
                "category": category,
                "turn_id": turn_id,
                "is_follow_up": is_follow_up,
            },
            "timestamp": utc_now().isoformat(),
        }
        self.save_message(user_message)

        record = create_pending_turn_evaluation(
            self.db,
            session_id=self.session_id,
            turn_id=turn_id,
            question_index=self.current_index,
            question=question_text,
            category=category,
            user_answer=user_answer,
            is_follow_up=is_follow_up,
        )

        if defer_evaluation:
            self.session.answered_count = (self.session.answered_count or 0) + 1
            self.session.evaluation_status = "processing"
            self.db.commit()
            self.save_message(
                {
                    "role": "system",
                    "type": "system",
                    "content": "本题回答已记录，评分将在后台完成，不影响继续作答。",
                    "metadata": {"round": self.current_index + 1, "turn_id": turn_id, "evaluation_pending": True},
                    "timestamp": utc_now().isoformat(),
                }
            )
            submit_turn_evaluation(self.session_id, record.id)
            return self.next_question()

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

        complete_turn_evaluation(record, evaluation)

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
                "turn_id": turn_id,
                "evidence": record.evidence or {},
            },
            "timestamp": utc_now().isoformat(),
        }
        self.save_message(evaluation_message)
        self.session.answered_count = len(self.evaluations)
        self.session.memory_snapshot = build_memory_snapshot(self.db, self.session_id)
        self.session.evaluation_status = "idle"
        self.db.commit()

        # 追问只能有一条产线：开关打开时由决策器独占（原稿 P3 的"追问升级"就是把 I3 的模板追问
        # 换成基于回答内容的针对性追问），关掉开关才回到这套模板。两套并存会让同一题被追两次——
        # 2026-10-18 验证重连链时实测到过（先模板一条、next_question 再决策一条）。
        if (
            not settings.INTERVIEW_USE_DECIDER
            and evaluation.get("follow_up")
            and evaluation.get("overall_score", 0) < 70
        ):
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
                    # 追问也是"下一题"，同样得带预算——少盖这一处，重连或追问时前端就掉回兜底值，
                    # 而哪一边都不报错（`test_both_question_emission_sites_stamp_the_field` 守这条）。
                    "timeout_seconds": timeout_for_type(self.db, resolve_question_type(question)),
                    "question_id": question.get("id", self.current_index),
                    "is_follow_up": True,
                    "turn_id": f"{turn_id}-follow-up",
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

    def handle_timeout(self) -> dict[str, Any]:
        self.timeout_count += 1
        self._load_session()
        self.session.timeout_count = self.timeout_count
        self.db.commit()

        questions = self.session.questions or []
        question = questions[self.current_index] if 0 <= self.current_index < len(questions) else {}
        question_text = question.get("question") or question.get("q") or ""
        category = question.get("category") or question.get("type") or "general"

        self.evaluations.append(
            {
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
            }
        )

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

    def finish(self) -> dict[str, Any]:
        return self._finish(reason="用户主动结束面试")

    def _finish(self, reason: str = "面试完成") -> dict[str, Any]:
        self._load_session()
        self.session.status = "completed"
        self.session.completed_at = utc_now()
        self._stopped = True
        # 先把"结束"这件事落库再决定报告怎么写：状态晚一步可见，逐题评分那边就会拿着旧的
        # `session.status` 判定，于是 `_evaluation_status` 永远回不到 completed。
        self.db.commit()

        try:
            report = self._generate_report()
        except Exception:
            report = self._fallback_report()

        # D225：判定放在锁里、并且**重读之后**才判。这两件事都是被现场逼出来的：
        #   · 生成上面这份报告用的 `self.evaluations` 是本引擎早先重建的，而这一次模型调用
        #     可能比最后一题的评分还慢（D224：报告调用 40.4s，最后几条评分在那之后才落地），
        #     于是"我算出来的报告"其实是空的，写下去就把已经齐了的终报盖回 0 分；
        #   · 评分 worker 也会写这两个字段，没有串行就是后写的赢、而不是对的赢。
        # 所以：还有 pending 才写这份占位报告；已经齐了就一律不写，交给 refresh 按表重建。
        with session_write_lock(self.session_id):
            self.db.refresh(self.session)
            pending = pending_evaluation_count(self.db, self.session_id)
            if pending:
                self.session.evaluation_status = "processing"
                self.session.memory_snapshot = build_memory_snapshot(self.db, self.session_id)
                report["evaluation_status"] = "processing"
                report["interview_memory"] = self.session.memory_snapshot
                # 赋值放在改完之后：JSON 列不是 MutableDict，一旦被 flush 出去，之后再动那个 dict
                # 也不会再来一次 UPDATE（D170 那条是同族的反方向）。
                self.session.evaluation = report
                self.db.commit()
            else:
                # 评分已经全齐：丢掉上面那份可能已经过期的内存视图，按表重建再生成一次。
                self.evaluations = self._rebuild_evaluations()
                report = self._generate_report()
                report["evaluation_status"] = "completed"
                report["interview_memory"] = build_memory_snapshot(self.db, self.session_id)
                self.session.evaluation = report
                self.session.evaluation_status = "completed"
                self.session.memory_snapshot = report["interview_memory"]
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

    def _evaluate_answer(self, question: str, ref_answer: str, user_answer: str) -> dict[str, Any]:
        agent = AnswerEvaluationAgent()
        context = AgentContext()
        context.set_extra("question", question)
        context.set_extra("ref_answer", ref_answer)
        context.set_extra("user_answer", user_answer)
        return agent.run_impl(context)

    def _generate_report(self) -> dict[str, Any]:
        valid_evals = [
            item for item in self.evaluations if not item.get("timed_out") and item.get("overall_score", 0) > 0
        ]
        if not valid_evals:
            return self._fallback_report()

        avg_completeness = sum(item["completeness"] for item in valid_evals) / len(valid_evals)
        avg_accuracy = sum(item["accuracy"] for item in valid_evals) / len(valid_evals)
        avg_depth = sum(item["depth"] for item in valid_evals) / len(valid_evals)
        avg_expression = sum(item["expression"] for item in valid_evals) / len(valid_evals)

        # T3-2：平台评分规则权重（未配置回落默认 0.30/0.30/0.25/0.15）
        from app.services.interview_config_service import get_scoring_rules, scoring_rule_map

        scoring_rules = get_scoring_rules(self.db)
        # 权重归一化：配置里的权重和可能 ≠ 1（如只配了 0.10+0.60），
        # 不归一化会导致 overall_score 超过 100。归一化后恒落在 [0,100]。
        _DEFAULT_WEIGHTS = {"completeness": 0.30, "accuracy": 0.30, "depth": 0.25, "expression": 0.15}
        weights = dict(_DEFAULT_WEIGHTS)
        weights.update({k: v for k, v in scoring_rule_map(self.db).items() if k in _DEFAULT_WEIGHTS})
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}
        overall_score = round(
            avg_completeness * weights.get("completeness", 0.30)
            + avg_accuracy * weights.get("accuracy", 0.30)
            + avg_depth * weights.get("depth", 0.25)
            + avg_expression * weights.get("expression", 0.15)
        )

        ai_report: dict[str, Any] = {}
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
            "scoring_rules": scoring_rules,  # T3-2：租户评分规则（维度/权重/展示名）
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
            "evaluation_status": self.session.evaluation_status if self.session else "completed",
            "interview_memory": self.session.memory_snapshot if self.session else {},
        }
        return report

    def _fallback_report(self) -> dict[str, Any]:
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
            "evaluation_status": self.session.evaluation_status if self.session else "completed",
            "interview_memory": self.session.memory_snapshot if self.session else {},
        }

    def save_message(self, msg: dict[str, Any]):
        self._load_session()
        messages = list(self.session.messages or [])
        messages.append(msg)
        self.session.messages = messages
        self.db.commit()

    def get_current_question(self) -> dict[str, Any] | None:
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

    def _get_latest_question_message(self) -> dict[str, Any] | None:
        self._load_session()
        for msg in reversed(self.session.messages or []):
            if msg.get("type") == "question":
                return msg
        return None

    def _question_answered(self, question: dict[str, Any]) -> bool:
        """判断该题消息之后是否已有同 round 的作答（避免断线后重复推送已答题目）。

        只统计位置在该题消息「之后」的 answer：这样主题的作答不会把其后的追问
        误判为已答（追问与主题同 round）。
        """
        meta = question.get("metadata") or {}
        round_num = int(meta.get("round") or 0)
        if not round_num:
            return False
        messages = self.session.messages or []
        q_pos = None
        for idx, msg in enumerate(messages):
            if msg is question:
                q_pos = idx
                break
        if q_pos is None:
            return False
        for msg in messages[q_pos + 1 :]:
            if msg.get("type") == "answer" and (msg.get("metadata") or {}).get("round") == round_num:
                return True
        return False

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

    def _rebuild_evaluations(self) -> list[dict[str, Any]]:
        self._load_session()
        stored_evaluations = completed_evaluation_payloads(self.db, self.session_id)
        if stored_evaluations:
            return [
                {
                    "question_index": item["question_index"],
                    "question": item["question"],
                    "category": item["category"],
                    "user_answer": item["user_answer"],
                    "completeness": item["completeness"],
                    "accuracy": item["accuracy"],
                    "depth": item["depth"],
                    "expression": item["expression"],
                    "overall_score": item["overall_score"],
                    "feedback": item["feedback"],
                    "improvement": item["improvement"],
                    "follow_up": item["is_follow_up"],
                    "evidence": item["evidence"],
                    "turn_id": item["turn_id"],
                }
                for item in stored_evaluations
            ]
        questions = self.session.questions or []
        evaluations: list[dict[str, Any]] = []
        pending_answers: list[dict[str, Any]] = []
        active_question: dict[str, Any] | None = None

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
                evaluations.append(
                    {
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
                    }
                )
                continue

            if msg_type == "system" and "timeout_count" in meta:
                round_num = int(meta.get("round") or 0)
                question = self._resolve_question_snapshot(questions, active_question, round_num)
                evaluations.append(
                    {
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
                    }
                )

        return evaluations

    @staticmethod
    def _resolve_question_snapshot(
        questions: list[dict[str, Any]],
        active_question: dict[str, Any] | None,
        round_num: int,
    ) -> dict[str, Any]:
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
    def _parse_timestamp(timestamp: str | None) -> float | None:
        if not timestamp:
            return None
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _message_to_payload(message: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": message.get("type", ""),
            "content": message.get("content", ""),
            "metadata": message.get("metadata", {}),
        }
