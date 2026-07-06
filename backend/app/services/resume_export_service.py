# -*- coding: utf-8 -*-
"""
简历智能生成与导出服务

功能：
  1. generate_optimized() — AI 生成优化版简历
  2. export_docx() — 导出 Word
  3. export_pdf() — 导出 PDF
"""
import os
import json
import uuid
import re
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.utils.time_helper import utc_now
from app.models.history import Resume, JobDescription, AnalysisRecord, ResumeVersion
from app.prompts.resume_generate import RESUME_GENERATE_PROMPT
from app.services.llm_service import chat_json
from app.utils.service_access import get_accessible_job_for_user, get_owned_resume
from app.utils.response import ok, fail


def generate_optimized(
    db: Session,
    resume_id: int,
    jd_id: Optional[int] = None,
    user_id: int | None = None,
) -> Dict[str, Any]:
    """
    生成优化版简历。
    1. 读取原简历 parsed_json
    2. 读取最新的优化建议（优先匹配指定 jd_id）
    3. 调用 AI 生成
    4. 保存到 resume.optimized_content 和 resume_version 表
    5. 返回生成结果
    """
    resume = (
        get_owned_resume(db, resume_id, user_id)
        if user_id is not None
        else db.query(Resume).filter(Resume.id == resume_id, Resume.is_deleted == 0).first()
    )
    if not resume:
        raise ValueError("简历不存在")
    if not resume.parsed_json:
        raise ValueError("简历未解析，请先解析简历")

    # 查找优化建议
    optimize_suggestions = {}
    jd_info = "无特定目标岗位"

    query = db.query(AnalysisRecord).filter(
        AnalysisRecord.resume_id == resume_id,
        AnalysisRecord.is_deleted == 0,
    )
    if user_id is not None:
        query = query.filter(AnalysisRecord.user_id == user_id)
    if jd_id:
        query = query.filter(AnalysisRecord.jd_id == jd_id)
    query = query.order_by(AnalysisRecord.create_time.desc())

    latest = query.first()
    if latest:
        optimize_suggestions = latest.optimize_suggestions or {}
        jd_obj = (
            get_accessible_job_for_user(db, latest.jd_id, user_id)
            if user_id is not None
            else db.get(JobDescription, latest.jd_id)
        )
        if jd_obj:
            parsed = jd_obj.parsed_json or {}
            parts = [
                f"岗位: {parsed.get('title', jd_obj.title or '')}",
                f"公司: {parsed.get('company', jd_obj.company or '')}",
                f"技能: {', '.join(parsed.get('required_skills', [])[:8])}",
                f"职责: {chr(10).join(parsed.get('responsibilities', [])[:3])}",
            ]
            jd_info = "\n".join(parts)

    # 调用 AI
    prompt = RESUME_GENERATE_PROMPT.format(
        original_resume=json.dumps(resume.parsed_json, ensure_ascii=False, indent=2),
        optimize_suggestions=json.dumps(optimize_suggestions, ensure_ascii=False, indent=2),
        jd_info=jd_info,
    )
    result: Dict[str, Any] = chat_json(prompt)

    # 保存到 resume 表
    markdown = result.get("markdown_content", "")
    resume.optimized_content = markdown
    resume.optimized_at = utc_now()
    db.add(resume)

    # 保存版本记录（Markdown）
    md_version = ResumeVersion(
        resume_id=resume_id,
        version_type="optimized",
        content=markdown,
        format="md",
    )
    db.add(md_version)
    # 保存结构化数据版本
    structured = result.get("structured_data", {})
    if structured:
        json_version = ResumeVersion(
            resume_id=resume_id,
            version_type="optimized",
            content=json.dumps(structured, ensure_ascii=False),
            format="json",
        )
        db.add(json_version)
    db.commit()
    db.refresh(md_version)

    return {
        "version_id": md_version.id,
        "markdown_content": markdown,
        "structured_data": result.get("structured_data", {}),
        "changes_log": result.get("changes_log", []),
        "created_at": md_version.created_at.isoformat() if md_version.created_at else None,
    }


def _build_docx(doc, markdown_content: str, style_title: str):
    """将 Markdown 转换为 python-docx 格式"""
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    lines = markdown_content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 一级标题 # 姓名 | ...
        if line.startswith("# ") and not line.startswith("## "):
            if i == 0:
                # 第一行是姓名+联系方式
                parts = line[2:].split("|")
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(parts[0].strip())
                run.bold = True
                run.font.size = Pt(18)
                if len(parts) > 1:
                    sub = doc.add_paragraph()
                    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    sub_run = sub.add_run(" | ".join(p.strip() for p in parts[1:]))
                    sub_run.font.size = Pt(10)
                    sub_run.font.color.rgb = RGBColor(100, 100, 100)
            else:
                p = doc.add_paragraph()
                run = p.add_run(line[2:])
                run.bold = True
                run.font.size = Pt(16)

        # 二级标题 ##
        elif line.startswith("## "):
            p = doc.add_paragraph()
            run = p.add_run(line[3:])
            run.bold = True
            run.font.size = Pt(14)
            run.font.color.rgb = RGBColor(0, 102, 204)

        # 三级标题 ###
        elif line.startswith("### "):
            p = doc.add_paragraph()
            run = p.add_run(line[4:])
            run.bold = True
            run.font.size = Pt(12)

        # 列表项 -
        elif line.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            # 处理 **粗体**
            text = line[2:]
            parts = re.split(r'(\*\*.*?\*\*)', text)
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    run = p.add_run(part[2:-2])
                    run.bold = True
                else:
                    p.add_run(part)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)

        # 空行
        elif line == "":
            pass

        # 普通段落
        else:
            p = doc.add_paragraph(line)

        i += 1


def export_docx(
    resume_id: int,
    version: str = "optimized",
    db: Session = None,
    user_id: int | None = None,
) -> str:
    """
    导出简历为 Word 文件。
    返回文件相对路径（相对于 uploads/）。
    """
    if db is None:
        from app.core.database import SessionLocal
        db = SessionLocal()
        close = True
    else:
        close = False

    try:
        resume = (
            get_owned_resume(db, resume_id, user_id)
            if user_id is not None
            else db.query(Resume).filter(Resume.id == resume_id, Resume.is_deleted == 0).first()
        )
        if not resume:
            raise ValueError("简历不存在")

        # 获取内容
        if version == "optimized" and resume.optimized_content:
            content = resume.optimized_content
        else:
            # 原简历：从 parsed_json 构建 markdown
            content = _build_original_md(resume)

        # 生成文件
        from docx import Document
        from docx.shared import Pt
        doc = Document()

        # 设置默认字体
        style = doc.styles["Normal"]
        style.font.name = "Microsoft YaHei"
        style.font.size = Pt(11)

        _build_docx(doc, content, version)

        # 保存
        ext = "docx"
        stored_name = f"resume_{resume_id}_{version}_{uuid.uuid4().hex}.{ext}"
        now = datetime.now()
        rel_dir = os.path.join(settings.UPLOAD_DIR, "export", str(now.year), f"{now.month:02d}")
        abs_dir = os.path.abspath(rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        abs_path = os.path.join(abs_dir, stored_name)
        doc.save(abs_path)

        rel_path = os.path.join(rel_dir, stored_name).replace("\\", "/")
        return rel_path

    finally:
        if close:
            db.close()


def export_pdf(
    resume_id: int,
    version: str = "optimized",
    db: Session = None,
    user_id: int | None = None,
) -> str:
    """
    导出简历为 PDF 文件。
    使用 weasyprint 将 Markdown 转为 HTML 再转 PDF。
    """
    if db is None:
        from app.core.database import SessionLocal
        db = SessionLocal()
        close = True
    else:
        close = False

    try:
        resume = (
            get_owned_resume(db, resume_id, user_id)
            if user_id is not None
            else db.query(Resume).filter(Resume.id == resume_id, Resume.is_deleted == 0).first()
        )
        if not resume:
            raise ValueError("简历不存在")

        if version == "optimized" and resume.optimized_content:
            content = resume.optimized_content
        else:
            content = _build_original_md(resume)

        # Markdown → HTML
        html = _md_to_html(content)

        # HTML → PDF
        from weasyprint import HTML as WeasyprintHTML

        stored_name = f"resume_{resume_id}_{version}_{uuid.uuid4().hex}.pdf"
        now = datetime.now()
        rel_dir = os.path.join(settings.UPLOAD_DIR, "export", str(now.year), f"{now.month:02d}")
        abs_dir = os.path.abspath(rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        abs_path = os.path.join(abs_dir, stored_name)

        WeasyprintHTML(string=html).write_pdf(abs_path)

        rel_path = os.path.join(rel_dir, stored_name).replace("\\", "/")
        return rel_path

    except ImportError:
        raise RuntimeError("PDF导出需要安装 weasyprint: pip install weasyprint")
    finally:
        if close:
            db.close()


def _build_original_md(resume: Resume) -> str:
    """从 parsed_json 构建原简历的 Markdown"""
    p = resume.parsed_json or {}
    lines = []

    name = p.get("name", "姓名")
    phone = p.get("phone", "")
    email = p.get("email", "")
    lines.append(f"# {name} | {phone} | {email}")
    lines.append("")

    # 技能
    skills = p.get("skills", [])
    if skills:
        lines.append("## 技能清单")
        lines.append("- " + "、".join(skills))
        lines.append("")

    # 工作经历
    exp = p.get("work_experience", []) or p.get("experience", [])
    if exp:
        lines.append("## 工作经历")
        for e in exp:
            company = e.get("company", "")
            title = e.get("title", "") or e.get("position", "")
            period = f"{e.get('start', '')} - {e.get('end', '')}"
            lines.append(f"### {company} · {title} · {period}")
            desc = e.get("desc", "")
            if desc:
                for d in desc.split("\n"):
                    if d.strip():
                        lines.append(f"- {d.strip()}")
            lines.append("")

    # 项目
    projs = p.get("project_experience", []) or p.get("projects", [])
    if projs:
        lines.append("## 项目经验")
        for pr in projs:
            name = pr.get("name", "")
            role = pr.get("role", "")
            lines.append(f"### {name} · {role}")
            tech = pr.get("tech", []) or pr.get("tech_stack", [])
            if tech:
                lines.append(f"- 技术栈：{'、'.join(tech)}")
            desc = pr.get("desc", "")
            if desc:
                lines.append(f"- {desc}")
            results = pr.get("results", "")
            if results:
                lines.append(f"- {results}")
            lines.append("")

    # 教育
    edu = p.get("education", [])
    if edu:
        lines.append("## 教育背景")
        if isinstance(edu, list):
            for e in edu:
                school = e.get("school", "")
                major = e.get("major", "")
                degree = e.get("degree", "")
                period = e.get("time", "")
                lines.append(f"- {school} · {major} · {degree} · {period}")
        elif isinstance(edu, str):
            lines.append(f"- {edu}")
        lines.append("")

    return "\n".join(lines)


def _md_to_html(md: str) -> str:
    """简易 Markdown → HTML 转换（用于 PDF 导出）"""
    lines = md.split("\n")
    html_parts = ['<!DOCTYPE html><html><head><meta charset="utf-8">',
                  '<style>',
                  'body{font-family:"Microsoft YaHei",sans-serif;padding:40px;line-height:1.6;}',
                  'h1{font-size:22px;text-align:center;margin-bottom:4px;}',
                  'h2{font-size:16px;color:#0066CC;border-bottom:1px solid #ddd;padding-bottom:4px;margin-top:20px;}',
                  'h3{font-size:14px;margin-top:12px;}',
                  'ul{padding-left:20px;}',
                  'li{margin:4px 0;}',
                  '.contact{text-align:center;color:#666;font-size:12px;}',
                  '</style></head><body>']

    for line in lines:
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            text = line[2:]
            parts = text.split("|")
            html_parts.append(f'<h1>{parts[0].strip()}</h1>')
            if len(parts) > 1:
                html_parts.append(f'<p class="contact">{" | ".join(p.strip() for p in parts[1:])}</p>')
        elif line.startswith("## "):
            html_parts.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith("### "):
            html_parts.append(f'<h3>{line[4:]}</h3>')
        elif line.startswith("- "):
            text = line[2:]
            html_parts.append(f"<li>{text}</li>")
        elif line == "":
            pass
        else:
            html_parts.append(f"<p>{line}</p>")

    html_parts.append("</body></html>")
    return "\n".join(html_parts)
