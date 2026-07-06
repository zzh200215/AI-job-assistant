# -*- coding: utf-8 -*-
"""简历相关业务：上传文件 + 解析为结构化 JSON"""
import os
import uuid
from datetime import datetime
from typing import Dict, Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.history import Resume
from app.prompts.rendering import render_prompt
from app.prompts.resume_parse import RESUME_PARSE_PROMPT
from app.services.llm_service import chat_json
from app.utils.file_access import resolve_upload_path
from app.utils.file_parser import parse_resume


def _date_dir() -> str:
    """返回 uploads/YYYY/MM 子目录"""
    now = datetime.now()
    return os.path.join(settings.UPLOAD_DIR, str(now.year), f"{now.month:02d}")


def save_upload_file(file_bytes: bytes, original_filename: str) -> Dict[str, Any]:
    """
    落盘简历文件，返回元信息。
    按 uploads/YYYY/MM/uuid.ext 结构存储。
    """
    ext = os.path.splitext(original_filename)[1].lower().lstrip(".")
    stored_name = f"{uuid.uuid4().hex}.{ext}"

    rel_dir = _date_dir()
    abs_dir = os.path.abspath(rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    abs_path = os.path.join(abs_dir, stored_name)
    with open(abs_path, "wb") as f:
        f.write(file_bytes)

    file_size = len(file_bytes)
    rel_path = os.path.join(rel_dir, stored_name).replace("\\", "/")
    return {
        "file_name": original_filename,
        "file_path": rel_path,
        "file_type": ext,
        "file_size": file_size,
    }


def parse_and_save(db: Session, resume_id: int) -> Resume:
    """
    根据 resume_id 读取文件 -> 抽文本 -> LLM 解析 -> 写回 DB
    """
    resume = db.get(Resume, resume_id)
    if not resume:
        raise ValueError(f"简历 {resume_id} 不存在")

    abs_path = str(resolve_upload_path(resume.file_path))

    try:
        raw_text = parse_resume(abs_path, resume.file_type)
    except Exception as e:
        err_msg = str(e)
        # 将具体错误转换为友好提示
        if "encrypted" in err_msg.lower() or "password" in err_msg.lower():
            raise ValueError("该 PDF 文件已加密，请先解密后重新上传")
        if "未开启 ocr" in err_msg.lower() or "tesseract" in err_msg.lower():
            raise ValueError("当前环境未开启 OCR 简历识别，请联系管理员开启后再上传图片简历或扫描件 PDF")
        if "扫描" in err_msg or "image" in err_msg.lower() or "图片 ocr" in err_msg.lower() or "图片型 pdf" in err_msg.lower():
            raise ValueError("该文件为扫描件或图片简历，OCR 未识别出有效文本，请更换更清晰图片或上传可编辑 PDF / DOCX")
        if "not a pdf" in err_msg.lower() or "corrupt" in err_msg.lower():
            raise ValueError("文件格式已损坏，请检查后重新上传")
        raise ValueError(f"文件解析失败: {err_msg}")

    if not raw_text or not raw_text.strip():
        raise ValueError("从文件中未能提取到有效文本，请检查文件内容")

    # 截断避免超长
    prompt = render_prompt(RESUME_PARSE_PROMPT, resume_text=raw_text[:6000])
    parsed: Dict[str, Any] = chat_json(prompt)

    resume.raw_text = raw_text
    resume.parsed_json = parsed
    resume.name = parsed.get("name")
    resume.phone = parsed.get("phone")
    resume.email = parsed.get("email")
    resume.years_exp = parsed.get("years_exp") or 0

    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume
