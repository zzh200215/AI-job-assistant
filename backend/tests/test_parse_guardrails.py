"""P1.1 简历/JD 解析健壮化的**护栏**（`简历与面试优化.md` §4 P1.1 "测试护栏（先于功能代码，F1-0 纪律）"）。

这份护栏**先于功能代码写**（那天它是 7 红 4 绿，红的全部红在"契约还没实现"），实现落地后 14 条全绿。
它钉的是"改完之后必须长成什么样"，逐条对应文档那四条：

1. 长简历夹具（>15000 字符、尾部含最新工作经历）→ `test_long_resume_keeps_tail_experience_and_stamps_truncation`
   ＋ `test_raw_text_column_still_holds_the_whole_file`（截断只发生在喂给模型的那一份，库里不许丢）；
2. mock provider 返回残缺 JSON → `test_invalid_first_response_is_repaired_by_one_self_correction`
   ＋ `test_two_invalid_responses_land_the_degraded_marker_and_still_persist`（一次为限、仍失败要落库＋打标记）；
3. 结构感知截断单测（优先级表驱动）→ `test_section_priority_table_drops_low_priority_whole_sections`
   ＋ `test_tiny_budget_keeps_the_highest_priority_section_and_respects_the_limit`；
4. JD 解析同套夹具对齐 → `test_jd_parse_uses_the_same_budget_and_marker`
   ＋ `test_jd_invalid_response_gets_one_self_correction`。

两条**反向证据**（守卫没有反向证据等于没守卫）：`test_conforming_response_writes_no_meta_markers`
（合规结果不该被误判降级）、`test_short_resume_is_not_marked_truncated`（没超限不该打截断标记）。
还有一条是**替项目政策站岗的**：`test_jd_nullable_by_prompt_contract_is_not_a_validation_failure`——
`app/prompts/jd_parse.py` 原文指令"缺失字段填 null 或空数组"，校验器若不分"键必须存在/值允许 null"两档，
就会把 prompt 自己的合法输出判成降级。

**契约的出处**：阈值 15000、`_meta.truncation = {truncated, dropped_chars, dropped_sections}`、
`_meta.parse_degraded`、优先级表"基本信息→工作经历→项目→技能→教育→其他"、自纠一次为限、校验错误要回喂——
全部来自文档 §4 P1.1。**只有一处是我加的**：`_meta.validation_errors`（降级时把失败原因落进库，
好让 A2 那条"对内必须真的可查"有料可查）；这一条要否掉请直说，去掉它不影响其余断言。

`app.utils.text_budget` 是**故意在函数内部 import** 的：那条纯函数还没落地，写在模块顶层会让整个文件
收集失败（一个 ImportError 盖掉九条断言的红色信号），那样这份护栏就没有诊断价值了。
"""

from __future__ import annotations

from app.core.security import hash_password
from app.models.history import JobDescription, Resume
from app.models.user import User
from app.services import jd_service, resume_service
from app.services.parse_guard import REPAIR_HEADER

# 文档 §4 P1.1 的新阈值。钉成常量：改这个数必须同时改文档，不许悄悄漂移。
NEW_BUDGET = 15000

# 文档原话"基本信息→工作经历→项目→技能→教育→其他"，写成可 grep 的段名。
PRIORITY_HEADS = ("基本信息", "工作经历", "项目经历", "技能", "教育", "其他")

_FILLER = "负责召回链路建设与稳定性治理，量化成果见附录表格。"


def _section(head: str, body_chars: int, tail: str | None = None) -> str:
    """一段：段名独占一行 + 中文正文 +（可选）压在**段尾**的记号。

    记号放段尾是有意的：真实简历里最新的那份工作既可能写在工作经历开头（倒序排布），
    也可能写在结尾（正序排布）。把值钱的东西压在尾部，才量得出"从头上硬切"这种修法有没有真修掉。
    """
    repeats = max(1, body_chars // len(_FILLER))
    tail_line = f"\n{tail}" if tail else ""
    return f"{head}\n{_FILLER * repeats}{tail_line}\n"


def _resume_text() -> str:
    """一份**超过阈值**的简历，正序排布（最新工作经历压在工作经历段尾，约在第 7,000 字符处），
    低优先级的"其他"在文档最末——硬切 [:6000] 会先把最新那份工作丢掉。
    """
    parts = [
        _section("基本信息", 40, "姓名：测试用户｜邮箱：guard@example.com｜电话：13800000000"),
        _section(
            "工作经历",
            8000,
            "初级后端工程师 2021-07 至 2024-02 EARLY_JOB_MARKER\n高级后端工程师 2024-03 至今 TAIL_JOB_MARKER",
        ),
        _section("项目经历", 5000, "检索增强生成平台 PROJ_MARKER"),
        _section("技能", 3000, "Python FastAPI LangGraph SKILL_MARKER"),
        _section("教育", 900, "硕士 计算机科学与技术 EDU_MARKER"),
        _section("其他", 2000, "兴趣与开源贡献 MISC_MARKER"),
    ]
    raw = "\n".join(parts)
    # 夹具自证：超阈值 + 值钱的记号确实落在阈值之外，否则这条测试什么都没量。
    assert len(raw) > NEW_BUDGET, f"夹具长度 {len(raw)} 没超过 {NEW_BUDGET}，量不到截断"
    assert raw.index("TAIL_JOB_MARKER") > 6000, "尾部记号落得太靠前，硬切 [:6000] 也保得住，测不出缺陷"
    return raw


def _conforming_parse() -> dict:
    """键名逐字照 `app/prompts/resume_parse.py:13-28` 的 Schema——文档原稿字段清单里的 `projects` 是错的。"""
    return {
        "name": "测试用户",
        "phone": "13800000000",
        "email": "guard@example.com",
        "years_exp": 5,
        "education": "硕士",
        "major": "计算机科学与技术",
        "current_company": "某智能招聘平台",
        "current_title": "高级后端工程师",
        "skills": ["Python", "FastAPI", "LangGraph"],
        "work_experience": [
            {
                "company": "某智能招聘平台",
                "title": "高级后端工程师",
                "start": "2024-03",
                "end": "至今",
                "desc": "召回链路",
            }
        ],
        "project_experience": [
            {"name": "检索增强生成平台", "role": "负责人", "start": "", "end": "", "desc": "", "tech": ["Python"]}
        ],
        "self_evaluation": "五年后端，两年 LLM 应用",
    }


def _conforming_jd_parse() -> dict:
    return {
        "title": "大模型应用工程师",
        "company": "某智能招聘平台",
        "location": "武汉",
        "salary_range": "25-40K",
        "experience_requirement": "3-5年",
        "education_requirement": "本科及以上",
        "responsibilities": ["负责召回链路"],
        "required_skills": ["Python", "RAG"],
        "nice_to_have": ["LangGraph"],
        "keywords": ["RAG"],
    }


def _user(db, tag: str) -> User:
    user = User(
        username=f"guard_{tag}",
        email=f"guard_{tag}@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _run_resume_parse(db, monkeypatch, raw_text: str, responses: list[dict], tag: str) -> tuple[Resume, list[str]]:
    """走真实的 `resume_service.parse_and_save`，只换两处：抽文本、模型返回。
    返回落库后的行 + 每次调用看到的 prompt（便于断言"回喂"和"截断"）。
    """
    prompts: list[str] = []
    queue = list(responses)

    def fake_parse_resume(_path, _file_type):
        return raw_text

    def fake_chat_json(prompt, **_kw):
        prompts.append(prompt)
        return queue.pop(0) if queue else dict(responses[-1])

    monkeypatch.setattr(resume_service, "parse_resume", fake_parse_resume)
    monkeypatch.setattr(resume_service, "chat_json", fake_chat_json)

    row = Resume(
        user_id=_user(db, tag).id,
        file_name="long_resume.docx",
        file_path="uploads/long_resume.docx",
        file_type="docx",
        file_size=4096,
    )
    db.add(row)
    db.commit()

    return resume_service.parse_and_save(db, row.id), prompts


def _run_jd_parse(db, monkeypatch, raw_text: str, responses: list[dict], tag: str) -> tuple[JobDescription, list[str]]:
    prompts: list[str] = []
    queue = list(responses)

    def fake_chat_json(prompt, **_kw):
        prompts.append(prompt)
        return queue.pop(0) if queue else dict(responses[-1])

    monkeypatch.setattr(jd_service, "chat_json", fake_chat_json)

    row = JobDescription(
        user_id=_user(db, tag).id,
        title="大模型应用工程师",
        company="某智能招聘平台",
        raw_text=raw_text,
    )
    db.add(row)
    db.commit()

    return jd_service.parse_and_save(db, row.id), prompts


# ---------- 文档第 1 条：长简历不许把尾部切掉 ----------


def test_long_resume_keeps_tail_experience_and_stamps_truncation(db_session, monkeypatch):
    raw = _resume_text()
    resume, prompts = _run_resume_parse(db_session, monkeypatch, raw, [_conforming_parse()], "long")

    assert len(prompts) == 1, "合规的首发结果不该触发重试"
    assert "TAIL_JOB_MARKER" in prompts[0], "超长简历尾部那份最新工作经历被切掉了：仍是按字符从头硬切"
    assert len(prompts[0]) < len(raw), "超阈值文本应当被裁剪过，否则阈值没有生效"

    meta = (resume.parsed_json or {}).get("_meta", {})
    trunc = meta.get("truncation", {})
    assert trunc.get("truncated") is True, "裁剪发生了却没打截断标记——R1 的『静默丢数据』没有修掉"
    assert trunc.get("dropped_chars", 0) > 0
    assert isinstance(trunc.get("dropped_sections"), list) and trunc["dropped_sections"]


def test_raw_text_column_still_holds_the_whole_file(db_session, monkeypatch):
    """ "不静默丢数据"的另一半：裁剪只发生在喂模型的那份，`raw_text` 列必须存全文。
    存了全文，将来重解析才不需要用户重新上传。
    """
    raw = _resume_text()
    resume, _prompts = _run_resume_parse(db_session, monkeypatch, raw, [_conforming_parse()], "fulltext")
    assert resume.raw_text == raw


def test_short_resume_is_not_marked_truncated(db_session, monkeypatch):
    """反向证据：没超阈值的简历不该被盖上 truncation 标记，否则标记成了噪声。"""
    resume, prompts = _run_resume_parse(
        db_session, monkeypatch, "姓名：测试用户\n工作经历\n负责召回链路三年。\n", [_conforming_parse()], "short"
    )
    assert len(prompts[0]) <= NEW_BUDGET
    meta = (resume.parsed_json or {}).get("_meta", {})
    assert not meta.get("truncation", {}).get("truncated"), "短简历被误标截断"


# ---------- 文档第 2 条：schema 校验 + 一次自纠 ----------


def test_invalid_first_response_is_repaired_by_one_self_correction(db_session, monkeypatch):
    """缺 skills → 校验失败 → 把校验错误回喂模型改一次 → 第二次合规 → 落库且不带降级标记。"""
    missing_skills = _conforming_parse()
    del missing_skills["skills"]

    resume, prompts = _run_resume_parse(
        db_session,
        monkeypatch,
        "姓名：测试用户\n工作经历\n负责召回链路。\n",
        [missing_skills, _conforming_parse()],
        "repair",
    )

    assert len(prompts) == 2, f"首发残缺应触发一次自纠，实际调用 {len(prompts)} 次"
    assert prompts[1] != prompts[0], "第二次调用必须带上校验错误，不能原样重发"
    # 判据**不能取字段名**：两支 prompt 的 Schema 段里本来就写着 "skills"，"字段名在不在 prompt 里"恒真。
    # 取的是那纸回喂判单本身——它由 `parse_guard` 打上，且经 grep 确认两支 prompt 都没有这串字。
    assert REPAIR_HEADER in prompts[1] and REPAIR_HEADER not in prompts[0], "第二次调用没带回喂的校验单"
    assert "skills" in prompts[1].split(REPAIR_HEADER, 1)[1], "校验单里没写出出问题的字段名"

    meta = (resume.parsed_json or {}).get("_meta", {})
    assert not meta.get("parse_degraded"), "自纠成功的那次不该带降级标记"
    assert resume.parsed_json["skills"] == ["Python", "FastAPI", "LangGraph"]
    assert resume.name == "测试用户" and resume.email == "guard@example.com"


def test_two_invalid_responses_land_the_degraded_marker_and_still_persist(db_session, monkeypatch):
    """二次仍失败：**一次为限**（不许无限重试烧钱），但必须落库并打 `parse_degraded`。
    候选人侧静默归 A2 那条产品决策管，这里只钉"标记真的落进了库"。
    """
    bad = _conforming_parse()
    bad["work_experience"] = "三段工作经历"  # 类型不对：schema 声明是 list，模型给了字符串

    resume, prompts = _run_resume_parse(
        db_session, monkeypatch, "姓名：测试用户\n工作经历\n三段工作经历。\n", [bad, bad], "degraded"
    )

    assert len(prompts) == 2, f"自纠次数应恰好 1 次（共 2 次调用），实际 {len(prompts)} 次"
    assert resume.parsed_json is not None, "两次仍失败就把行丢掉：下游会拿到一条空解析"
    meta = resume.parsed_json.get("_meta", {})
    assert meta.get("parse_degraded") is True, "两次仍失败必须落降级标记"
    assert isinstance(meta.get("validation_errors"), list) and meta["validation_errors"], "降级标记没带失败原因"


def test_conforming_response_writes_no_meta_markers(db_session, monkeypatch):
    """反向证据：一次就合规的解析，两个标记都不该出现。"""
    resume, prompts = _run_resume_parse(
        db_session, monkeypatch, "姓名：测试用户\n工作经历\n负责召回链路。\n", [_conforming_parse()], "clean"
    )
    assert len(prompts) == 1
    meta = (resume.parsed_json or {}).get("_meta", {})
    assert "parse_degraded" not in meta
    assert not meta.get("truncation", {}).get("truncated")


# ---------- 文档第 3 条：结构感知截断，优先级表驱动 ----------


def test_section_priority_table_drops_low_priority_whole_sections():
    """优先级表就是文档那句"基本信息→工作经历→项目→技能→教育→其他"，超限时从尾部丢**整段**。"""
    from app.utils.text_budget import PRIORITY_ORDER, fit_structured_text

    assert list(PRIORITY_ORDER) == list(PRIORITY_HEADS), "优先级表与文档不符"

    raw = _resume_text()
    out = fit_structured_text(raw, NEW_BUDGET)

    assert out.truncated is True
    assert len(out.text) <= NEW_BUDGET
    for section in out.dropped_sections:
        assert section in PRIORITY_HEADS, f"丢段表里出现了不认识的名字：{section}"
        assert section not in out.text, f"{section} 标成丢了但正文里还有残片：切了半段"
    assert "TAIL_JOB_MARKER" in out.text, "工作经历保留优先级第二高，尾部那份最新工作不许丢"
    assert out.dropped_chars == len(raw) - len(out.text)


def test_tiny_budget_keeps_the_highest_priority_section_and_respects_the_limit():
    """极端预算：连一段都装不下时，仍要保住最高优先级的"基本信息"，且长度不越界。
    中文按字节硬切会出乱码，所以顺带钉一条"没有替换符"。
    """
    from app.utils.text_budget import fit_structured_text

    raw = _resume_text()
    tiny = fit_structured_text(raw, 200)
    assert len(tiny.text) <= 200
    assert "姓名" in tiny.text, "最低预算把最高优先级段整段丢了"
    # 按字节硬切会留下半个多字节序列；往返一次 utf-8 能抓到这种事（Python 的 str 切片本身切不开字符）。
    assert tiny.text.encode("utf-8").decode("utf-8") == tiny.text, "文本不是干净的 utf-8：截断切在字符中间了"

    exact = fit_structured_text(raw, len(raw))
    assert exact.truncated is False
    assert exact.dropped_sections == [] and exact.dropped_chars == 0


def test_text_without_any_recognizable_head_is_hard_cut_but_still_marked():
    """认不出段落是**常态不是意外**（纯图片型排版抽出来的文本、或段名写法不在别名表里）。
    这时退回硬切可以接受，但必须盖标记——R1 的罪名是"静默"，不是"裁剪"。
    """
    from app.utils.text_budget import fit_structured_text

    blob = "张三 13800000000 zhang@example.com " + "负责召回链路建设与稳定性治理。" * 1500
    out = fit_structured_text(blob, 15000)

    assert out.truncated is True, "认不出段落就什么都不标：这条又变回静默丢数据了"
    assert out.dropped_sections == [], "没认出任何段落，就不该声称丢了某段"
    assert len(out.text) <= 15000
    assert out.dropped_chars == len(blob) - len(out.text)


def test_a_single_oversized_section_is_not_dropped_to_nothing():
    """整份只有一栏超大工作经历时，丢到底会得到**一个空 prompt**——那一发必然解析失败，
    比硬切更糟。这一条钉的是"始终留一段"，是覆盖率门照出来的真缺陷。
    """
    from app.utils.text_budget import fit_structured_text

    one = "工作经历\n" + "负责召回链路建设与稳定性治理。" * 1500
    out = fit_structured_text(one, 15000)

    assert out.text.strip(), "把唯一那段也丢了：喂给模型的文本是空的"
    assert out.dropped_sections == [], "唯一的一段被当成'低优先级段'丢掉了"
    assert len(out.text) <= 15000 and out.truncated is True


def test_a_real_resume_head_prefixed_with_a_decoration_glyph_still_counts():
    """2026-10-16 扫库里 13 份真简历的抽取文本量到的排版：段名前挂一个 U+258E 左侧竖块
    （「专业技能」「项目经历」「教育背景」这类装饰真人在用）。不认它就等于整段没有归属——
    它的正文会被并进上一段，然后跟着上一段一起被丢。

    字面量用 `chr(0x258E)` 构造而不写进源码：这台机器的写入通道会改写生僻码位。
    只走公开接口（`fit_structured_text` 的丢段结果），不碰内部函数。
    """
    from app.utils.text_budget import fit_structured_text

    glyph = chr(0x258E)
    raw = (
        _section("基本信息", 40, "姓名：测试用户 zhang@example.com")
        + glyph
        + "专业技能\n"
        + "Python、FastAPI、RAG 检索链路建设。" * 120
        + "\n"
        + glyph
        + "教育背景\n"
        + "硕士 计算机科学与技术 主修课程与学分。" * 900
    )
    out = fit_structured_text(raw, 6000)

    assert "教育" in out.dropped_sections, f"带装饰前缀的段名没被当成独立段落，丢段表是 {out.dropped_sections}"
    assert glyph + "教育背景" not in out.text, "整段没丢干净，还剩半截"
    assert out.text.count("RAG 检索链路建设") > 0, "技能段被连带丢了"
    # 边界要取整个匹配的行首：取了别名起点的话，段名前那个装饰会被留在上一段尾巴上，
    # 于是"整段丢掉"的教育留下一个孤立的 ▎。数一遍符号个数比看文本更不容易糊过去。
    assert out.text.count(glyph) == 1, f"裁剪结果里残留了 {out.text.count(glyph)} 个装饰符，应为 1（技能段自己那处）"


def test_the_lines_before_the_first_section_head_survive_every_drop():
    """真实简历开头常是"张三 / 138xxx / 邮箱"这几行，上面没有段名。这一段没有归属，
    必须**永远不参与丢段**——否则丢完段落连姓名和联系方式都没了。
    """
    from app.utils.text_budget import fit_structured_text

    raw = (
        "张三\n13800000000\nzhang@example.com\n"
        + _section("工作经历", 400, "高级后端工程师 TAIL_JOB_MARKER")
        + _section("其他", 20000, "兴趣与开源贡献 MISC_MARKER")
    )
    out = fit_structured_text(raw, 1500)

    assert "张三" in out.text and "zhang@example.com" in out.text, "段名之前的引子被丢了"
    assert "TAIL_JOB_MARKER" in out.text, "唯一的工作经历段是没归属的引子之后第一个可丢单元，不该被丢"
    assert "其他" in out.dropped_sections


# ---------- 文档第 4 条：JD 同套夹具对齐 ----------


def test_jd_parse_uses_the_same_budget_and_marker(db_session, monkeypatch):
    """JD 侧同族债：截断不在 `jd_parse_agent.py`（那只是壳），真位置是 `jd_service.py:27` 的 `[:4000]`。
    超阈值时同样要保尾部、同样要打标记。
    """
    raw = _section("岗位职责", 18000) + _section("任职要求", 3000, "必备：RAG 与评测体系 JD_TAIL_MARKER")
    assert "JD_TAIL_MARKER" in raw[-4000:], "夹具的记号得在尾部才量得出硬切"

    jd, prompts = _run_jd_parse(db_session, monkeypatch, raw, [_conforming_jd_parse()], "jdbudget")

    assert len(prompts) == 1
    assert "JD_TAIL_MARKER" in prompts[0], "JD 尾部职责被硬切：JD 侧仍在用 [:4000] 之类的头切"
    meta = (jd.parsed_json or {}).get("_meta", {})
    assert meta.get("truncation", {}).get("truncated") is True, "JD 侧裁剪了却没打标记"


def test_jd_invalid_response_gets_one_self_correction(db_session, monkeypatch):
    """JD 的 `required_skills` 实测有 52% 落库就是空的或 null——校验＋一次自纠是这条链的入口。"""
    no_skills = _conforming_jd_parse()
    del no_skills["required_skills"]

    jd, prompts = _run_jd_parse(
        db_session,
        monkeypatch,
        "岗位职责：负责 RAG 检索链路。必备：Python。",
        [no_skills, _conforming_jd_parse()],
        "jdrepair",
    )

    assert len(prompts) == 2, "JD 首发缺 required_skills 未触发自纠——两支必须共用同一套校验"
    assert REPAIR_HEADER in prompts[1] and "required_skills" in prompts[1].split(REPAIR_HEADER, 1)[1]
    meta = (jd.parsed_json or {}).get("_meta", {})
    assert not meta.get("parse_degraded")
    assert jd.parsed_json["required_skills"] == ["Python", "RAG"]


def test_jd_nullable_by_prompt_contract_is_not_a_validation_failure(db_session, monkeypatch):
    """值取 null 是 prompt **自己指令**的合法形状，不许判成校验失败。
    这条站的是文档 §4 修法表里"两档制"那句：键必须存在 / 值允许 null。
    """
    nulls = _conforming_jd_parse()
    nulls["nice_to_have"] = None
    nulls["salary_range"] = None

    jd, prompts = _run_jd_parse(db_session, monkeypatch, "岗位职责：负责 RAG 检索链路。", [nulls], "jdnull")

    assert len(prompts) == 1, "prompt 自己指令的 null 被判成校验失败，触发了无谓的重试"
    meta = (jd.parsed_json or {}).get("_meta", {})
    assert not meta.get("parse_degraded"), "prompt 指令的 null 被写成了降级"
