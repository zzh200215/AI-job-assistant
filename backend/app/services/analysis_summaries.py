"""简历 / JD 的一行式摘要：给 prompt 当输入用的紧凑文本。

原先住在这个位置的是 `agent_steps.py` 的 11 个裸步骤函数（`step_by_step` 编排），
它们与 linear/layered 两条流水线重复，已随该策略一起删除；只有这两个摘要构造器
被 IntentAgent 与 SummaryAgent 复用，所以留在这里。
"""

from app.models.history import JobDescription, Resume


def resume_digest(resume: Resume | None) -> str:
    if not resume:
        return "无简历信息"
    parsed = resume.parsed_json or {}
    parts = [
        f"姓名: {parsed.get('name', '未知')}",
        f"工作年限: {parsed.get('years_exp', 0)}年",
        f"技能: {', '.join((parsed.get('skills') or [])[:8])}",
        f"当前公司: {parsed.get('current_company', '未知')}",
        f"当前职位: {parsed.get('current_title', '未知')}",
    ]
    return "\n".join(parts)


def jd_digest(jd: JobDescription | None) -> str:
    if not jd:
        return "无JD信息"
    parsed = jd.parsed_json or {}
    parts = [
        f"岗位: {parsed.get('title', jd.title or '未知')}",
        f"公司: {parsed.get('company', jd.company or '未知')}",
        f"地点: {parsed.get('location', '未知')}",
        f"薪资: {parsed.get('salary_range', '未知')}",
        f"必备技能: {', '.join((parsed.get('required_skills') or [])[:8])}",
    ]
    return "\n".join(parts)
