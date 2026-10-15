"""多项目组合的六维尺 —— `docs/portfolio-report-spec.md` §2 的唯一权威（树里的第三把尺）。

三把尺各量一件事，别混：
* `resume_report_rubric` 量**整份简历**（七维，评级用字母 A/B/C/D）；
* `project_report_rubric` 量**单个项目**（六维，项目本身 95 分 + 它在简历里排第几 5 分）；
* 这一把量**两三个项目叠在一起**（六维满分与单项目那把同为 24/24/19/14/14/5，
  但维度名与判据换成组合口径：D2 问的是"换皮没有"，D5 只问跨项目那一层）。

两处**故意的**不对齐，改动要在台账里点名：
1. **档位区间与单项目那把不同**（本仓库自定，反推待定）：唯一的反推样本《总分析》里
   组合 94 分写的是"优秀"，而单项目那把尺 90 以上叫"标杆级"。照抄那套区间会让 94 变成
   标杆级，与参考件矛盾，所以组合按自己的档位切。代价是同一个词在两把尺里不是同一个区间——
   报告在合计那块用一行脚注明写这一句，不偷偷复用。
2. **1.3 的"组合覆盖"那一列由格子算出来，不信模型写的词**（见 `coverage_verdict`）：
   参考件里那一格写的是"金融最完整"这种带编辑色彩的话，机器推不出"最完整"，
   所以推出来的是"强（2/3 项覆盖，重点在金融）"。措辞与参考件不同，是刻意的。

这一把尺照样不做任何模型调用：给维度表、把模型返回的分读成可信的数、算位次那一维、
求和、落档、把能力覆盖与共用栈从**格子和技术栈清单**里推出来。
"""

from __future__ import annotations

import re
from typing import Any

from app.services.project_report_rubric import (
    RANK_SCORES,
    has_paired_value,
    metric_gap_clauses,
    rank_coefficient,
    score_or_none,
    split_clauses,
    stack_footprint,
)

# (键, 对外标签, 满分, 是否由模型判, 判分口径一句话)
# D6 不由模型判：它是"这一组占了简历里第几位到第几位"的函数。
DIMENSIONS: tuple[tuple[str, str, int, bool, str], ...] = (
    (
        "d1_role_signal",
        "D1 岗位信号强度",
        24,
        True,
        "把选中的几个项目叠在一起看：技能带盖得宽不宽、合起来是不是还在同一个岗位方向上、"
        "有没有一条能对得上 JD 的能力主线。单个项目自己的成色在它们各自的报告里量，"
        "这一维只量「合起来像不像同一个人来应聘这个岗位」。",
    ),
    (
        "d2_combo_distinct",
        "D2 组合区分度与真实感",
        24,
        True,
        "项目之间是真差异还是换个领域把同一件事写三遍：骨架重叠多少、技术栈重叠多少、"
        "每个项目有没有一到两个别的项目没有的技术决策、领域跨度大时说不说得清积累是怎么迁移的。"
        "这一维是组合层最容易失分的地方，也是单项目报告看不见的那一分。",
    ),
    (
        "d3_metric",
        "D3 指标责任与达成",
        19,
        True,
        "合起来看有没有可核验的量化产出：每个项目自己的前后对比齐不齐、"
        "几项改动一起上时贡献拆没拆开、业务效果（采纳率、人工节省、复用率）这一族"
        "是不是在几个项目里普遍偏薄。"
        "这一维扣分要落到**哪一个项目的哪一条**，笼统写「指标不足」不算点名。",
    ),
    (
        "d4_growth_line",
        "D4 技术纵深与迁移",
        14,
        True,
        "几个项目合起来能不能看出一条能力成长线（从单点优化到编排再到工程化与运营），"
        "而不是一条路走了三遍；共用栈展示熟练、差异栈展示选型判断，两头都得有。",
    ),
    (
        "d5_interview",
        "D5 面试承载力",
        14,
        True,
        "只看跨项目那一层问得下去吗：这几个项目有什么本质不同、只留一个留哪个、哪个最难、"
        "技术栈为什么重叠、行业跨度这么大怎么做到的——每一问都要有能讲两层的答案。"
        "单项目深挖的承载力在各自报告里已经算过，这一维不重复给分。",
    ),
    (
        "d6_rank_span",
        "D6 简历位次与叙事",
        5,
        False,
        "只看这一组项目占据简历里的第几位到第几位：起始位次定基本盘（第一位 5 分、"
        "第二位 3 分、第三位及以后 1 分，沿用单项目那把尺的系数），"
        "跨的位数越多越需要设计顺序，所以跨多位扣一分。",
    ),
)

DIMENSION_KEYS: tuple[str, ...] = tuple(row[0] for row in DIMENSIONS)
MODEL_JUDGED_KEYS: tuple[str, ...] = tuple(row[0] for row in DIMENSIONS if row[3])
TOTAL_FULL: int = sum(row[2] for row in DIMENSIONS)
BODY_FULL: int = sum(row[2] for row in DIMENSIONS if row[3])

# 位次那一维里"跨多位"扣的那一分（反推待定：唯一样本是参考件——占第 1~3 位、这一维写 4 分，
# 起始位次给 5、跨多位扣 1 是能对上那个 4 的最省解释；不是从原文推出来的规则）。
SPAN_PENALTY: int = 1

# 组合评级（档位区间见模块头第 1 条）。区间按参考件那一个点（94 → 优秀）切。
GRADE_BANDS: tuple[tuple[str, int, int, str], ...] = (
    ("标杆级", 95, 100, "组合层几乎没有短板：差异、归因、业务效果三处都拿得出出处"),
    ("优秀", 88, 94, "单项目质量都在优档，扣分集中在同质化风险、归因拆分与业务效果"),
    ("良好", 75, 87, "组合立得住，但至少要能回答「这三个项目有什么不同」"),
    ("需重组", 60, 74, "项目之间还没有形成关系，先补差异再谈组合"),
    ("暂不可投", 0, 59, "这一组项目合起来还没有可核验的产出"),
)

# 难度档位**不新造**：直接沿用单项目那把尺的 L1–L5（同一件事——链路上叠了几类范式）。
# 参考件组合难度写的是 "L5+"，树里没有 "+" 这一档，白名单不扩：模型只能提名 L1–L5，
# 服务端按 `is_known_difficulty` 收。这是模块头之外的第三条故意不对齐。
DIFFICULTY_BANDS: tuple[tuple[str, str, str], ...] = (
    ("L1", "教程复现", "照着教程把一条链路搭起来，选型与参数都是别人定的，说不出为什么这么选。"),
    ("L2", "单链路跑通", "一条链路自己走通了，有结果但没有对照，没有优化过程。"),
    ("L3", "链路上有优化与评测", "在链路上做过选型对比、重排/召回调优，并留下自己的指标口径。"),
    ("L4", "编排加工程化的完整体", "有条件分支/状态编排、结构化输出约束、部署与观测，但不涉及多智能体协作或模型训练。"),
    (
        "L5",
        "多范式叠加",
        "两类以上高难范式同时压在同一条链路上（多智能体协作、领域微调、图谱多跳、多模态、私有化推理）。",
    ),
)

# 组合红线。判法两档与单项目那把尺同一条口径：
#   "code"  = 服务端自己算，不问模型；
#   "model" = 模型只能提名，且证据必须逐字落在**被选项目原文的并集**里，命不中整条作废。
RED_LINES: tuple[tuple[str, str, str, str], ...] = (
    (
        "duplicate_projects",
        "同一个项目换名字写了两遍",
        "code",
        "选中项目里有两条正文折叠掉空白与标点后**完全相同**。",
    ),
    (
        "others_work_combo",
        "整组不是本人参与却都写成自己的",
        "model",
        "几个项目都写成「我主导 / 我负责全部」，可原文里给不出各自的分工边界——同行一问投入分配就露。",
    ),
    (
        "no_growth_line",
        "一条路走了三遍",
        "model",
        "几个项目其实是同一件事换个领域重做，且**给不出任何一个别的项目没有的技术决策**——"
        "面试官问「这三个有什么本质不同」时只能重复技术栈。",
    ),
    (
        "unanswerable_combo",
        "组合层一问就穿",
        "model",
        "跨项目那几问（只留一个留哪个、哪个最难、跨度这么大怎么做到的）里，"
        "原文自己就把答案堵死了——要么三处口径互相矛盾，要么明写着说不清。",
    ),
)

RED_LINE_KEYS: tuple[str, ...] = tuple(row[0] for row in RED_LINES)
_CODE_JUDGED_RED_LINES: tuple[str, ...] = tuple(row[0] for row in RED_LINES if row[2] == "code")
# 代码能逐字核的那一条里，只有"完全相同"够得上**出局**；近似雷同（换皮的中间形状）
# 只出证据。理由与单项目那把尺同一条：同一公司两个项目共用一栈是常态，
# 把"技术栈集合相同"判成出局是必然误伤，不是门。
_REJECTING_CODE_RED_LINES: frozenset[str] = frozenset({"duplicate_projects"})
# 近似雷同判据的阈值（反推待定：先按字符三元组 Jaccard ≥ 0.85，
# 上线前要在真简历上量一遍假阳性——见 `docs/portfolio-report-spec.md` §3）。
NEAR_COPY_THRESHOLD: float = 0.85

_LABELS: dict[str, str] = {row[0]: row[1] for row in DIMENSIONS}
_FULLS: dict[str, int] = {row[0]: row[2] for row in DIMENSIONS}

# 1.3 与 2.1 的能力维度白名单：模型只能从这些里选，服务端按格子算覆盖结论。
# 词表反推自参考件那 12 行（RAG / Agent 这一族的主流能力带）。**新增一行要有出处**，
# 不在白名单里的提名整行作废并记对内——这一列决定"哪一类能力只在一个项目里出现"，
# 让模型自由造维度等于让它自己造题目再自己答。
CAPABILITIES: tuple[tuple[str, str], ...] = (
    ("doc_parsing", "文档解析与结构化"),
    ("hybrid_retrieval", "混合检索"),
    ("knowledge_graph", "知识图谱"),
    ("rrf_rerank", "RRF / Rerank"),
    ("agent_orchestration", "Agent 编排"),
    ("tool_protocol", "工具协议化（MCP）"),
    ("rule_llm", "规则 + LLM 协同"),
    ("hitl", "HITL 中断续跑"),
    ("refusal", "拒答 / 不确定性表达"),
    ("llmops", "LLMOps / 分层评测"),
    ("cost_control", "成本控制"),
    ("discriminative_feature", "强区分特征处理"),
)
CAPABILITY_KEYS: tuple[str, ...] = tuple(row[0] for row in CAPABILITIES)
CAPABILITY_LABELS: dict[str, str] = {row[0]: row[1] for row in CAPABILITIES}

# 覆盖三档。格子只有这三种取值，第四种（"大概覆盖"）不接受。
COVER_FULL = "重点覆盖"
COVER_PARTIAL = "部分覆盖"
COVER_NONE = "未覆盖"
COVERAGE_CELLS: tuple[str, ...] = (COVER_FULL, COVER_PARTIAL, COVER_NONE)
# 参考件图例里用的是 ● / ○，界面与下载共用这一组符号。
COVERAGE_MARKS: dict[str, str] = {COVER_FULL: "●", COVER_PARTIAL: "○", COVER_NONE: ""}

# 列数跟着项目数长的两张表（1.2 横向对比、1.3/2.1 覆盖矩阵）在窄屏上的地板宽（px）。
# 这三个数是量出来的，不是拟的：活页与下载件在 400px 视口下格子压到 36px，
# 一个项目名换三行、能力名一格两个字；同一张表在 700px 以上稳定是 86px 一格。
# 所以窄屏不许继续压表——按这一组宽算出整张表的最小宽，让它在外层容器里横向滚。
WIDE_LABEL_PX = 96
WIDE_CELL_PX = 86
WIDE_TAIL_PX = 100


def wide_table_min_px(project_count: int, *, with_tail: bool = False) -> int:
    """一张随项目数变宽的表至少要多宽，才不会出现"一格两个字"。"""
    return WIDE_LABEL_PX + WIDE_CELL_PX * int(project_count) + (WIDE_TAIL_PX if with_tail else 0)


# 1.1 那张六维评分卡不随项目数长（五列固定），但"主要扣分理由"那一列吃的是长句子：
# 307px 视口实测它被压到 63px、一句话排 15 行。地板宽同样取自这张表自己的读数——
# 它在 560px 视口那一档的实测分配是 85/41/46/58/240，合计就是下面这个数。
SCORECARD_MIN_PX = 470


# 跨项目面试的六个题型：反推自参考件那 12 题的实际问法，不是先验拟的。
QUESTION_KINDS: tuple[str, ...] = ("差异与取舍", "选型与理由", "真实与边界", "评测与归因", "整合与演进", "沉淀与成长")
QUESTION_STATUSES: tuple[str, ...] = ("可答", "需补强", "高危")
TARGET_QUESTION_COUNT = 12

# 2.4 跨项目面试时序那五轮：轮次名写死在代码里，模型只许往里面填话。
# 五轮是组合层独有的形状（单项目那一族没有"质疑真实性"这一轮），
# 顺序本身是判据：第三、第四轮才是组合层面的胜负手。
INTERVIEW_ROUNDS: tuple[tuple[str, str], ...] = (
    ("single_deep_dive", "第一轮 · 挑一个项目深挖"),
    ("selection_reason", "第二轮 · 问技术选型的理由"),
    ("cross_compare", "第三轮 · 跨项目横向对比"),
    ("authenticity", "第四轮 · 质疑真实性"),
    ("next_step", "收尾 · 未来方向"),
)
INTERVIEW_ROUND_KEYS: tuple[str, ...] = tuple(row[0] for row in INTERVIEW_ROUNDS)
INTERVIEW_ROUND_LABELS: dict[str, str] = {row[0]: row[1] for row in INTERVIEW_ROUNDS}
# 参考件里点名的"胜负手"两轮（这一句直接来自原文，不是推的）。
DECISIVE_ROUNDS: tuple[str, ...] = ("cross_compare", "authenticity")

# "补齐后预计"那一列要点名维度。两种写法都认：编号（D3）与标签里的词。
_DIMENSION_HINTS: tuple[str, ...] = (
    "岗位信号",
    "区分度",
    "真实感",
    "指标责任",
    "纵深",
    "迁移",
    "面试承载",
    "位次",
    "叙事",
)

_TODO = re.compile(r"【待补[^】]*】")
_TRIPLE = re.compile(r"\s+")

# 1.2 横向对比那七行：行名写死在代码里，模型只许按行填每个项目的说法。
# 这七行是参考件实际给了的七行，少一行就是表格缺角。
COMPARE_ROWS: tuple[tuple[str, str], ...] = (
    ("domain", "领域"),
    ("skeleton", "核心骨架"),
    ("orchestration", "编排方式"),
    ("retrieval", "检索方案"),
    ("highlight", "核心亮点"),
    ("metric", "关键指标"),
    ("transferable", "可迁移亮点"),
)
COMPARE_ROW_KEYS: tuple[str, ...] = tuple(row[0] for row in COMPARE_ROWS)
COMPARE_ROW_LABELS: dict[str, str] = {row[0]: row[1] for row in COMPARE_ROWS}


def dimension_label(key: str) -> str:
    return _LABELS.get(key, key)


def dimension_full(key: str) -> int:
    return _FULLS.get(key, 0)


def rubric_prompt_block() -> str:
    lines = []
    for key, label, full, judged, note in DIMENSIONS:
        tail = "" if judged else "（这一维由服务端按位次区间算，不要打分）"
        lines.append(f"- {key}（{label}，满分 {full}）：{note}{tail}")
    lines.append(f"六维满分之和 = {TOTAL_FULL}，其中前五维是组合本体（{BODY_FULL} 分），第六维是排列（5 分）。")
    return "\n".join(lines)


def red_line_prompt_block() -> str:
    """红线表里**要模型提名**的那三条：证据必须逐字落在被选项目原文并集里，否则整条作废。"""
    return "\n".join(f"- {key}（{label}）：{rubric}" for key, label, judged, rubric in RED_LINES if judged == "model")


def judged_red_line_keys() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(代码自算的两类键, 模型只能提名的键)。"""
    return _CODE_JUDGED_RED_LINES, tuple(row[0] for row in RED_LINES if row[2] == "model")


def rejecting_code_red_line(key: str) -> bool:
    """代码自算的那一条里，只有它够得上出局；其余只出证据。"""
    return key in _REJECTING_CODE_RED_LINES


def red_line_label(key: str) -> str:
    for row in RED_LINES:
        if row[0] == key:
            return row[1]
    return key


def red_line_prompt_for(key: str) -> str:
    for row in RED_LINES:
        if row[0] == key:
            return row[3]
    return ""


def difficulty_prompt_block() -> str:
    return "\n".join(f"- {level}（{name}）：{what}" for level, name, what in DIFFICULTY_BANDS)


def is_known_difficulty(level: Any) -> bool:
    return isinstance(level, str) and level.strip() in {row[0] for row in DIFFICULTY_BANDS}


def grade_scale_block() -> str:
    return " / ".join(f"{name} {low}–{high}（{desc}）" for name, low, high, desc in GRADE_BANDS)


def grade_of(total: int | None) -> str | None:
    if total is None:
        return None
    for grade, low, high, _desc in GRADE_BANDS:
        if low <= total <= high:
            return grade
    return GRADE_BANDS[-1][0]


def grade_desc_of(total: int | None) -> str:
    grade = grade_of(total)
    for name, _low, _high, desc in GRADE_BANDS:
        if name == grade:
            return desc
    return ""


def mentions_dimension(text: str) -> bool:
    body = text or ""
    if re.search(r"[Dd][1-6]", body):
        return True
    return any(hint in body for hint in _DIMENSION_HINTS)


# ------------------------------------------------------------------ D6：位次区间
def span_of(indices: list[int]) -> tuple[int, int]:
    """这一组占据的第一位与最后一位（从 1 起算，按简历里的顺序，不是勾选顺序）。"""
    clean = sorted(int(i) for i in indices)
    if not clean:
        return (0, 0)
    return (clean[0] + 1, clean[-1] + 1)


def span_score(indices: list[int]) -> int:
    """起始位次给基本盘分（沿用单项目那把尺的 5/3/1），跨多位扣 SPAN_PENALTY 一分，最低 1 分。"""
    first, last = span_of(indices)
    if first <= 0:
        return 0
    base = RANK_SCORES[min(first - 1, len(RANK_SCORES) - 1)]
    if last - first >= 1:
        base -= SPAN_PENALTY
    return max(1, base)


def span_note(indices: list[int]) -> str:
    first, last = span_of(indices)
    if last == first:
        return f"占据简历第 {first} 位；越靠前，这一项给得越高。"
    return f"占据简历第 {first}~{last} 位；越靠前给分越高，跨的位数越多越要设计顺序。"


def read_dimensions(raw: Any, indices: list[int]) -> list[dict[str, Any]]:
    """模型给的五维 + 服务端算的位次那一维，读成固定六行。位次那一行不接受模型给的分。"""
    source = raw if isinstance(raw, dict) else {}
    first, last = span_of(indices)
    rows: list[dict[str, Any]] = []
    for key, label, full, judged, _note in DIMENSIONS:
        if not judged:
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "full": full,
                    "score": span_score(indices),
                    "note": span_note(indices),
                    "positional": True,
                    "span": [first, last],
                }
            )
            continue
        value = source.get(key)
        note = ""
        if isinstance(value, dict):
            score = score_or_none(value.get("score"), full)
            note = value["note"].strip() if isinstance(value.get("note"), str) else ""
        else:
            score = score_or_none(value, full)
        rows.append({"key": key, "label": label, "full": full, "score": score, "note": note, "positional": False})
    return rows


def total_of(rows: list[dict[str, Any]]) -> int | None:
    """六维之和；任一维未知则总分未知——缺维度不等于 0 分（三把尺同一条口径）。"""
    scores = [row["score"] for row in rows]
    if len(scores) != len(DIMENSIONS) or any(score is None for score in scores):
        return None
    return sum(scores)  # type: ignore[arg-type]


# ------------------------------------------------------------------ 表头那几个派生量
def average_of(scores: list[int | None]) -> float | None:
    """表头「单项目均分」那一格：只算**已经跑过且给得出分**的那几份。

    一份没跑就整格留空由调用侧决定；这里不做「缺的那份按 0 算」那种事——
    一个少算了一份的平均数比「没算出来」更坏，它看起来像个真数。
    """
    known = [int(score) for score in scores if score is not None]
    if not known:
        return None
    return round(sum(known) / len(known), 1)


def _norm_stack_atom(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", (value or "").lower())


def _atoms(tech: list[str]) -> list[tuple[str, str]]:
    """技术栈条目拆成可比对的原子：斜杠/顿号并列写法（"Milvus / Chroma"）各算一个。

    每个原子带两份：**折叠形**用来跨项目判同一个组件（大小写、连字符、空格都不算差异），
    **显示形**是原文里出现的那一个写法。折叠形不能直接上屏——把 "FastAPI" 画成 "fastapi"
    会让人以为是另一个组件，而这两栏的正经用途就是回答"这套栈是不是同一套"。
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in tech or []:
        for atom in re.split(r"[/／|｜、,，]+", str(item or "")):
            display = atom.strip()
            folded = _norm_stack_atom(display)
            if len(folded) >= 2 and folded not in seen:
                seen.add(folded)
                out.append((folded, display))
    return out


def stack_reuse(tech_by_index: dict[int, list[str]]) -> dict[str, Any]:
    """共用栈与差异栈**由服务端从技术栈清单算**，不信模型自报的那一份。

    共用 = 出现在 ≥2 个项目里的组件；差异 = 只出现在 1 个项目里的组件。
    这两栏分别回答"这套选型稳不稳"和"是不是照搬"，是回答同质化质疑的两层，
    所以宁可只列真在清单里出现过的，也不放模型编的组件名。
    """
    counts: dict[str, int] = {}
    where: dict[str, list[int]] = {}
    display: dict[str, str] = {}
    for index, tech in sorted(tech_by_index.items()):
        for folded, name in _atoms(tech):
            display.setdefault(folded, name)
            if index not in where.setdefault(folded, []):
                where[folded].append(int(index))
                counts[folded] = counts.get(folded, 0) + 1
    shared = sorted((f for f, count in counts.items() if count >= 2), key=lambda f: (-counts[f], f))
    unique: dict[str, list[str]] = {}
    for index in sorted(tech_by_index):
        unique[str(index)] = sorted(display[f] for f, count in counts.items() if count == 1 and index in where[f])
    total = len(counts)
    return {
        "shared": [display[f] for f in shared],
        "shared_count": len(shared),
        "unique_by_index": unique,
        "total_atoms": total,
        # 共用比例是 D2 的证据：一格 0.9 与一格 0.3 说的是两件不同的事。
        "shared_ratio": round(len(shared) / total, 3) if total else None,
    }


def model_claimed_shared(claimed: list[str], shared: list[str]) -> dict[str, list[str]]:
    """模型自报的"共用栈"与服务端算出来的差集：它报的组件若不在 ≥2 个项目的清单里，整条丢弃。"""
    pool = {_norm_stack_atom(a) for a in shared}
    kept: list[str] = []
    dropped: list[str] = []
    for item in claimed or []:
        folded = _norm_stack_atom(str(item))
        if folded and folded in pool:
            kept.append(str(item).strip())
        else:
            dropped.append(str(item).strip())
    return {"kept": kept, "dropped": dropped}


# ------------------------------------------------------------------ 1.3 能力覆盖
def normalize_cell(value: Any) -> str:
    raw = str(value or "").strip()
    if raw in COVERAGE_CELLS:
        return raw
    # 参考件图上用的是 ● / ○，模型两种写法都可能给。
    if raw == "●":
        return COVER_FULL
    if raw == "○":
        return COVER_PARTIAL
    if raw in ("", "—", "-", "×", "✕", "空白"):
        return COVER_NONE
    if "重点" in raw or "全覆盖" in raw:
        return COVER_FULL
    if "部分" in raw:
        return COVER_PARTIAL
    return COVER_NONE


def coverage_verdict(cells: dict[int, str], project_count: int) -> dict[str, Any]:
    """组合覆盖那一格由**格子**算出来——模型只能填格子，不能自己写结论。

    极强 = 每个被选项目都重点覆盖；强 = 至少一个项目重点覆盖；
    中 = 只有部分覆盖；未覆盖 = 一格重点都没有、连部分都没有。
    """
    full = [index for index, cell in cells.items() if cell == COVER_FULL]
    partial = [index for index, cell in cells.items() if cell == COVER_PARTIAL]
    count = max(int(project_count), 1)
    if full and len(full) >= count:
        word, detail = "极强", f"{count} 个项目全覆盖"
    elif full:
        word, detail = "强", f"{len(full)}/{count} 项重点覆盖"
    elif partial:
        word, detail = "中", f"{len(partial)}/{count} 项部分覆盖"
    else:
        word, detail = "未覆盖", "这一组里没有一个项目做到"
    return {"word": word, "detail": detail, "full": sorted(full), "partial": sorted(partial)}


def clean_capability_rows(raw: Any, wanted_indices: list[int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """把模型给的覆盖矩阵读成固定表：维度必须在白名单里、项目编号必须在选中集里、格子归三档。

    返回 (行, 被丢的)。**同一维度重复提名只留第一条**——两行同名不同格子，
    候选人不知道信哪一行，而机检也分不出这是重写还是补漏。
    """
    rows: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    seen: set[str] = set()
    wanted = {int(i) for i in wanted_indices}
    for item in raw if isinstance(raw, list) else []:
        data = item if isinstance(item, dict) else {}
        key = str(data.get("capability") or "").strip()
        if key not in CAPABILITY_LABELS:
            dropped.append({"reason": "capability_off_list", "detail": key[:40]})
            continue
        if key in seen:
            dropped.append({"reason": "capability_duplicate", "detail": key})
            continue
        cells: dict[int, str] = {}
        bad_index = False
        for row in data.get("cells") if isinstance(data.get("cells"), list) else []:
            entry = row if isinstance(row, dict) else {}
            try:
                index = int(entry.get("project_index"))
            except (TypeError, ValueError):
                bad_index = True
                continue
            if index not in wanted or index in cells:
                bad_index = True
                continue
            cells[index] = normalize_cell(entry.get("cell"))
        if bad_index or len(cells) != len(wanted):
            dropped.append({"reason": "cells_incomplete", "detail": f"{key}：{len(cells)}/{len(wanted)} 列"})
            continue
        seen.add(key)
        rows.append(
            {
                "key": key,
                "label": CAPABILITY_LABELS[key],
                "cells": cells,
                "verdict": coverage_verdict(cells, len(wanted)),
            }
        )
    return rows, dropped


# ------------------------------------------------------------------ 红线 1：换皮的两种形状
def _fold_text(value: str) -> str:
    """折叠到只剩可比较的字符：空白、标点、`【待补…】` 都不算内容差异。"""
    body = _TODO.sub("", value or "")
    body = re.sub(r"\s+", "", body)
    return re.sub(r"[，。；、：:；;．.\-—_*#（）()【】\[\]\"'“”‘’/|]+", "", body)


def trigrams(value: str) -> set[str]:
    folded = _fold_text(value)
    if len(folded) < 3:
        return {folded} if folded else set()
    return {folded[i : i + 3] for i in range(len(folded) - 2)}


def pair_similarity(a: str, b: str) -> float:
    left, right = trigrams(a), trigrams(b)
    if not left or not right:
        return 0.0
    return round(len(left & right) / len(left | right), 3)


def duplicate_pairs(text_by_index: dict[int, str]) -> list[dict[str, Any]]:
    """折叠后**完全相同**的两条正文——出局证据。"""
    out: list[dict[str, Any]] = []
    items = sorted(text_by_index.items())
    for position, (index, text) in enumerate(items):
        folded = _fold_text(text)
        if not folded:
            continue
        for other_index, other_text in items[position + 1 :]:
            other = _fold_text(other_text)
            if other and other == folded:
                out.append({"kind": "identical", "pair": [index, other_index], "ratio": 1.0})
    return out


def near_copy_pairs(text_by_index: dict[int, str], threshold: float = NEAR_COPY_THRESHOLD) -> list[dict[str, Any]]:
    """像到一问就穿、但还没有完全相同的那几对——只出证据，不判出局。"""
    out: list[dict[str, Any]] = []
    items = sorted(text_by_index.items())
    for position, (index, text) in enumerate(items):
        for other_index, other_text in items[position + 1 :]:
            ratio = pair_similarity(text, other_text)
            if ratio >= threshold:
                out.append({"kind": "near_copy", "pair": [index, other_index], "ratio": ratio})
    return out


def metric_gaps_by_project(text_by_index: dict[int, str]) -> dict[str, list[dict[str, str]]]:
    """每个项目自己的"写了提升却没闭合"条目——D3 在组合层的点名粒度是**一条**，不是整组。"""
    return {str(index): metric_gap_clauses(text) for index, text in sorted(text_by_index.items())}


__all__ = [
    "BODY_FULL",
    "CAPABILITIES",
    "CAPABILITY_KEYS",
    "CAPABILITY_LABELS",
    "COMPARE_ROW_KEYS",
    "COMPARE_ROW_LABELS",
    "COMPARE_ROWS",
    "COVER_FULL",
    "COVER_NONE",
    "COVER_PARTIAL",
    "COVERAGE_CELLS",
    "COVERAGE_MARKS",
    "DECISIVE_ROUNDS",
    "DIFFICULTY_BANDS",
    "DIMENSIONS",
    "DIMENSION_KEYS",
    "GRADE_BANDS",
    "INTERVIEW_ROUND_KEYS",
    "INTERVIEW_ROUND_LABELS",
    "INTERVIEW_ROUNDS",
    "MODEL_JUDGED_KEYS",
    "NEAR_COPY_THRESHOLD",
    "QUESTION_KINDS",
    "QUESTION_STATUSES",
    "RANK_SCORES",
    "RED_LINES",
    "RED_LINE_KEYS",
    "SCORECARD_MIN_PX",
    "SPAN_PENALTY",
    "TARGET_QUESTION_COUNT",
    "TOTAL_FULL",
    "WIDE_CELL_PX",
    "WIDE_LABEL_PX",
    "WIDE_TAIL_PX",
    "average_of",
    "clean_capability_rows",
    "coverage_verdict",
    "difficulty_prompt_block",
    "dimension_full",
    "dimension_label",
    "duplicate_pairs",
    "grade_desc_of",
    "grade_of",
    "grade_scale_block",
    "has_paired_value",
    "is_known_difficulty",
    "judged_red_line_keys",
    "mentions_dimension",
    "metric_gap_clauses",
    "metric_gaps_by_project",
    "model_claimed_shared",
    "near_copy_pairs",
    "normalize_cell",
    "pair_similarity",
    "read_dimensions",
    "red_line_label",
    "red_line_prompt_block",
    "red_line_prompt_for",
    "rejecting_code_red_line",
    "rubric_prompt_block",
    "rank_coefficient",
    "span_note",
    "span_of",
    "span_score",
    "split_clauses",
    "stack_footprint",
    "stack_reuse",
    "total_of",
    "trigrams",
    "wide_table_min_px",
]
