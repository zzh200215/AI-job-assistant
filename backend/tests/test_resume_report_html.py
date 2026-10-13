"""报告 HTML 渲染器：产出必须过自己的机检，且候选人写的东西进不了标签。

`render_report_html` 在返回前跑 `lint_report_html`，所以这一族用例只要不抛异常，
就等于"导航↔模块一一对应、编号↔批注一一对应、声明数=实际数、无外部资源、
合计行=逐维相加、无禁词无示例值"这七件事同时成立。
"""

from __future__ import annotations

import pytest

from app.services.report_html_lint import MODULE_IDS, lint_report_html
from app.services.resume_blocks import build_report_sections
from app.services.resume_report_html import render_report_html
from app.services.resume_report_schema import Redline, RedlineBlock, RedlineEdit, Report
from app.services.resume_report_service import load_apply_strategy

SELF_EVAL = "1 年多 AI 应用开发经验，做过法律、金融、电网三个场景"
PROJ = "证据检索准确率约 92%，这套检索链路是我搭的。最大执行步数写在配置里。"
PARSED = {
    "name": "示例候选人",
    "phone": "13600000001",
    "email": "z@example.com",
    "years_exp": 2,
    "education": "本科",
    "major": "计算机科学与技术",
    "current_title": "AI 应用开发工程师（RAG / Agent）",
    "self_evaluation": SELF_EVAL,
    "skills": ["LangChain", "BM25", "RRF", "FastAPI"],
    "work_experience": [
        {"company": "上海合提", "title": "AI 应用开发", "start": "2024.11", "end": "至今", "desc": "负责检索链路"}
    ],
    "project_experience": [{"name": "法律智能体平台", "role": "主程", "tech": ["FastAPI", "LangGraph"], "desc": PROJ}],
}

DIM_KEYS = [
    ("metric_ownership", "指标责任与达成（C）★", 20, 12),
    ("interview_hooks", "面试钩子设计（E）★", 10, 5),
    ("role_fit", "岗位契合度（赛道定位）", 20, 16),
    ("transferability", "技术可迁移性", 15, 10),
    ("project_depth", "项目深度与真实感", 20, 13),
    ("expression_structure", "表达与结构", 10, 7),
    ("advantage_section", "个人优势介绍", 5, 2),
]


def _report(**overrides) -> Report:
    sections = build_report_sections(PARSED)
    redline = Redline(
        blocks=[
            RedlineBlock(
                block_id="self_evaluation",
                label="个人优势",
                text=SELF_EVAL,
                edits=[
                    RedlineEdit(
                        1,
                        "self_evaluation",
                        "做过法律、金融、电网三个场景",
                        "负责三个场景的检索链路与 Agent 流程",
                        "面试官一定追你负责哪一块，原文没答",
                        True,
                    ),
                ],
            ),
            RedlineBlock(
                block_id="proj[0].desc",
                label="法律智能体平台 · 主程",
                text=PROJ,
                editable=True,
                edits=[
                    RedlineEdit(
                        2,
                        "proj[0].desc",
                        "最大执行步数写在配置里。",
                        "最大执行步数是【待补：实际配置值】，跑一半挂掉能接着跑。",
                        "长任务跑飞了怎么办，这题要有纸面答案",
                        False,
                    ),
                ],
            ),
        ]
    )
    report = Report(
        resume_id=1,
        user_id=1,
        report_date="2026-10-13",
        verdict={
            "direction": "RAG 应用（Agent / Workflow）",
            "direction_basis": "简历未附 JD，按关键词自动识别",
            "target_level": "中级",
            "level_basis": "相关工作年限约 1.7 年、计算机强相关、普通本科，落在中级区间",
            "candidate_name": PARSED["name"],
        },
        dimensions=[
            {
                "key": key,
                "label": label,
                "full": full,
                "star": "★" in label,
                "score": score,
                "note": f"{label}的待优化点：点名到项目 1 的成果那一条",
            }
            for key, label, full, score in DIM_KEYS
        ],
        total_score=sum(score for *_rest, score in DIM_KEYS),
        grade="C",
        grade_desc="项目描述需要重构后再投",
        grade_scale="A 85–100（稀缺档） / B 75–84（质量过关，可直接投） / C 65–74（需要重构后再投） / D 0–64（先补齐再谈投递）",
        to_next_grade=["法律、电网两个项目各补 1 处「优化前 → 优化后」的基线"],
        missing_keywords=["RAG", "评测集"],
        competition={
            "positioning_badge": "B 档（中上）",
            "positioning_note": "专业强相关 + 三个生产级项目 + 模块负责的角色，基本盘很硬",
            "cards": ["三个项目的检索链路和 Agent 流程都是我搭的"],
            "gaps": ["指标缺优化前基线，1–2 天能补"],
            "advice": ["投递方向锁定 RAG / Agent 应用开发的中级岗"],
            "salary_note": "未提供期望薪资，按中级档给参考：12K–15K",
        },
        redline=redline,
        sections=sections,
        interview={
            "deferred": False,
            "note": "",
            "questions": [
                {
                    "no": 1,
                    "question": "混合检索里 BM25 和向量检索各自解决什么问题？",
                    "kind": "项目深挖",
                    "project": "项目 1 · 法律智能体平台",
                    "answer": "简单说，BM25 管精确词命中，向量管语义泛化。法条编号这类精确 token 向量经常抓不住，反过来口语描述只能靠向量，所以两路并行再 RRF 融合。",
                    "followups": [
                        {"kind": "为什么", "text": "为什么不加大向量权重了事？"},
                        {"kind": "权衡/代价", "text": "混合的代价是什么？"},
                        {"kind": "边界", "text": "什么场景纯向量就够？"},
                    ],
                    "status": "需补强",
                    "missing": ["两路重合度"],
                }
            ],
            "distribution": {
                "total": 1,
                "by_kind": {"项目深挖": 1},
                "by_project": {"项目 1 · 法律智能体平台": 1},
                "weak": 1,
            },
        },
        apply_strategy=load_apply_strategy(),
        personalization={
            "one_line_label": SELF_EVAL,
            "opener": "三个项目的检索链路和 Agent 流程都是我搭的",
        },
    )
    for key, value in overrides.items():
        setattr(report, key, value)
    return report


def test_a_full_report_renders_and_passes_its_own_lint():
    document = render_report_html(_report())

    assert lint_report_html(document) == []
    for anchor in MODULE_IDS:
        assert f'id="{anchor}"' in document
    assert "<script src=" not in document and "http://" not in document.replace("http://www.w3.org", "")


def test_change_marks_and_annotations_number_one_to_one():
    document = render_report_html(_report())

    assert document.count('<sup class="mk') == 2
    assert document.count('<span class="mk">') == 2
    assert '<sup class="mk key">1</sup>' in document
    assert '<div class="note key">' in document
    assert "共 <b>2</b> 处改动，其中 <b>1</b> 处是关键项" in document


def test_a_number_that_was_never_measured_stays_a_placeholder():
    document = render_report_html(_report())

    assert '<span class="todo">【待补：实际配置值】</span>' in document
    assert "最大执行步数写在配置里。" in document  # 原文仍在，被删除线标着


def test_candidate_text_cannot_escape_into_a_tag():
    report = _report()
    report.verdict["candidate_name"] = '<img src=x onerror="alert(1)">'
    report.dimensions[0]["note"] = "<script>alert(2)</script>"

    document = render_report_html(report)

    assert "<img" not in document
    assert "&lt;img src=x onerror=" in document
    assert document.count("<script>") == 1, "只有页内那一段自述脚本，注入的那一段必须被转义"


def test_a_missing_redline_module_does_not_break_the_rest():
    document = render_report_html(_report(redline=None))

    assert lint_report_html(document) == []
    assert "这一节这次没能生成" in document


def test_a_deferred_interview_module_still_passes_lint():
    report = _report()
    report.interview = {
        "deferred": True,
        "note": "这一节先不生成。先把关键项改完、把欠的数跑出来，这一节再做价值更大。",
        "questions": [],
        "distribution": None,
    }

    document = render_report_html(report)

    assert lint_report_html(document) == []
    assert "这一节先不生成" in document


def test_a_clean_resume_says_so_instead_of_inventing_edits():
    report = _report()
    report.redline = Redline(blocks=[], mode="unchanged", free_note="这一版可以原样用，无需改动")

    document = render_report_html(report)

    assert lint_report_html(document) == []
    assert "这一版可以原样用，无需改动" in document
    assert '<sup class="mk' not in document


def test_the_total_row_is_the_sum_of_the_seven_rows():
    document = render_report_html(_report())

    assert '<td class="n">65</td><td class="n">100</td>' in document


def test_the_boss_module_carries_the_two_fillins_from_this_report_only():
    """§7 那两处个性化：一句话标签取第三节原文第一句，亮点取竞争分析那张牌——
    两处都是引用，不是模型另写一句自我介绍。内容住在 `personalization`，渲染器不自己算。"""
    report = _report()
    report.personalization = {"one_line_label": "1 年多 AI 应用开发经验", "opener": "三个项目的检索链路都是我搭的"}

    document = render_report_html(report)
    boss = document.split('id="m-boss"')[1].split("<footer")[0]

    assert "本报告的两处填空" in boss
    assert "quoted-resume" in boss
    assert "1 年多 AI 应用开发经验" in boss
    assert "三个项目的检索链路都是我搭的" in boss


def test_the_exemption_is_marked_not_blanket():
    """豁免按标记给：候选人原文（`quoted-resume`、`.paper`）放过，
    **报告自己写的叙述**里有禁词就整份下不了盘。这张牌住在竞争分析里，是我们的话。"""
    report = _report()
    report.competition["cards"] = ["高风险任务人工兜底这件事是我定的"]

    with pytest.raises(RuntimeError) as excinfo:
        render_report_html(report)

    assert "mechanism-word" in str(excinfo.value)


def test_a_banned_word_in_the_candidates_own_advantage_sentence_is_tolerated():
    """同一句"人工兜底"如果是**候选人自己写的**、被引成一句话标签，不该让整份报告报废：
    要收拾的是他的用词，做法是提示他改，而不是不给他报告。"""
    report = _report()
    quote = "5 年后端经验，高风险任务人工兜底由我配置"
    report.sections = [
        {**row, "text": quote if row["block_id"] == "self_evaluation" else row["text"]} for row in report.sections
    ]
    report.personalization = {"one_line_label": quote, "opener": "检索链路是我搭的"}
    # 原文换了字，批改稿那两条的 `del` 就落不到位置上；这一条要量的不是它，所以整块换成"零改动"。
    report.redline = Redline(blocks=[], mode="unchanged", free_note="这一版可以原样用，无需改动")

    document = render_report_html(report)

    assert quote in document
    assert lint_report_html(document) == []


def test_a_miscounted_total_is_refused_before_it_lands_on_disk():
    report = _report()
    report.total_score = 99  # 逐维相加是 65，合计行却写 99

    with pytest.raises(RuntimeError) as excinfo:
        render_report_html(report)

    assert "total-authority" in str(excinfo.value)
