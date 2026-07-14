"""JD 相关路由"""

import traceback

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.history import JobDescription
from app.models.user import User
from app.schemas.jd import JDCreateReq, JDCreateResp, JDParseResp
from app.services import jd_service
from app.utils.job_access import get_accessible_job
from app.utils.response import ERR_AI, ERR_PARAM, fail, ok

router = APIRouter()


@router.post("", summary="创建岗位 JD（同时可选解析）")
async def create_jd(
    payload: JDCreateReq, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    # ---- JD 文本非空校验 ----
    if not payload.raw_text or not payload.raw_text.strip():
        return fail(message="JD 内容不能为空", code=ERR_PARAM)

    try:
        jd = jd_service.create_jd(db, payload.title, payload.company, payload.raw_text, user_id=current_user.id)
    except Exception as e:
        return fail(message=f"JD 保存失败: {str(e)}", code=ERR_PARAM)

    return ok(
        JDCreateResp(
            id=jd.id,
            title=jd.title,
            company=jd.company,
            raw_text=jd.raw_text,
            parsed=jd.parsed_json or {},
        ).model_dump(),
        message="JD 创建成功",
    )


@router.post("/parse", summary="解析 JD（调用 LLM）")
async def parse_jd(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    jd_id = payload.get("jd_id")
    if not jd_id:
        return fail(message="jd_id 必填", code=ERR_PARAM)

    # 权限校验
    jd = (
        db.query(JobDescription)
        .filter(JobDescription.id == int(jd_id), JobDescription.user_id == current_user.id)
        .first()
    )
    if not jd:
        return fail(message="JD 不存在或无权限", code=ERR_PARAM)

    try:
        jd = jd_service.parse_and_save(db, int(jd_id))
    except ValueError as e:
        return fail(message=str(e), code=ERR_PARAM)
    except Exception as e:
        traceback.print_exc()
        return fail(message=f"AI 解析失败: {str(e)}", code=ERR_AI)

    return ok(
        JDParseResp(
            id=jd.id,
            title=jd.title,
            parsed=jd.parsed_json or {},
            salary_range=jd.salary_range,
            location=jd.location,
        ).model_dump(),
        message="JD 解析成功",
    )


@router.get("/list", summary="JD 列表")
async def list_jd(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(JobDescription).filter(
        JobDescription.user_id == current_user.id,
    )
    q = q.order_by(JobDescription.create_time.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return ok(
        {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": j.id,
                    "title": j.title,
                    "company": j.company,
                    "location": j.location,
                    "salary_range": j.salary_range,
                    "create_time": j.create_time.isoformat() if j.create_time else None,
                }
                for j in items
            ],
        }
    )


@router.get("/{jd_id}", summary="获取 JD 详情")
async def get_jd(jd_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    jd = get_accessible_job(db, jd_id, current_user)
    if not jd:
        return fail(message="JD 不存在或无权限", code=ERR_PARAM)
    return ok(
        {
            "id": jd.id,
            "title": jd.title,
            "company": jd.company,
            "location": jd.location,
            "salary_range": jd.salary_range,
            "raw_text": jd.raw_text,
            "parsed": jd.parsed_json or {},
            "create_time": jd.create_time.isoformat() if jd.create_time else None,
        }
    )


# ============================================================
# JD 智能导入增强
# ============================================================


@router.post("/import-url", summary="从URL粘贴导入JD")
async def import_jd_from_url(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    从招聘网站URL粘贴导入JD。
    支持粘贴URL，系统自动抓取页面内容并解析。
    如果URL不可访问，用户也可以直接粘贴网页文本。
    """
    url = payload.get("url", "").strip()
    raw_text = payload.get("raw_text", "").strip()

    if not url and not raw_text:
        return fail(message="url 或 raw_text 至少填一项", code=ERR_PARAM)

    # 如果有URL，尝试抓取
    if url:
        try:
            fetched_text = _fetch_jd_from_url(url)
            if fetched_text:
                raw_text = fetched_text
        except Exception:
            if not raw_text:
                return fail(message="无法抓取URL内容，请直接粘贴网页文本", code=ERR_PARAM)

    if not raw_text:
        return fail(message="未获取到JD内容", code=ERR_PARAM)

    # 创建 JD
    try:
        jd = jd_service.create_jd(db, title="", company="", raw_text=raw_text, user_id=current_user.id)
        # 自动解析
        jd = jd_service.parse_and_save(db, jd.id)
    except Exception as e:
        return fail(message=f"JD 导入失败: {str(e)}", code=ERR_AI)

    return ok(
        {
            "id": jd.id,
            "title": jd.title,
            "company": jd.company,
            "parsed": jd.parsed_json or {},
            "salary_range": jd.salary_range,
            "location": jd.location,
            "source_url": url,
        },
        message="JD 从URL导入成功",
    )


@router.post("/batch-import", summary="批量导入JD")
async def batch_import_jds(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量导入多个JD。
    支持: 文本列表（用空行或---分隔多个JD）、JSON数组。
    """
    items = payload.get("items", [])
    raw_text = payload.get("raw_text", "").strip()
    auto_parse = payload.get("auto_parse", True)

    # 如果提供了合并文本，按分隔符拆分
    if raw_text and not items:
        # 按 --- 或连续两个以上空行分割
        import re

        chunks = re.split(r"\n\s*---\s*\n|\n{3,}", raw_text)
        items = [{"raw_text": chunk.strip()} for chunk in chunks if chunk.strip()]

    if not items:
        return fail(message="items 或 raw_text 至少填一项", code=ERR_PARAM)

    results = []
    errors = []

    for idx, item in enumerate(items):
        text = item.get("raw_text", "").strip()
        if not text:
            errors.append({"index": idx, "error": "内容为空"})
            continue

        try:
            jd = jd_service.create_jd(
                db,
                title=item.get("title", ""),
                company=item.get("company", ""),
                raw_text=text,
                user_id=current_user.id,
            )
            if auto_parse:
                jd = jd_service.parse_and_save(db, jd.id)

            results.append(
                {
                    "index": idx,
                    "id": jd.id,
                    "title": jd.title,
                    "company": jd.company,
                    "parsed": jd.parsed_json or {},
                }
            )
        except Exception as e:
            errors.append({"index": idx, "error": str(e)})

    return ok(
        {
            "imported": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        },
        message=f"批量导入完成: 成功 {len(results)} 个, 失败 {len(errors)} 个",
    )


def _fetch_jd_from_url(url: str) -> str:
    """从URL抓取JD内容"""
    import httpx
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    with httpx.Client(headers=headers, follow_redirects=True, timeout=15) as client:
        resp = client.get(url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # 移除脚本和样式
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # 尝试找到职位描述区域
    jd_selectors = [
        {
            "class_": lambda c: c
            and any(
                k in str(c).lower()
                for k in ["job-desc", "job-desc", "detail-content", "job_detail", "position-content"]
            )
        },
        {"class_": lambda c: c and any(k in str(c).lower() for k in ["description", "detail", "content-body"])},
    ]

    for sel in jd_selectors:
        container = soup.find("div", **sel)
        if container:
            return container.get_text(separator="\n", strip=True)

    # 回退：取 body 全文
    body = soup.find("body")
    if body:
        text = body.get_text(separator="\n", strip=True)
        # 截取前 5000 字符避免过大
        return text[:5000]

    return ""
