"""外部能力端点（T6-1）：简历解析 / 匹配评估 / 模拟面试。

统一响应：成功 `{"success": true, "data": {...}, "request_id": "..."}`；
失败 `{"success": false, "error": "..."}`（HTTP 4xx/5xx）。
每次调用写 api_usage（成功计费、失败不计费）。
"""

from __future__ import annotations

import base64
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.external.auth import require_api_key
from app.core.database import get_db
from app.core.tenant_context import TenantContext, reset_current_tenant, set_current_tenant
from app.models.api_key import ApiKey
from app.services import external_service
from app.services.api_key_service import record_usage

router = APIRouter(prefix="/external", tags=["external-capabilities"])


def _tenant_token(key: ApiKey):
    """按 Key 归属租户注入租户上下文，供 RAG / tenant_filter 使用。"""
    return set_current_tenant(TenantContext(tenant_id=key.tenant_id))


def _run(db, key, endpoint, fn, request_id: str = "", event: str = ""):
    token = _tenant_token(key)
    try:
        try:
            data = fn()
        except ValueError as exc:
            record_usage(db, key=key, endpoint=endpoint, status="failed", request_id=request_id)
            # 业务失败返回 HTTP 400（与「success:false 即 4xx」的契约一致），
            # 不再用 HTTP 200 兜成功语义；失败调用已记 usage（计配额但不计费）。
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": str(exc), "request_id": request_id},
            )
        record_usage(db, key=key, endpoint=endpoint, status="success", request_id=request_id)
        if event:
            from app.services.webhook_service import publish_event

            publish_event(db, api_key_id=key.id, event=event, payload=data)
        return {"success": True, "data": data, "request_id": request_id}
    finally:
        reset_current_tenant(token)


def _rid(payload: dict) -> str:
    rid = str(payload.get("request_id") or "").strip()
    return rid or uuid.uuid4().hex


@router.post("/resume/parse", summary="外部：简历解析")
def external_resume_parse(
    payload: dict,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    request_id = _rid(payload)

    def fn():
        file_b64 = payload.get("file_base64")
        filename = str(payload.get("filename") or "")
        if file_b64:
            return external_service.parse_resume_file(base64.b64decode(file_b64), filename or "resume.txt", db=db)
        return external_service.parse_resume_text(str(payload.get("content") or ""), db=db)

    return _run(db, key, "resume.parse", fn, request_id, event="resume.parsed")


@router.post("/match/evaluate", summary="外部：简历 × JD 匹配评估")
def external_match_evaluate(
    payload: dict,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    request_id = _rid(payload)

    def fn():
        rag_context = ""
        if payload.get("use_rag"):
            from app.services.rag_service import build_rag_context_multi

            query = str(payload.get("jd") or {}).get("title") if isinstance(payload.get("jd"), dict) else str(payload.get("jd") or "")
            ctx = build_rag_context_multi(query or "岗位匹配", db, user_id=None, intent="match")
            rag_context = ctx.get("all", "")
        return external_service.evaluate_match(payload.get("resume"), payload.get("jd"), rag_context=rag_context, db=db)

    return _run(db, key, "match.evaluate", fn, request_id, event="match.evaluated")


@router.post("/interview/simulate", summary="外部：模拟面试（生成题 + 可选逐题评分）")
def external_interview_simulate(
    payload: dict,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    request_id = _rid(payload)

    def fn():
        answers = payload.get("answers") or []
        # 成本防护：逐题评分是 N 次 LLM 调用，而单次请求只记 1 笔账单，
        # 必须限制答案数量；超限时在生成题之前拒绝，避免白耗一次 LLM。
        MAX_ANSWERS = 20
        if isinstance(answers, list) and len(answers) > MAX_ANSWERS:
            raise ValueError(f"answers 数量超出上限（最多 {MAX_ANSWERS} 条）")
        result = external_service.generate_interview_questions(
            payload.get("resume"), payload.get("jd"), db=db
        )
        if isinstance(answers, list) and answers:
            evaluations = []
            for item in answers:
                question = str(item.get("question") or "")
                ref_answer = str(item.get("ref_answer") or "")
                user_answer = str(item.get("answer") or "")
                evaluation = external_service.evaluate_answer(
                    question, ref_answer, user_answer, db=db
                )
                evaluations.append(
                    {
                        "question": question,
                        "evaluation": evaluation,
                    }
                )
            result["evaluations"] = evaluations
        return result

    return _run(db, key, "interview.simulate", fn, request_id, event="interview.completed")
